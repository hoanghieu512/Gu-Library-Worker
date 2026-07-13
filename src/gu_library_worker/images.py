# src/gu_library_worker/images.py
"""Wrap a single image (jpg/png/…) into a one-page PDF.

Each image is its OWN document (never merged into a multi-page PDF). The page
keeps the image's aspect ratio — a wide/double-page photo yields a landscape
page, a portrait photo a portrait page — with the long side set to A4 length so
the embedded pixels map to a realistic DPI, which lets the existing heavy-scan
detection + normalization apply exactly as for scanned PDFs. The image is
embedded as-is (JPEG stays JPEG, no re-encode) so quality is preserved; if that
raster is too heavy for a phone, the scan-normalization path lightens it later.
"""
from __future__ import annotations
from pathlib import Path
import fitz  # PyMuPDF

_PAGE_LONG_PT = 842.0  # A4 long side (points); page aspect comes from the image

def image_to_single_page_pdf(src: Path, out: Path) -> None:
    src = Path(src)
    data = src.read_bytes()  # from bytes -> no OS handle lingers on the source
    with fitz.open(stream=data, filetype=src.suffix.lstrip(".").lower()) as im:
        rect = im[0].rect
        w, h = rect.width, rect.height  # ratio == pixel ratio (aspect preserved)
    if w <= 0 or h <= 0:
        raise ValueError(f"bad image dimensions for {src.name}")
    if w >= h:  # landscape / square -> landscape page
        page_w, page_h = _PAGE_LONG_PT, _PAGE_LONG_PT * h / w
    else:       # portrait -> portrait page
        page_w, page_h = _PAGE_LONG_PT * w / h, _PAGE_LONG_PT
    doc = fitz.open()
    try:
        page = doc.new_page(width=page_w, height=page_h)
        page.insert_image(page.rect, stream=data)  # lossless embed (JPEG kept as-is)
        doc.save(str(out), garbage=4, deflate=True)
    finally:
        doc.close()
