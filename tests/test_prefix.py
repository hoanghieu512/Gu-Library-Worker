import logging
from gu_library_worker.prefix import parse_prefix, Parsed

def test_share_prefix():
    r = parse_prefix("[Tố tụng Hình sự] bai-giang.pdf")
    assert r == Parsed(subject="Tố tụng Hình sự", clean_name="bai-giang.pdf", source="share")

def test_unclassified_prefix():
    r = parse_prefix("[Chưa phân loại] x.docx")
    assert r.subject == "Chưa phân loại"
    assert r.source == "share"
    assert r.clean_name == "x.docx"

def test_no_prefix_is_watch_and_unclassified():
    r = parse_prefix("ngau-nhien.pdf")
    assert r.subject == "Chưa phân loại"
    assert r.source == "watch"
    assert r.clean_name == "ngau-nhien.pdf"

def test_prefix_with_extra_spaces():
    r = parse_prefix("[Luật Công chứng]   spaced.pdf")
    assert r.subject == "Luật Công chứng"
    assert r.clean_name == "spaced.pdf"

# --- v0.9.0: nested prefix ---

def test_nested_two_levels():
    r = parse_prefix("[Luật Đất đai][Bài giảng] file.pdf")
    assert r.subject == "Luật Đất đai/Bài giảng"   # split into folders downstream
    assert r.clean_name == "file.pdf"
    assert r.source == "share"

def test_nested_three_levels():
    r = parse_prefix("[Môn][Bài giảng][Chương 1] x.pdf")
    assert r.subject == "Môn/Bài giảng/Chương 1"
    assert r.clean_name == "x.pdf"

def test_unsafe_segments_routed_to_unclassified(caplog):
    for name in ("[Môn][..] x.pdf", "[Môn][] x.pdf", "[Môn][_abc] x.pdf",
                 "[a/b][c] x.pdf", "[Môn][.] x.pdf"):
        with caplog.at_level(logging.WARNING, logger="gu_library_worker"):
            r = parse_prefix(name)
        assert r.subject == "Chưa phân loại"       # blocked safely, stays in kho
        assert r.clean_name == "x.pdf"
    assert any("unsafe subject prefix" in rec.message for rec in caplog.records)

def test_nested_under_unclassified_flattens(caplog):
    with caplog.at_level(logging.WARNING, logger="gu_library_worker"):
        r = parse_prefix("[Chưa phân loại][Con] x.pdf")
    assert r.subject == "Chưa phân loại"           # no sub-structure in this area
    assert r.clean_name == "x.pdf"
    assert any("nested prefix under" in rec.message for rec in caplog.records)
