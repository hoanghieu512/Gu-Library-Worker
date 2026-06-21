# tests/test_legal.py
from gu_library_worker.readers.base import Line
from gu_library_worker.legal import has_legal_structure, parse_legal

def _lines(texts):
    return [Line(text=t, page=1) for t in texts]

def test_detects_legal():
    assert has_legal_structure(_lines(["Chương I", "Điều 1. Phạm vi"]))
    assert not has_legal_structure(_lines(["Mở đầu", "Một đoạn văn xuôi."]))

def test_article_without_clauses_is_one_dieu():
    units = parse_legal(_lines([
        "Chương I QUY ĐỊNH CHUNG",
        "Điều 1. Phạm vi điều chỉnh",
        "Luật này quy định về công chứng.",
    ]))
    types = [(u.type, u.label) for u in units]
    assert ("heading", "Chương I") in types
    dieu = [u for u in units if u.type == "dieu"]
    assert len(dieu) == 1 and dieu[0].label == "Điều 1"
    assert dieu[0].path == ["Chương I"]
    assert "Phạm vi điều chỉnh" in dieu[0].text

def test_article_with_clauses_splits_into_khoan():
    units = parse_legal(_lines([
        "Điều 2. Giải thích từ ngữ",
        "Trong Luật này, các từ ngữ được hiểu như sau:",
        "1. Công chứng là việc công chứng viên chứng nhận.",
        "2. Công chứng viên là người đủ điều kiện.",
    ]))
    dieu = [u for u in units if u.type == "dieu"]
    khoan = [u for u in units if u.type == "khoan"]
    assert len(dieu) == 1 and dieu[0].label == "Điều 2"
    assert [k.label for k in khoan] == ["Khoản 1", "Khoản 2"]
    assert khoan[0].path == ["Điều 2"]
    assert "Công chứng là việc" in khoan[0].text
    # lead text stays on the dieu, clause text does not duplicate onto it
    assert "Công chứng là việc" not in dieu[0].text

def test_no_text_lost_total_chars():
    src = ["Điều 1. Tiêu đề", "1. Một.", "2. Hai."]
    units = parse_legal(_lines(src))
    joined = " ".join(u.text for u in units)
    for token in ["Tiêu đề", "Một", "Hai"]:
        assert token in joined

def test_second_chapter_resets_ancestors():
    units = parse_legal(_lines([
        "Chương I QUY ĐỊNH CHUNG",
        "Điều 1. Phạm vi",
        "Chương II HIỆU LỰC",
        "Điều 2. Hiệu lực thi hành",
    ]))
    dieu = {u.label: u for u in units if u.type == "dieu"}
    assert dieu["Điều 1"].path == ["Chương I"]
    assert dieu["Điều 2"].path == ["Chương II"]  # not ["Chương I"]
