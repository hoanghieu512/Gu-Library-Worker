# tests/test_smoke_filter.py
# Bug 2: the smoke sidecar scan must skip folder metadata (_mon.json) and only
# validate real document sidecars. These tests run unconditionally (no env gate,
# no LibreOffice) by calling the extracted helper directly.
import json
import pytest
from gu_library_worker.schema import to_sidecar, Document, Unit
from test_smoke_real import validate_document_sidecars

def _write_sidecar(folder, stem, units):
    (folder / f"{stem}.pdf").write_bytes(b"%PDF-1.4\n")
    doc = Document(title=stem, source="share", sourceFormat="pdf", kind="legal",
                   addedAt="2026-06-22T10:00:00+07:00", pageCount=1, units=units)
    (folder / f"{stem}.json").write_text(
        json.dumps(to_sidecar(doc), ensure_ascii=False), encoding="utf-8")

def test_skips_mon_json_and_validates_real_sidecar(tmp_path):
    mon = tmp_path / "Luật Công chứng"
    mon.mkdir()
    # folder metadata: no schemaVersion, no sibling pdf -> must be skipped
    (mon / "_mon.json").write_text(json.dumps({"color": "#75420E", "order": 1}),
                                   encoding="utf-8")
    _write_sidecar(mon, "law", [Unit("dieu", "Điều 1", ["Chương I"], "Nội dung", 1)])

    checked = validate_document_sidecars(tmp_path)   # no KeyError on _mon.json
    assert checked == 1

def test_ignores_inbox_and_print(tmp_path):
    for special in ("_inbox", "_print"):
        d = tmp_path / special
        d.mkdir()
        (d / "stray.pdf").write_bytes(b"%PDF-1.4\n")
        (d / "stray.json").write_text(json.dumps({"nope": True}), encoding="utf-8")
    assert validate_document_sidecars(tmp_path) == 0

def test_skips_stversions_backups(tmp_path):
    # Syncthing M8 versioning keeps old-schema sidecars (no schemaVersion) under
    # .stversions/ at the share root, mirroring the subject subtree. The scan
    # must skip them — even though the versioned .json has a versioned .pdf
    # sibling (so the sibling-pdf check alone would NOT save us).
    versioned = tmp_path / ".stversions" / "Aa Dân sự"
    versioned.mkdir(parents=True)
    (versioned / "giao-trinh~20260621-082220.pdf").write_bytes(b"%PDF-1.4\n")
    (versioned / "giao-trinh~20260621-082220.json").write_text(
        json.dumps({"name": "giao-trinh", "pages": 12, "structure": []}),  # old schema
        encoding="utf-8")

    # a real, current sidecar living outside .stversions
    mon = tmp_path / "Aa Dân sự"
    mon.mkdir()
    _write_sidecar(mon, "giao-trinh", [Unit("paragraph", "", [], "Nội dung", 1)])

    checked = validate_document_sidecars(tmp_path)  # no KeyError on the backup
    assert checked == 1

def test_still_catches_empty_text_sidecar(tmp_path):
    mon = tmp_path / "Môn"
    mon.mkdir()
    (mon / "_mon.json").write_text(json.dumps({"color": "#553B08"}), encoding="utf-8")
    # a real document sidecar with an empty-text unit must still fail
    bad = mon / "bad.json"
    (mon / "bad.pdf").write_bytes(b"%PDF-1.4\n")
    bad.write_text(json.dumps({
        "schemaVersion": 1, "title": "bad", "source": "share",
        "addedAt": "x", "sourceFormat": "pdf", "pageCount": 1, "kind": "prose",
        "units": [{"type": "paragraph", "label": "", "path": [], "text": "  ", "page": 1}],
    }, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(AssertionError):
        validate_document_sidecars(tmp_path)
