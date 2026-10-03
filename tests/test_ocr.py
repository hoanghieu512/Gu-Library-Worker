# tests/test_ocr.py
import sys
import pytest
from gu_library_worker import ocr
from gu_library_worker.ocr import OcrLine, clean_text, page_verdict, parse_tsv
from gu_library_worker.schema import Unit, Document, to_sidecar, validate_sidecar

TSV_HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"

def _row(level, block, par, line, word, left, top, w, h, conf, text):
    return f"{level}\t1\t{block}\t{par}\t{line}\t{word}\t{left}\t{top}\t{w}\t{h}\t{conf}\t{text}\n"

def test_clean_text_fixes_eth_lookalikes_and_composes():
    assert clean_text("Ðiều 5. Hiệu lực") == "Điều 5. Hiệu lực"
    assert clean_text("ðã ban hành") == "đã ban hành"
    assert clean_text("Điều") == "Điều"    # combining marks -> NFC
    assert clean_text("phòng ñaàu") == "phòng ñaàu"     # no VNI decoding of OCR text

def test_parse_tsv_groups_words_into_lines_in_points():
    tsv = TSV_HEADER + "".join([
        _row(1, 0, 0, 0, 0, 0, 0, 1654, 2339, -1, ""),            # page row: ignored
        _row(5, 1, 1, 1, 1, 200, 400, 100, 40, 96, "Điều"),
        _row(5, 1, 1, 1, 2, 320, 402, 40, 38, 90, "1."),
        _row(5, 1, 1, 2, 1, 200, 460, 300, 40, 80, "Phạm"),
        _row(5, 1, 1, 2, 2, 520, 460, 10, 40, -1, " "),            # empty word: ignored
        _row(5, 2, 1, 1, 1, 200, 600, 120, 40, 70, "Khoản"),
    ])
    lines = parse_tsv(tsv, dpi=200)
    assert [l.text for l in lines] == ["Điều 1.", "Phạm", "Khoản"]
    assert lines[0].conf == 93.0
    assert lines[0].bbox == [72.0, 144.0, 129.6, 158.4]        # px * 72 / 200
    assert lines[0].block == (1, 1) and lines[2].block == (2, 1)

def test_median_line_height_uses_long_lines_only():
    lines = [OcrLine("một dòng chữ đủ dài để tính", [0, 0, 100, 9], 90, (1, 1)),
             OcrLine("ngắn", [0, 0, 10, 30], 90, (1, 1))]
    assert ocr.median_line_height_px(lines, 200) == pytest.approx(25.0)
    assert ocr.median_line_height_px([lines[1]], 200) is None

WORDS = frozenset("luật này quy định về các tội phạm và hình phạt".split())

def _lines(*texts, conf=90.0):
    return [OcrLine(t, [0, 0, 100, 10], conf, (1, 1)) for t in texts]

def test_verdict_keeps_good_text():
    assert page_verdict(_lines("Luật này quy định về các tội phạm và hình phạt."), WORDS) == (True, "")

def test_verdict_rejects_too_little_text():
    ok, why = page_verdict(_lines("7"), WORDS)
    assert not ok and "too little" in why

def test_verdict_rejects_low_confidence():
    ok, why = page_verdict(_lines("Luật này quy định về các tội phạm và hình phạt.", conf=40), WORDS)
    assert not ok and "confidence" in why

def test_verdict_rejects_unrecognised_words():
    ok, why = page_verdict(_lines("HLH5 nằm Eưúc lại bỏ hình păai tự hình đốn vớt"), WORDS)
    assert not ok and "unrecognised" in why

def test_shipped_lexicon_is_fixed_vietnamese_word_list():
    words = ocr.lexicon()
    assert {"điều", "khoản", "luật", "người", "trường"} <= words
    assert all(1 <= len(w) <= 7 and w == w.lower() for w in words)

def test_unit_ocr_flag_serialized_only_when_true():
    doc = Document(title="t", source="share", sourceFormat="pdf", kind="prose",
                   addedAt="2026-10-03T00:00:00+07:00", pageCount=1,
                   units=[Unit("paragraph", "", [], "chữ OCR", 1, ocr=True),
                          Unit("paragraph", "", [], "chữ thường", 1)])
    sc = to_sidecar(doc)
    assert sc["units"][0]["ocr"] is True
    assert "ocr" not in sc["units"][1]
    assert validate_sidecar(sc) == []

def test_validate_rejects_non_boolean_ocr():
    doc = Document(title="t", source="share", sourceFormat="pdf", kind="prose",
                   addedAt="2026-10-03T00:00:00+07:00", pageCount=1,
                   units=[Unit("paragraph", "", [], "x", 1)])
    sc = to_sidecar(doc)
    sc["units"][0]["ocr"] = "yes"
    assert any("ocr must be a boolean" in e for e in validate_sidecar(sc))

def test_find_engine_reports_missing_binary(monkeypatch):
    monkeypatch.setenv("GULIB_TESSERACT", r"Z:\nowhere\tesseract.exe")
    monkeypatch.setattr(ocr, "_TESSERACT_PATHS", ())
    monkeypatch.setattr(ocr.shutil, "which", lambda name: None)
    engine, reason = ocr.find_engine()
    assert engine is None and "not found" in reason

def test_find_engine_rejects_a_model_that_is_not_tessdata_best(tmp_path, monkeypatch):
    tessdata = tmp_path / "tessdata"
    tessdata.mkdir()
    (tessdata / "vie.traineddata").write_bytes(b"standard model, not best")
    monkeypatch.setenv("GULIB_TESSERACT", sys.executable)    # any existing file
    monkeypatch.setenv("GULIB_TESSDATA", str(tessdata))
    engine, reason = ocr.find_engine()
    assert engine is None and "tessdata_best" in reason
