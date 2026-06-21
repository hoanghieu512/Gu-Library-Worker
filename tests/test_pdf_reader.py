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
