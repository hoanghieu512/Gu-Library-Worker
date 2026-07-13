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
