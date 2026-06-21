# tests/test_pages.py
from gu_library_worker.schema import Unit
from gu_library_worker.pages import anchor_pages, page_count

def test_page_count(make_pdf):
    path = make_pdf("x.pdf", ["a", "b", "c"])
    assert page_count(path) == 3

def test_anchor_assigns_pages_by_text_search(make_pdf):
    pdf = make_pdf("x.pdf", [
        "Điều 1. Phạm vi điều chỉnh nằm ở trang một.",
        "Điều 2. Giải thích từ ngữ nằm ở trang hai.",
    ])
    units = [
        Unit(type="dieu", label="Điều 1", path=[], text="Điều 1. Phạm vi điều chỉnh", page=0),
        Unit(type="dieu", label="Điều 2", path=[], text="Điều 2. Giải thích từ ngữ", page=0),
    ]
    anchor_pages(units, pdf)
    assert units[0].page == 1
    assert units[1].page == 2

def test_anchor_falls_back_to_floor_when_not_found(make_pdf):
    pdf = make_pdf("x.pdf", ["chỉ một trang nội dung"])
    units = [Unit(type="paragraph", label="", path=[], text="văn bản không có trong pdf", page=0)]
    anchor_pages(units, pdf)
    assert units[0].page == 1  # fallback never below 1
