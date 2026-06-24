# tests/test_pdf_reader.py
import re
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

# --- Defect 1: running header/footer removal (PDF only) ---

def test_running_header_stripped(make_pdf_blocks):
    header = "CÔNG BÁO/Số 367 + 368/Ngày 01-3-2024"
    pages = [{"header": header, "body": f"Điều {i}. Nội dung của điều thứ {i}."}
             for i in range(1, 5)]
    ext = read_pdf(make_pdf_blocks("cb.pdf", pages))
    joined = " ".join(u.text for u in ext.units)
    assert "CÔNG BÁO" not in joined                       # never injected
    assert not any(u.text.strip() == header for u in ext.units)  # no junk unit
    assert {u.label for u in ext.units if u.type == "dieu"} == \
        {"Điều 1", "Điều 2", "Điều 3", "Điều 4"}          # real articles survive

def test_running_footer_stripped(make_pdf_blocks):
    footer = "Trang chung của bản công báo này"
    pages = [{"body": f"Điều {i}. Nội dung điều.", "footer": footer}
             for i in range(1, 5)]
    ext = read_pdf(make_pdf_blocks("ft.pdf", pages))
    assert all("Trang chung" not in u.text for u in ext.units)
    assert {u.label for u in ext.units if u.type == "dieu"} == \
        {"Điều 1", "Điều 2", "Điều 3", "Điều 4"}

def test_standalone_page_numbers_stripped(make_pdf_blocks):
    pages = [{"header": str(i), "body": f"Điều {i}. Nội dung điều."}
             for i in range(1, 6)]
    ext = read_pdf(make_pdf_blocks("pn.pdf", pages))
    assert not any(re.fullmatch(r"\d+", u.text.strip()) for u in ext.units)
    assert {u.label for u in ext.units if u.type == "dieu"} == \
        {"Điều 1", "Điều 2", "Điều 3", "Điều 4", "Điều 5"}

def test_header_not_injected_into_spanning_article(make_pdf_blocks):
    header = "CÔNG BÁO/Số 367"
    pages = [
        {"header": header, "body": "Điều 5. Quyền sử dụng đất của địa phương"},
        {"header": header, "body": "được quy định chi tiết trong nghị định."},
    ]
    ext = read_pdf(make_pdf_blocks("span.pdf", pages))
    dieu = [u for u in ext.units if u.type == "dieu"]
    assert len(dieu) == 1
    assert "CÔNG BÁO" not in dieu[0].text                 # not injected mid-text
    assert "được quy định chi tiết" in dieu[0].text       # continuation kept

def test_pdf_without_header_keeps_all_text(make_pdf_blocks):
    pages = [
        {"body": "Điều 1. Phạm vi điều chỉnh. Quy định nội dung điều một."},
        {"body": "Điều 2. Giải thích từ ngữ. Quy định nội dung điều hai."},
    ]
    ext = read_pdf(make_pdf_blocks("plain.pdf", pages))
    assert {u.label for u in ext.units if u.type == "dieu"} == {"Điều 1", "Điều 2"}
    joined = " ".join(u.text for u in ext.units)
    assert "nội dung điều một" in joined and "nội dung điều hai" in joined

# --- Defect 2: reference is not an article boundary ---

def test_reference_not_treated_as_article(make_pdf_blocks):
    body = ("Điều 201. Sử dụng đất khu công nghiệp.\n"
            "Điều 201 của Luật này được áp dụng cho trường hợp đặc biệt.")
    ext = read_pdf(make_pdf_blocks("ref.pdf", [{"body": body}]))
    dieu = [u for u in ext.units if u.type == "dieu"]
    assert len(dieu) == 1                                 # not counted twice
    assert dieu[0].label == "Điều 201"
    joined = " ".join(u.text for u in ext.units)
    assert "của Luật này được áp dụng" in joined          # reference text kept

def test_reference_false_positives_out_of_range(make_pdf_blocks):
    body = ("Điều 171. Đất khu kinh tế.\n"
            "Theo quy định tại Điều 53 và Điều 126 của Luật này.\n"
            "Điều 172. Đất sử dụng cho khu công nghệ cao.")
    ext = read_pdf(make_pdf_blocks("range.pdf", [{"body": body}]))
    labels = sorted(u.label for u in ext.units if u.type == "dieu")
    assert labels == ["Điều 171", "Điều 172"]             # 53/126 are references

# --- v0.7.4: header/footer no longer stitched into a page-spanning Khoản ---

def test_spanning_khoan_strips_interleaved_header_footer(make_pdf_blocks):
    header = "CÔNG BÁO/Số 363 + 364/Ngày 01-3-2024"
    pages = [
        {"header": header,
         "body": ("Điều 10. Điều khoản chuyển tiếp\n"
                  "1. Khoản một có nội dung dài bắt đầu ở cuối trang"),
         "footer": "Thời gian ký: 21.03.2024 15:22:01 +07:00\n4"},
        {"header": header,
         "body": "và tiếp tục liền mạch sang trang kế rồi kết thúc tại đây.",
         "footer": "Thời gian ký: 21.03.2024 15:30:11 +07:00\n5"},
    ]
    ext = read_pdf(make_pdf_blocks("span2.pdf", pages))
    khoan = [u for u in ext.units if u.type == "khoan"]
    assert len(khoan) == 1
    txt = khoan[0].text
    assert "CÔNG BÁO" not in txt                       # header not injected
    assert "Thời gian ký" not in txt                   # signature not injected
    assert all(not re.fullmatch(r"\d+", line) for line in txt.split("\n"))  # no page num
    # content stitched across the page break, nothing lost
    assert "Khoản một có nội dung dài" in txt
    assert "tiếp tục liền mạch sang trang kế" in txt

def test_digit_masked_header_detected(make_pdf_blocks):
    # Issue number differs every page; only digits vary. Exact-text matching
    # (v0.7.2) missed this — digit-masked matching must catch it.
    pages = [{"header": f"CÔNG BÁO/Số {360 + i} + {361 + i}/Ngày 01-3-2024",
              "body": f"Điều {i}. Nội dung của điều."} for i in range(1, 5)]
    ext = read_pdf(make_pdf_blocks("vary.pdf", pages))
    assert all("CÔNG BÁO" not in u.text for u in ext.units)
    assert {u.label for u in ext.units if u.type == "dieu"} == \
        {"Điều 1", "Điều 2", "Điều 3", "Điều 4"}

def test_digital_signature_line_stripped(make_pdf_blocks):
    pages = [{"body": f"Điều {i}. Nội dung điều.",
              "footer": f"Thời gian ký: 2{i}.03.2024 15:2{i}:01 +07:00"}
             for i in range(1, 5)]
    ext = read_pdf(make_pdf_blocks("sig.pdf", pages))
    assert all("Thời gian ký" not in u.text for u in ext.units)
    assert {u.label for u in ext.units if u.type == "dieu"} == \
        {"Điều 1", "Điều 2", "Điều 3", "Điều 4"}

# --- v0.7.6: page-1 cover metadata (appears once, repetition can't catch it) ---

def test_cover_page_signature_and_masthead_stripped(make_pdf_blocks):
    page1 = "\n".join([
        "thongtinchinhphu@chinhphu.vn",
        "Cơ quan: VĂN PHÒNG CHÍNH PHỦ",
        "Thời gian ký: 21.03.2024 15:22:01 +07:00",
        "VĂN BẢN QUY PHẠM PHÁP LUẬT",
        "CHỦ TỊCH NƯỚC - QUỐC HỘI",
        "QUỐC HỘI",
        "Luật số: 31/2024/QH15",
        "LUẬT ĐẤT ĐAI",                                       # title: kept
        "Căn cứ Hiến pháp nước Cộng hòa xã hội chủ nghĩa Việt Nam;",  # preamble: kept
        "Điều 1. Phạm vi điều chỉnh",
        "1. Luật này quy định về đất đai.",
    ])
    ext = read_pdf(make_pdf_blocks("dat1.pdf", [{"body": page1}]))
    joined = " ".join(u.text for u in ext.units)
    for junk in ("Thời gian ký", "thongtinchinhphu@chinhphu.vn", "Cơ quan:",
                 "VĂN BẢN QUY PHẠM PHÁP LUẬT", "CHỦ TỊCH NƯỚC", "QUỐC HỘI",
                 "Luật số:"):
        assert junk not in joined, f"cover junk leaked: {junk}"
    # legitimate front matter and articles preserved
    assert "LUẬT ĐẤT ĐAI" in joined
    assert "Căn cứ Hiến pháp" in joined
    assert [u.label for u in ext.units if u.type == "dieu"] == ["Điều 1"]
    khoan = [u for u in ext.units if u.type == "khoan"]
    assert khoan and "Luật này quy định về đất đai" in khoan[0].text

def test_signature_splitting_a_clause_is_rejoined(make_pdf_blocks):
    # file _3 case: the stamp lands in the MIDDLE of điểm a), cutting the clause
    page1 = "\n".join([
        "Điều 5. Quyền của người sử dụng đất",
        "1. Người sử dụng đất có các quyền sau:",
        "a) được cấp giấy chứng nhận quyền sử dụng",
        "Thời gian ký: 21.03.2024 15:22:01 +07:00",
        "đất và tài sản gắn liền với đất;",
    ])
    ext = read_pdf(make_pdf_blocks("dat3.pdf", [{"body": page1}]))
    khoan = [u for u in ext.units if u.type == "khoan"]
    assert len(khoan) == 1
    flat = khoan[0].text.replace("\n", " ")
    assert "Thời gian ký" not in flat
    assert "được cấp giấy chứng nhận quyền sử dụng đất và tài sản gắn liền" in flat

def test_cover_email_line_stripped_and_clause_rejoined(make_pdf_blocks):
    # v0.7.7: the 'Email: <addr>' line of the page-1 signature block (file _3
    # case) lands between Khoản 1 and điểm a) — must be dropped and the clause
    # stitched continuous.
    page1 = "\n".join([
        "Điều 5. Giao đất, cho thuê đất",
        "1. Việc giao đất được quy định như sau:",
        "Email: thongtinchinhphu@chinhphu.vn",
        "a) Thời hạn giao đất không quá năm mươi năm;",
    ])
    ext = read_pdf(make_pdf_blocks("dat3email.pdf", [{"body": page1}]))
    khoan = [u for u in ext.units if u.type == "khoan"]
    assert len(khoan) == 1
    flat = khoan[0].text.replace("\n", " ")
    assert "thongtinchinhphu" not in flat
    assert "Email:" not in flat
    assert "được quy định như sau: a) Thời hạn giao đất" in flat

def test_email_inside_real_sentence_is_kept(make_pdf_blocks):
    # An email embedded in a real sentence (not the signature block) is content.
    page1 = "\n".join([
        "Điều 1. Phạm vi điều chỉnh",
        "1. Mọi liên hệ gửi về abc@toaan.gov.vn trước ngày làm việc.",
    ])
    ext = read_pdf(make_pdf_blocks("ds_email.pdf", [{"body": page1}]))
    joined = " ".join(u.text for u in ext.units)
    assert "abc@toaan.gov.vn" in joined
    assert [u.label for u in ext.units if u.type == "dieu"] == ["Điều 1"]

def test_plain_law_cover_not_stripped(make_pdf_blocks):
    # A law with a normal title + preamble but NO công báo masthead/signature
    # (e.g. Bộ luật Dân sự) must keep everything.
    page1 = "\n".join([
        "BỘ LUẬT DÂN SỰ",
        "Căn cứ Hiến pháp nước Cộng hòa xã hội chủ nghĩa Việt Nam;",
        "Quốc hội ban hành Bộ luật Dân sự.",
        "Điều 1. Phạm vi điều chỉnh",
        "Bộ luật này quy định địa vị pháp lý của cá nhân.",
    ])
    ext = read_pdf(make_pdf_blocks("ds.pdf", [{"body": page1}]))
    joined = " ".join(u.text for u in ext.units)
    assert "BỘ LUẬT DÂN SỰ" in joined
    assert "Căn cứ Hiến pháp" in joined
    assert "Quốc hội ban hành Bộ luật Dân sự" in joined          # not mistaken for masthead
    assert "địa vị pháp lý của cá nhân" in joined
    assert [u.label for u in ext.units if u.type == "dieu"] == ["Điều 1"]
