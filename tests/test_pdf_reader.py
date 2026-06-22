# tests/test_pdf_reader.py
from gu_library_worker.readers.pdf_reader import read_pdf

def test_legal_pdf_extracts_dieu(make_pdf):
    path = make_pdf("law.pdf", [
        "Điều 1. Phạm vi điều chỉnh\nLuật này quy định về công chứng.",
        "Điều 2. Giải thích từ ngữ\n1. Công chứng là việc chứng nhận.",
    ])
    ext = read_pdf(path)
    assert ext.kind == "legal"
    dieu = [u for u in ext.units if u.type == "dieu"]
    assert {u.label for u in dieu} == {"Điều 1", "Điều 2"}
    # page anchors come from the real PDF pages
    assert dieu[0].page == 1
    assert dieu[1].page == 2

def test_prose_pdf_degrades_without_losing_text(make_pdf):
    path = make_pdf("doc.pdf", [
        "Giới thiệu chung về môn học.\nĐoạn nội dung đầu tiên.",
        "Trang hai có thêm nội dung quan trọng.",
    ])
    ext = read_pdf(path)
    assert ext.kind == "prose"
    assert all(u.type == "paragraph" for u in ext.units)
    joined = " ".join(u.text for u in ext.units)
    assert "Đoạn nội dung đầu tiên" in joined
    assert "Trang hai" in joined
    # page anchors preserved
    assert any(u.page == 2 for u in ext.units)

def _valid_top_left_rect(bbox):
    assert bbox is not None and len(bbox) == 4
    x0, y0, x1, y1 = bbox
    assert all(isinstance(c, float) for c in bbox)
    assert x0 < x1 and y0 < y1  # top-left origin, y grows downward

def test_legal_pdf_units_carry_bbox(make_pdf):
    path = make_pdf("law.pdf", [
        "Điều 1. Phạm vi điều chỉnh\nLuật này quy định về công chứng.",
        "Điều 2. Giải thích từ ngữ\n1. Công chứng là việc chứng nhận.",
    ])
    ext = read_pdf(path)
    assert ext.units                       # has units
    for u in ext.units:
        _valid_top_left_rect(u.bbox)       # every PDF unit gets a bbox

def test_prose_pdf_units_carry_bbox(make_pdf):
    path = make_pdf("doc.pdf", ["Một đoạn văn xuôi không có cấu trúc điều khoản."])
    ext = read_pdf(path)
    assert ext.kind == "prose"
    for u in ext.units:
        _valid_top_left_rect(u.bbox)
