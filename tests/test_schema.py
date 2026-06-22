from gu_library_worker.schema import (
    Unit, Document, to_sidecar, validate_sidecar, SCHEMA_VERSION,
)

def _doc():
    return Document(
        title="Luật X", source="share", sourceFormat="docx", kind="legal",
        addedAt="2026-06-21T10:30:00+07:00", pageCount=3,
        units=[Unit(type="dieu", label="Điều 1", path=["Chương I"], text="Nội dung", page=1)],
    )

def test_to_sidecar_shape():
    d = to_sidecar(_doc())
    assert d["schemaVersion"] == SCHEMA_VERSION
    assert d["title"] == "Luật X"
    assert d["units"][0] == {
        "type": "dieu", "label": "Điều 1", "path": ["Chương I"],
        "text": "Nội dung", "page": 1,
    }

def test_validate_accepts_good():
    assert validate_sidecar(to_sidecar(_doc())) == []

def test_validate_flags_missing_field():
    bad = to_sidecar(_doc())
    del bad["pageCount"]
    errors = validate_sidecar(bad)
    assert any("pageCount" in e for e in errors)

def test_validate_flags_bad_unit_type_and_empty_text():
    bad = to_sidecar(_doc())
    bad["units"][0]["type"] = "nonsense"
    bad["units"][0]["text"] = ""
    errors = validate_sidecar(bad)
    assert any("type" in e for e in errors)
    assert any("text" in e for e in errors)

def test_validate_flags_non_positive_page():
    bad = to_sidecar(_doc())
    bad["units"][0]["page"] = 0
    assert any("page" in e for e in validate_sidecar(bad))

def test_validate_rejects_bool_for_int_fields():
    bad = to_sidecar(_doc())
    bad["pageCount"] = True          # bool subclasses int; must be rejected
    assert any("pageCount" in e for e in validate_sidecar(bad))
    bad2 = to_sidecar(_doc())
    bad2["units"][0]["page"] = True
    assert any("page" in e for e in validate_sidecar(bad2))

def test_to_sidecar_omits_bbox_when_absent():
    d = to_sidecar(_doc())
    assert "bbox" not in d["units"][0]   # optional field, omitted when None

def test_to_sidecar_includes_bbox_when_present():
    doc = _doc()
    doc.units[0].bbox = [10.0, 20.0, 30.0, 40.0]
    d = to_sidecar(doc)
    assert d["units"][0]["bbox"] == [10.0, 20.0, 30.0, 40.0]

def test_validate_accepts_unit_with_valid_bbox():
    doc = _doc()
    doc.units[0].bbox = [1.0, 2.0, 3.0, 4.0]
    assert validate_sidecar(to_sidecar(doc)) == []

def test_validate_accepts_unit_without_bbox():
    assert validate_sidecar(to_sidecar(_doc())) == []   # absence is valid

def test_validate_flags_bad_bbox():
    bad = to_sidecar(_doc())
    bad["units"][0]["bbox"] = [1.0, 2.0, 3.0]   # only 3 numbers
    assert any("bbox" in e for e in validate_sidecar(bad))
    bad2 = to_sidecar(_doc())
    bad2["units"][0]["bbox"] = "nope"           # not a list
    assert any("bbox" in e for e in validate_sidecar(bad2))
    bad3 = to_sidecar(_doc())
    bad3["units"][0]["bbox"] = [1.0, 2.0, 3.0, "x"]   # non-number element
    assert any("bbox" in e for e in validate_sidecar(bad3))
