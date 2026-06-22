# tests/test_pptx_reader.py
from gu_library_worker.readers.pptx_reader import read_pptx

def test_one_unit_per_slide_with_page_anchor(make_pptx):
    path = make_pptx("deck.pptx", ["Slide một nội dung", "Slide hai nội dung", "Slide ba"])
    ext = read_pptx(path)
    assert ext.kind == "slide"
    assert len(ext.units) == 3
    assert [u.label for u in ext.units] == ["Slide 1", "Slide 2", "Slide 3"]
    assert [u.page for u in ext.units] == [1, 2, 3]
    assert all(u.type == "slide" and u.path == [] for u in ext.units)
    assert "Slide một" in ext.units[0].text

def test_empty_slide_keeps_unit_with_placeholder_text(make_pptx):
    path = make_pptx("deck.pptx", [""])
    ext = read_pptx(path)
    assert len(ext.units) == 1
    assert ext.units[0].text  # never empty

def test_pptx_units_have_no_bbox(make_pptx):
    # Slide origin has no PDF coordinates at extract time -> bbox left empty.
    path = make_pptx("deck.pptx", ["A", "B"])
    ext = read_pptx(path)
    assert all(u.bbox is None for u in ext.units)

def test_pptx_output_unchanged_regression(make_pptx):
    # Regression guard for v0.7.2: PDF-reader fixes must not change PPTX output.
    ext = read_pptx(make_pptx("d.pptx", ["Nội dung A", "Nội dung B"]))
    assert [(u.type, u.label, u.page, u.path, u.bbox) for u in ext.units] == [
        ("slide", "Slide 1", 1, [], None),
        ("slide", "Slide 2", 2, [], None),
    ]
