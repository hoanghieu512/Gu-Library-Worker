# tests/test_acceptance_synthetic.py
import json
from pathlib import Path
from gu_library_worker.config import Paths
from gu_library_worker.scan import scan_once

def _convert(src, outdir, **kw):
    import fitz
    out = outdir / (src.stem + ".pdf")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Điều 1. Phạm vi điều chỉnh", fontsize=12)
    doc.save(out); doc.close()
    return out

def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))

def test_word_law_yields_dieu_khoan_with_pages(make_docx, tmp_path):
    paths = Paths(kho_root=tmp_path)
    (tmp_path / "_inbox").mkdir()
    src = make_docx("law.docx", [
        "Chương I QUY ĐỊNH CHUNG",
        "Điều 1. Phạm vi điều chỉnh",
        "Luật này quy định về công chứng.",
        "Điều 2. Giải thích từ ngữ",
        "1. Công chứng là việc chứng nhận.",
    ])
    src.rename(tmp_path / "_inbox" / "[Luật Công chứng] law.docx")
    scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    sc = _read_json(tmp_path / "Luật Công chứng" / "law.json")
    assert sc["kind"] == "legal"
    types = {(u["type"], u["label"]) for u in sc["units"]}
    assert ("dieu", "Điều 1") in types
    assert ("dieu", "Điều 2") in types
    assert ("khoan", "Khoản 1") in types
    assert all(u["page"] >= 1 for u in sc["units"])
    # Word origin has no PDF coordinates -> no bbox written (still valid)
    assert all("bbox" not in u for u in sc["units"])
    assert not (tmp_path / "_inbox" / "[Luật Công chứng] law.docx").exists()

def test_pptx_one_unit_per_slide(make_pptx, tmp_path):
    paths = Paths(kho_root=tmp_path)
    (tmp_path / "_inbox").mkdir()
    # 3-page canonical pdf so slide pages 1..3 anchor cleanly
    def convert3(src, outdir, **kw):
        import fitz
        out = outdir / (src.stem + ".pdf")
        doc = fitz.open()
        for i in range(3):
            doc.new_page().insert_text((72, 72), f"Slide {i+1}", fontsize=12)
        doc.save(out); doc.close()
        return out
    src = make_pptx("deck.pptx", ["A", "B", "C"])
    src.rename(tmp_path / "_inbox" / "[Hiến pháp] deck.pptx")
    scan_once(paths, convert_fn=convert3, sleep=lambda s: None)
    sc = _read_json(tmp_path / "Hiến pháp" / "deck.json")
    assert sc["kind"] == "slide"
    assert [u["label"] for u in sc["units"]] == ["Slide 1", "Slide 2", "Slide 3"]
    assert [u["page"] for u in sc["units"]] == [1, 2, 3]

def test_real_pdf_origin_not_reconverted(make_pdf, tmp_path):
    paths = Paths(kho_root=tmp_path)
    (tmp_path / "_inbox").mkdir()
    src = make_pdf("vb.pdf", [
        "Điều 1. Nội dung trang một.",
        "Đoạn văn xuôi trang hai không có cấu trúc điều khoản.",
    ])
    original_bytes = src.read_bytes()
    src.rename(tmp_path / "_inbox" / "[Luật X] vb.pdf")
    scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    out_pdf = tmp_path / "Luật X" / "vb.pdf"
    assert out_pdf.read_bytes() == original_bytes  # canonical = original, no reconvert
    sc = _read_json(tmp_path / "Luật X" / "vb.json")
    assert sc["sourceFormat"] == "pdf"
    joined = " ".join(u["text"] for u in sc["units"])
    assert "trang một" in joined and "trang hai" in joined  # no text lost
    # PDF origin -> every unit carries a valid top-left bbox
    for u in sc["units"]:
        assert len(u["bbox"]) == 4
        x0, y0, x1, y1 = u["bbox"]
        assert x0 < x1 and y0 < y1

def test_tmp_file_left_alone(tmp_path):
    paths = Paths(kho_root=tmp_path)
    (tmp_path / "_inbox").mkdir()
    (tmp_path / "_inbox" / "[Môn] x.pdf.tmp").write_bytes(b"half written")
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert (tmp_path / "_inbox" / "[Môn] x.pdf.tmp").exists()
    assert report.processed == 0
