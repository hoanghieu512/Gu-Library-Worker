# tests/test_docx_reader.py
from gu_library_worker.readers.docx_reader import read_docx

def test_legal_docx_yields_dieu_and_khoan(make_docx):
    path = make_docx("law.docx", [
        "Chương I QUY ĐỊNH CHUNG",
        "Điều 1. Phạm vi điều chỉnh",
        "Luật này quy định về công chứng.",
        "Điều 2. Giải thích từ ngữ",
        "1. Công chứng là việc chứng nhận.",
        "2. Công chứng viên là người đủ điều kiện.",
    ])
    ext = read_docx(path)
    assert ext.kind == "legal"
    labels = [(u.type, u.label) for u in ext.units]
    assert ("dieu", "Điều 1") in labels
    assert ("dieu", "Điều 2") in labels
    assert ("khoan", "Khoản 1") in labels
    assert all(u.page == 0 for u in ext.units)  # not anchored yet

def test_prose_docx_degrades_to_paragraphs(make_docx):
    path = make_docx("notes.docx", [
        "Giới thiệu môn học",
        "Đây là đoạn mở đầu của giáo trình.",
        "Đoạn thứ hai tiếp tục nội dung.",
    ])
    ext = read_docx(path)
    assert ext.kind == "prose"
    assert all(u.type in {"paragraph", "heading"} for u in ext.units)
    joined = " ".join(u.text for u in ext.units)
    assert "đoạn mở đầu" in joined

def test_docx_units_have_no_bbox(make_docx):
    # Word origin has no PDF coordinates at extract time -> bbox left empty.
    path = make_docx("law.docx", ["Điều 1. Phạm vi", "Nội dung điều một."])
    ext = read_docx(path)
    assert all(u.bbox is None for u in ext.units)

def test_docx_output_unchanged_regression(make_docx):
    # Regression guard for v0.7.2: the PDF-reader fixes (header strip + stricter
    # Điều regex) must NOT change DOCX output. Locks the exact units.
    ext = read_docx(make_docx("law.docx", [
        "Chương I QUY ĐỊNH CHUNG",
        "Điều 1. Phạm vi điều chỉnh",
        "Việc áp dụng Điều 1 của Luật này do Chính phủ quy định.",
        "Điều 2. Giải thích từ ngữ",
        "1. Công chứng là việc chứng nhận.",
    ]))
    summary = [(u.type, u.label, u.page, u.bbox) for u in ext.units]
    assert summary == [
        ("heading", "Chương I", 0, None),
        ("dieu", "Điều 1", 0, None),     # reference paragraph stays as its continuation
        ("dieu", "Điều 2", 0, None),
        ("khoan", "Khoản 1", 0, None),
    ]
    # the reference sentence is preserved (folded into Điều 1), never lost
    dieu1 = next(u for u in ext.units if u.label == "Điều 1")
    assert "Điều 1 của Luật này" in dieu1.text
