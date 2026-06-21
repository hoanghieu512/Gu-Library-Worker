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
