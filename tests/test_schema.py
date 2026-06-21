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
