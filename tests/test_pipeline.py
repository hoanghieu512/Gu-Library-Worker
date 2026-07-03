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
    assert prepared.canonical_pdf != src                       # a new, lighter file
    assert _max_img_width(prepared.canonical_pdf) < src_w      # fewer pixels to decode
    assert prepared.sidecar["pageCount"] == 2                  # sidecar matches kho copy
    assert validate_sidecar(prepared.sidecar) == []

def test_light_scan_pdf_passthrough(tmp_path):
    # a zero-text scan that is already low-res -> not heavy -> not re-rastered
    src = _heavy_scan(tmp_path / "[Môn] light.pdf", pages=1, img_w=150)   # ~72 dpi
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    assert prepared.normalized is False
    assert prepared.canonical_pdf == src                       # untouched
