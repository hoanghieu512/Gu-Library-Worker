import json
from pathlib import Path

import pytest

from gu_library_worker.schema import validate_sidecar
from gu_library_worker.vnifix import (
    BACKUP_DIRNAME,
    convert_sidecar,
    needs_vni_fix,
    vnifix_kho,
)


def _sidecar(units, *, kind="slide", page_count=3):
    return {
        "schemaVersion": 1,
        "title": "Bài giảng",
        "source": "share",
        "addedAt": "2026-07-23T00:47:19+07:00",
        "sourceFormat": "pptx",
        "pageCount": page_count,
        "kind": kind,
        "units": units,
    }


def _slide(text, page):
    return {"type": "slide", "label": f"Slide {page}", "path": [],
            "text": text, "page": page, "bbox": [10.0, 20.0, 30.0, 40.0]}


def _vni_doc():
    return _sidecar([
        _slide("CHÖÔNG XV\nMIEÃN, GIAÛM TRAÙCH NHIEÄM HÌNH SÖÏ", 1),
        _slide("Khaùi nieäm vaø yù nghóa cuûa QÑHP", 2),
        _slide("Ñoái töôïng ñieàu chænh", 3),
    ])


# --- detection ---------------------------------------------------------------

def test_detects_vni_text():
    assert needs_vni_fix(_vni_doc()) is True


def test_unicode_document_is_not_a_target():
    doc = _sidecar([_slide("CHƯƠNG XV — MIỄN, GIẢM TRÁCH NHIỆM HÌNH SỰ", 1)])
    assert needs_vni_fix(doc) is False


def test_ascii_document_is_not_a_target():
    assert needs_vni_fix(_sidecar([_slide("Bai 15 - Mien giam TNHS", 1)])) is False


def test_one_vni_unit_among_unicode_ones_still_flags_the_document():
    doc = _sidecar([
        _slide("CÁC TRƯỜNG HỢP LOẠI TRỪ TRÁCH NHIỆM HÌNH SỰ", 1),
        _slide("I. Khaùi nieäm chung", 2),
    ])
    assert needs_vni_fix(doc) is True


# --- conversion --------------------------------------------------------------

def test_converts_every_vni_unit():
    out, changed = convert_sidecar(_vni_doc())
    assert changed == 3
    assert out["units"][0]["text"] == "CHƯƠNG XV\nMIỄN, GIẢM TRÁCH NHIỆM HÌNH SỰ"
    assert out["units"][1]["text"] == "Khái niệm và ý nghĩa của QĐHP"
    assert out["units"][2]["text"] == "Đối tượng điều chỉnh"


def test_conversion_touches_nothing_but_text():
    data = _vni_doc()
    out, _ = convert_sidecar(data)
    for before, after in zip(data["units"], out["units"]):
        assert after["page"] == before["page"]
        assert after["label"] == before["label"]
        assert after["bbox"] == before["bbox"]
        assert after["type"] == before["type"]
    for key in ("schemaVersion", "title", "source", "addedAt", "sourceFormat",
                "pageCount", "kind"):
        assert out[key] == data[key]


def test_conversion_leaves_unicode_units_alone():
    data = _sidecar([
        _slide("CÁC TRƯỜNG HỢP LOẠI TRỪ TRÁCH NHIỆM HÌNH SỰ", 1),
        _slide("I. Khaùi nieäm chung", 2),
    ], page_count=2)
    out, changed = convert_sidecar(data)
    assert changed == 1
    assert out["units"][0]["text"] == data["units"][0]["text"]
    assert out["units"][1]["text"] == "I. Khái niệm chung"


def test_conversion_output_is_valid():
    out, _ = convert_sidecar(_vni_doc())
    assert validate_sidecar(out) == []


def test_word_count_is_preserved():
    data = _vni_doc()
    out, _ = convert_sidecar(data)
    for before, after in zip(data["units"], out["units"]):
        assert len(after["text"].split()) == len(before["text"].split())


def test_empty_document_is_refused():
    assert convert_sidecar(_sidecar([])) is None


# --- kho walk ----------------------------------------------------------------

@pytest.fixture
def kho(tmp_path):
    root = tmp_path / "GuLibrary-Prod" / "kho"
    (root / "Môn A").mkdir(parents=True)
    return root


def _place(folder: Path, stem: str, data: dict) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{stem}.pdf").write_bytes(b"%PDF-1.4 fake")
    p = folder / f"{stem}.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_dry_run_reports_without_writing(kho):
    p = _place(kho / "Môn A", "deck", _vni_doc())
    before = p.read_text(encoding="utf-8")
    report = vnifix_kho(kho, apply=False)
    assert (report.targets, report.rewritten, report.units_changed) == (1, 1, 3)
    assert p.read_text(encoding="utf-8") == before


def test_apply_rewrites_the_sidecar(kho):
    p = _place(kho / "Môn A", "deck", _vni_doc())
    report = vnifix_kho(kho, apply=True)
    assert report.rewritten == 1
    after = json.loads(p.read_text(encoding="utf-8"))
    assert after["units"][1]["text"] == "Khái niệm và ý nghĩa của QĐHP"
    assert validate_sidecar(after) == []


def test_apply_backs_up_to_its_own_folder(kho):
    """reslide's `_sidecar_backup/` holds the pre-slide originals — untouchable."""
    _place(kho / "Môn A", "deck", _vni_doc())
    archive = kho.with_name(kho.name + "_archive")
    reslide_backup = archive / "_sidecar_backup" / "Môn A" / "deck.json"
    reslide_backup.parent.mkdir(parents=True)
    reslide_backup.write_text('{"keep": "me"}', encoding="utf-8")

    vnifix_kho(kho, apply=True)

    assert json.loads(reslide_backup.read_text(encoding="utf-8")) == {"keep": "me"}
    ours = archive / BACKUP_DIRNAME / "Môn A" / "deck.json"
    assert "MIEÃN" in ours.read_text(encoding="utf-8")


def test_unicode_document_is_left_untouched(kho):
    doc = _sidecar([_slide("CHƯƠNG XV — MIỄN, GIẢM TRÁCH NHIỆM", 1)])
    p = _place(kho / "Môn A", "sach", doc)
    before = p.read_text(encoding="utf-8")
    report = vnifix_kho(kho, apply=True)
    assert report.targets == 0
    assert p.read_text(encoding="utf-8") == before


def test_running_twice_is_a_no_op(kho):
    p = _place(kho / "Môn A", "deck", _vni_doc())
    vnifix_kho(kho, apply=True)
    after_first = p.read_text(encoding="utf-8")
    report = vnifix_kho(kho, apply=True)
    assert report.targets == 0
    assert p.read_text(encoding="utf-8") == after_first


def test_broken_fragments_are_counted_not_hidden(kho):
    """A modifier the PDF reader tore off its own vowel can't be decoded by
    anyone; it must show up in the report rather than pass silently."""
    doc = _sidecar([_slide("c ûa l aät hình söï\ncuûa luaät hình söï", 1)])
    _place(kho / "Môn A", "deck", doc)
    report = vnifix_kho(kho, apply=True)
    assert report.rewritten == 1
    assert report.units_still_vni == 1


# --- NFC: tone marks left as separate combining characters -------------------

def _decomposed(text: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFD", text)


def test_a_document_needing_only_nfc_is_a_target():
    """It carries no VNI at all — but `Bô` + a combining hook never matches a
    query for `Bổ`, so search misses it just as completely."""
    from gu_library_worker.vnifix import needs_text_fix, needs_vni_fix
    doc = _sidecar([_slide(_decomposed("Bổ sung tội Làm giàu bất chính"), 1)])
    assert needs_vni_fix(doc) is False
    assert needs_text_fix(doc) is True


def test_nfc_only_document_is_composed(kho):
    p = _place(kho / "Môn A", "vanban",
               _sidecar([_slide(_decomposed("Bổ sung tội danh"), 1)]))
    report = vnifix_kho(kho, apply=True)
    assert report.rewritten == 1
    after = json.loads(p.read_text(encoding="utf-8"))
    assert after["units"][0]["text"] == "Bổ sung tội danh"


def test_clean_document_is_still_not_a_target(kho):
    """The gate is 'normalizing would change something', so text that is already
    composed and already Unicode is left alone."""
    p = _place(kho / "Môn A", "sach",
               _sidecar([_slide("Bổ sung tội danh theo Bộ luật hình sự", 1)]))
    before = p.read_text(encoding="utf-8")
    report = vnifix_kho(kho, apply=True)
    assert report.targets == 0
    assert p.read_text(encoding="utf-8") == before


def test_word_count_survives_composition(kho):
    doc = _sidecar([_slide(_decomposed("một hai ba bốn năm"), 1)])
    out, _ = convert_sidecar(doc)
    assert len(out["units"][0]["text"].split()) == 5
