import json
from pathlib import Path

import pytest

from gu_library_worker.reslide import (
    is_degraded_slide_sidecar,
    regroup_slide_units,
    reslide_kho,
)
from gu_library_worker.schema import validate_sidecar


def _sidecar(units, *, kind="prose", source_format="pptx", page_count=3):
    return {
        "schemaVersion": 1,
        "title": "Bài giảng",
        "source": "share",
        "addedAt": "2026-07-02T19:02:51+07:00",
        "sourceFormat": source_format,
        "pageCount": page_count,
        "kind": kind,
        "units": units,
    }


def _para(text, page, bbox=(10.0, 20.0, 30.0, 40.0)):
    u = {"type": "paragraph", "label": "", "path": [], "text": text, "page": page}
    if bbox is not None:
        u["bbox"] = list(bbox)
    return u


def _degraded():
    return _sidecar([
        _para("Tiêu đề bài", 1, (10, 10, 100, 30)),
        _para("Giảng viên", 1, (10, 40, 120, 60)),
        _para("Nội dung hai", 2, (15, 20, 200, 50)),
        _para("Kết luận", 3, (5, 5, 90, 25)),
    ])


# --- detection -------------------------------------------------------------

def test_detects_legacy_ppt_sidecar():
    assert is_degraded_slide_sidecar(_degraded()) is True


def test_legal_sidecar_is_not_a_target():
    """A .ppt whose PDF parsed as law keeps its Điều/Khoản labels — never touch it."""
    data = _degraded()
    data["kind"] = "legal"
    data["units"][0].update(type="dieu", label="Điều 1")
    assert is_degraded_slide_sidecar(data) is False


def test_already_slide_sidecar_is_not_a_target():
    data = _degraded()
    data["kind"] = "slide"
    for u in data["units"]:
        u["type"], u["label"] = "slide", "Slide 1"
    assert is_degraded_slide_sidecar(data) is False


def test_pdf_origin_prose_is_not_a_target():
    """A real PDF book degrades to paragraphs legitimately; it has no slides."""
    data = _degraded()
    data["sourceFormat"] = "pdf"
    assert is_degraded_slide_sidecar(data) is False


def test_native_pptx_without_bbox_is_not_a_target():
    """Only the PDF reader emits bbox; no bbox means it never went that path."""
    data = _sidecar([_para("x", 1, bbox=None), _para("y", 2, bbox=None)])
    assert is_degraded_slide_sidecar(data) is False


# --- regrouping ------------------------------------------------------------

def test_regroup_makes_one_slide_unit_per_page_with_text():
    out = regroup_slide_units(_degraded())
    assert out is not None
    assert out["kind"] == "slide"
    assert [u["page"] for u in out["units"]] == [1, 2, 3]
    assert [u["type"] for u in out["units"]] == ["slide"] * 3
    assert [u["label"] for u in out["units"]] == ["Slide 1", "Slide 2", "Slide 3"]


def test_regroup_keeps_every_page_anchor_unchanged():
    """The hard constraint: page must still point at the same PDF page."""
    data = _degraded()
    before = {u["page"] for u in data["units"]}
    out = regroup_slide_units(data)
    assert {u["page"] for u in out["units"]} == before


def test_regroup_loses_no_text():
    data = _degraded()
    out = regroup_slide_units(data)
    joined = "\n".join(u["text"] for u in out["units"])
    for u in data["units"]:
        assert u["text"] in joined


def test_regroup_unions_bboxes_of_the_page():
    out = regroup_slide_units(_degraded())
    assert out["units"][0]["bbox"] == [10.0, 10.0, 120.0, 60.0]


def test_regroup_omits_bbox_when_no_unit_on_the_page_had_one():
    data = _sidecar([_para("a", 1, bbox=None), _para("b", 1)])
    data["units"][1].pop("bbox")
    out = regroup_slide_units(data)
    assert "bbox" not in out["units"][0]


def test_regroup_output_passes_validate_sidecar():
    assert validate_sidecar(regroup_slide_units(_degraded())) == []


def test_regroup_preserves_document_metadata():
    data = _degraded()
    out = regroup_slide_units(data)
    for key in ("schemaVersion", "title", "source", "addedAt", "sourceFormat", "pageCount"):
        assert out[key] == data[key]


def test_regroup_refuses_when_a_page_exceeds_pagecount():
    """A page beyond the PDF would make the app jump nowhere — refuse, don't guess."""
    data = _sidecar([_para("a", 1), _para("b", 9)], page_count=3)
    assert regroup_slide_units(data) is None


def test_regroup_refuses_when_every_unit_is_blank():
    data = _sidecar([_para("   ", 1), _para("", 2)])
    assert regroup_slide_units(data) is None


def test_regroup_skips_pages_whose_units_are_all_blank():
    data = _sidecar([_para("thật", 1), _para("   ", 2)])
    out = regroup_slide_units(data)
    assert [u["page"] for u in out["units"]] == [1]


# --- kho walk --------------------------------------------------------------

@pytest.fixture
def kho(tmp_path):
    root = tmp_path / "GuLibrary" / "kho"
    (root / "Môn A").mkdir(parents=True)
    return root


def _place(folder: Path, stem: str, data: dict) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{stem}.pdf").write_bytes(b"%PDF-1.4 fake")
    p = folder / f"{stem}.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_dry_run_reports_targets_without_writing(kho):
    p = _place(kho / "Môn A", "deck", _degraded())
    before = p.read_text(encoding="utf-8")
    report = reslide_kho(kho, apply=False)
    assert report.rewritten == 1
    assert p.read_text(encoding="utf-8") == before


def test_apply_rewrites_the_sidecar(kho):
    p = _place(kho / "Môn A", "deck", _degraded())
    report = reslide_kho(kho, apply=True)
    assert report.rewritten == 1
    after = json.loads(p.read_text(encoding="utf-8"))
    assert after["kind"] == "slide"
    assert after["units"][0]["label"] == "Slide 1"
    assert validate_sidecar(after) == []


def test_apply_backs_up_the_old_sidecar_outside_the_kho(kho):
    _place(kho / "Môn A", "deck", _degraded())
    reslide_kho(kho, apply=True)
    backup = kho.with_name(kho.name + "_archive") / "_sidecar_backup" / "Môn A" / "deck.json"
    assert backup.exists()
    assert json.loads(backup.read_text(encoding="utf-8"))["kind"] == "prose"


def test_walk_ignores_non_document_json(kho):
    (kho / "Môn A" / "_mon.json").write_text("{}", encoding="utf-8")
    (kho / "_reading-abc.json").write_text("{}", encoding="utf-8")
    report = reslide_kho(kho, apply=True)
    assert report.rewritten == 0
    assert report.targets == 0


def test_walk_ignores_syncthing_and_worker_folders(kho):
    for folder in (".stversions", "_inbox", "_print"):
        _place(kho / folder, "deck", _degraded())
    report = reslide_kho(kho, apply=True)
    assert report.targets == 0


def test_walk_leaves_untargeted_documents_alone(kho):
    legal = _degraded()
    legal["kind"] = "legal"
    p = _place(kho / "Môn A", "luat", legal)
    before = p.read_text(encoding="utf-8")
    report = reslide_kho(kho, apply=True)
    assert report.rewritten == 0
    assert p.read_text(encoding="utf-8") == before


def test_unsafe_sidecar_is_skipped_not_rewritten(kho):
    data = _sidecar([_para("a", 1), _para("b", 99)], page_count=3)
    p = _place(kho / "Môn A", "deck", data)
    before = p.read_text(encoding="utf-8")
    report = reslide_kho(kho, apply=True)
    assert report.rewritten == 0
    assert report.skipped_unsafe == 1
    assert p.read_text(encoding="utf-8") == before
