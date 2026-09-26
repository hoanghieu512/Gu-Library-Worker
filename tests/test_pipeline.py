# tests/test_pipeline.py
import shutil
from pathlib import Path
from gu_library_worker.pipeline import process_one_file, Prepared
from gu_library_worker.schema import validate_sidecar

def _fake_convert(src, outdir, **kw):
    # for non-pdf, pretend LibreOffice rendered a 1-page pdf with the text
    import fitz
    out = outdir / (src.stem + ".pdf")
    doc = fitz.open(); page = doc.new_page()
    page.insert_text((72, 72), "Điều 1. Phạm vi điều chỉnh", fontsize=12)
    doc.save(out); doc.close()
    return out

def test_docx_pipeline_produces_valid_sidecar(make_docx, tmp_path):
    src = make_docx("[Luật X] luat.docx", [
        "Điều 1. Phạm vi điều chỉnh",
        "Luật này quy định về công chứng.",
    ])
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    assert isinstance(prepared, Prepared)
    assert prepared.subject == "Luật X"
    assert prepared.clean_name == "luat.docx"
    assert prepared.sidecar["sourceFormat"] == "docx"
    assert prepared.sidecar["source"] == "share"
    assert prepared.sidecar["kind"] == "legal"
    assert prepared.sidecar["pageCount"] >= 1
    assert prepared.sidecar["addedAt"].endswith("+07:00")
    assert validate_sidecar(prepared.sidecar) == []

def test_pdf_origin_keeps_original_as_canonical(make_pdf, tmp_path):
    src = make_pdf("[Luật Y] vb.pdf", ["Điều 1. Nội dung trang một."])
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    assert prepared.sidecar["sourceFormat"] == "pdf"
    # canonical pdf is the original bytes (no reconvert), and NOT normalized
    assert prepared.canonical_pdf.read_bytes() == src.read_bytes()
    assert prepared.normalized is False

def _heavy_scan(path, pages=1, img_w=500):
    # small page + threshold-crossing image (150pt page, 500px -> 240 dpi) = fast
    import fitz
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page(width=150, height=200)
        pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, img_w, round(img_w * 200 / 150)))
        pm.set_rect(pm.irect, (235, 235, 235))
        page.insert_image(page.rect, pixmap=pm)
    doc.save(path); doc.close()
    return path

def _max_img_width(pdf):
    import fitz
    with fitz.open(pdf) as d:
        return max(img[2] for page in d for img in page.get_images(full=True))

def test_heavy_image_pdf_is_normalized(tmp_path):
    src = _heavy_scan(tmp_path / "[Môn] scan.pdf", pages=2, img_w=500)
    src_w = _max_img_width(src)
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    assert prepared.normalized is True
    assert prepared.archive_original is True                    # heavy original archived
    assert prepared.canonical_pdf != src                       # a new, lighter file
    assert _max_img_width(prepared.canonical_pdf) < src_w      # fewer pixels to decode
    assert prepared.sidecar["pageCount"] == 2                  # sidecar matches kho copy
    assert validate_sidecar(prepared.sidecar) == []

def test_legacy_doc_marked_for_archive(tmp_path):
    src = tmp_path / "[Luật] old.doc"; src.write_bytes(b"ole-junk")
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    assert prepared.sidecar["sourceFormat"] == "docx"   # legacy .doc -> docx enum
    assert prepared.normalized is False                 # not a re-raster
    assert prepared.archive_original is True            # source preserved, not deleted

def test_legacy_ppt_marked_for_archive(tmp_path):
    src = tmp_path / "[Môn] deck.ppt"; src.write_bytes(b"ole-junk")
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    assert prepared.archive_original is True

def test_docx_not_archived(make_docx, tmp_path):
    src = make_docx("[Luật X] luat.docx", ["Điều 1. Phạm vi điều chỉnh"])
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    assert prepared.archive_original is False           # OOXML source deleted as before

def _jpeg(path, w, h):
    import fitz
    pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, w, h)); pm.set_rect(pm.irect, (210, 190, 170))
    path.write_bytes(pm.tobytes("jpeg", jpg_quality=88)); return path

def test_image_becomes_single_page_pdf_sidecar(tmp_path):
    from gu_library_worker.readers.pdf_reader import IMAGE_PAGE_MARKER
    import fitz
    src = _jpeg(tmp_path / "[Môn] photo.jpg", 700, 1000)     # portrait, light
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    assert prepared.normalized is False                     # image source not archived
    assert prepared.archive_original is False               # consumed source -> deleted
    assert prepared.sidecar["sourceFormat"] == "pdf"
    assert prepared.sidecar["pageCount"] == 1
    assert prepared.sidecar["units"] and IMAGE_PAGE_MARKER in prepared.sidecar["units"][0]["text"]
    assert validate_sidecar(prepared.sidecar) == []
    with fitz.open(prepared.canonical_pdf) as d:
        assert d[0].rect.height > d[0].rect.width           # portrait page

def test_landscape_image_gives_landscape_pdf(tmp_path):
    import fitz
    src = _jpeg(tmp_path / "[Môn] wide.jpg", 1600, 900)      # double-page / landscape
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    with fitz.open(prepared.canonical_pdf) as d:
        assert d[0].rect.width > d[0].rect.height           # NOT forced portrait

def test_heavy_image_lightened(tmp_path):
    import fitz
    src = _jpeg(tmp_path / "[Môn] big.jpg", 2600, 1700)      # high-res -> heavy
    src_w = 2600
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    with fitz.open(prepared.canonical_pdf) as d:
        embedded_w = d[0].get_images(full=True)[0][2]
    assert embedded_w < src_w                               # re-rastered lighter (150dpi)
    assert prepared.normalized is False                     # still not archived (image)
    assert prepared.sidecar["pageCount"] == 1

def test_light_scan_pdf_passthrough(tmp_path):
    # a zero-text scan that is already low-res -> not heavy -> not re-rastered
    src = _heavy_scan(tmp_path / "[Môn] light.pdf", pages=1, img_w=150)   # ~72 dpi
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    assert prepared.normalized is False
    assert prepared.canonical_pdf == src                       # untouched


def _render_pdf(out, pages):
    """Render real (Unicode-safe) text pages, the way LibreOffice would."""
    import html as html_mod
    import fitz
    mb = fitz.paper_rect("a4")
    writer = fitz.DocumentWriter(str(out))
    for body in pages:
        story = fitz.Story(html=f"<p>{html_mod.escape(body)}</p>")
        dev = writer.begin_page(mb)
        story.place(mb + (36, 36, -36, -36))
        story.draw(dev, None)
        writer.end_page()
    writer.close()
    return out


def _convert_to_prose_pages(src, outdir, **kw):
    """Stand-in for LibreOffice rendering a deck: plain text, one block per page."""
    return _render_pdf(outdir / (src.stem + ".pdf"),
                       ["Mở đầu bài giảng", "Nội dung chính", "Tổng kết"])


def _convert_to_legal_pages(src, outdir, **kw):
    """Stand-in for a deck that quotes law: the PDF reader finds Điều/Khoản."""
    return _render_pdf(outdir / (src.stem + ".pdf"), [
        "Điều 1. Phạm vi điều chỉnh\nLuật này quy định về tội phạm.",
        "Điều 2. Giải thích từ ngữ\nTrong Luật này, các từ ngữ dưới đây được hiểu như sau.",
    ])


def test_legacy_ppt_gets_slide_structure_not_bare_paragraphs(tmp_path):
    """v0.14.0: a .ppt no longer lands in the kho as unlabelled text blocks."""
    src = tmp_path / "[Hình sự][Slide] bai 1.ppt"
    src.write_bytes(b"fake ole")
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w",
                                convert_fn=_convert_to_prose_pages)
    sidecar = prepared.sidecar
    assert sidecar["sourceFormat"] == "pptx"
    assert sidecar["kind"] == "slide"
    assert [u["type"] for u in sidecar["units"]] == ["slide"] * 3
    assert [u["label"] for u in sidecar["units"]] == ["Slide 1", "Slide 2", "Slide 3"]
    assert [u["page"] for u in sidecar["units"]] == [1, 2, 3]
    assert validate_sidecar(sidecar) == []
    assert prepared.archive_original is True  # source still preserved


def test_legacy_ppt_that_parses_as_law_keeps_its_legal_units(tmp_path):
    """A deck quoting law has better structure than slides — don't flatten it."""
    src = tmp_path / "[Hình sự][Slide] blhs.ppt"
    src.write_bytes(b"fake ole")
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w",
                                convert_fn=_convert_to_legal_pages)
    assert prepared.sidecar["kind"] == "legal"
    assert prepared.sidecar["units"][0]["type"] == "dieu"


def test_legacy_doc_is_untouched_by_the_slide_repair(tmp_path):
    src = tmp_path / "[Hình sự][VBPL] luat.doc"
    src.write_bytes(b"fake ole")
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w",
                                convert_fn=_convert_to_prose_pages)
    assert prepared.sidecar["sourceFormat"] == "docx"
    assert prepared.sidecar["kind"] == "prose"  # prose stays prose for .doc


def _convert_to_vni_pages(src, outdir, **kw):
    """Stand-in for a deck typed in a VNI-Times font: the PDF holds raw VNI bytes."""
    return _render_pdf(outdir / (src.stem + ".pdf"), [
        "CHÖÔNG XV: MIEÃN, GIAÛM TRAÙCH NHIEÄM HÌNH SÖÏ",
        "Khaùi nieäm vaø yù nghóa cuûa QÑHP",
    ])


def test_legacy_ppt_in_a_vni_font_lands_as_unicode(tmp_path):
    """v0.15.0: raw VNI bytes would be unsearchable — decode at extraction."""
    src = tmp_path / "[Hình sự][Slide] bai 15.ppt"
    src.write_bytes(b"fake ole")
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w",
                                convert_fn=_convert_to_vni_pages)
    texts = [u["text"] for u in prepared.sidecar["units"]]
    assert texts == ["CHƯƠNG XV: MIỄN, GIẢM TRÁCH NHIỆM HÌNH SỰ",
                     "Khái niệm và ý nghĩa của QĐHP"]
    assert prepared.sidecar["kind"] == "slide"
    assert validate_sidecar(prepared.sidecar) == []


def test_pdf_text_is_normalized_too(make_pdf, tmp_path):
    """v0.16.0: normalization is not a .doc/.ppt speciality. A PDF whose tone
    marks arrive as separate combining characters would be unsearchable."""
    import unicodedata
    src = make_pdf("[Môn] vb.pdf", [unicodedata.normalize("NFD", "Bổ sung tội danh")])
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    joined = "\n".join(u["text"] for u in prepared.sidecar["units"])
    assert "Bổ sung tội danh" in unicodedata.normalize("NFC", joined)
    assert joined == unicodedata.normalize("NFC", joined)


def test_pptx_text_is_normalized_too(make_pptx, tmp_path):
    """A .pptx (not just legacy .ppt) can carry VNI text pasted in from an old
    deck; it must not sail past unconverted."""
    src = make_pptx("[Môn] deck.pptx", ["Khaùi nieäm vaø yù nghóa cuûa QÑHP"])
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    assert prepared.sidecar["units"][0]["text"] == "Khái niệm và ý nghĩa của QĐHP"


def test_docx_text_is_normalized_too(make_docx, tmp_path):
    src = make_docx("[Môn] bai.docx", ["Ñoái töôïng ñieàu chænh"])
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    joined = "\n".join(u["text"] for u in prepared.sidecar["units"])
    assert "Đối tượng điều chỉnh" in joined


def test_image_pdf_marker_survives_normalization(tmp_path):
    """The scanned-page marker is what Phase 2 OCR looks for — it must come out
    byte-identical."""
    from gu_library_worker.readers.pdf_reader import IMAGE_PAGE_MARKER
    src = _heavy_scan(tmp_path / "[Môn] scan.pdf", pages=1, img_w=150)
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    assert IMAGE_PAGE_MARKER in prepared.sidecar["units"][0]["text"]


def test_pdf_in_a_vni_font_is_decoded_too(make_pdf, tmp_path):
    """The VNI half of normalization is not a .ppt speciality either: a plain
    PDF whose text was typed in a VNI-Times font must land searchable."""
    src = make_pdf("[Môn] bai.pdf", [
        "Khaùi nieäm vaø yù nghóa cuûa QÑHP",
        "Ñoái töôïng ñieàu chænh cuûa luaät hình söï",
    ])
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    joined = "\n".join(u["text"] for u in prepared.sidecar["units"])
    assert "Khái niệm và ý nghĩa của QĐHP" in joined
    assert "Đối tượng điều chỉnh của luật hình sự" in joined
    assert validate_sidecar(prepared.sidecar) == []


def test_a_vni_law_pdf_keeps_its_legal_structure(make_pdf, tmp_path):
    """Decoding happens after parsing, so it cannot disturb Điều/Khoản units —
    but a VNI-encoded law never parsed as legal in the first place."""
    src = make_pdf("[Môn] luat.pdf", [
        "Điều 1. Phạm vi điều chỉnh",
        "Luaät naøy quy ñònh veà toäi phaïm.",
    ])
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    assert prepared.sidecar["kind"] == "legal"
    joined = "\n".join(u["text"] for u in prepared.sidecar["units"])
    assert "Luật này quy định về tội phạm." in joined
