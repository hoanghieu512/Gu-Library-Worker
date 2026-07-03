# src/gu_library_worker/normalize.py
"""Normalize a heavy scanned/image PDF so phone viewers can open it smoothly.

A book scanned at 300 dpi with one JPEG2000 image per page decodes to ~33 MB of
bitmap per page — a few pages at once kill the app process. The fix (Option A,
locked): for the ZERO-TEXT branch only, if the page rasters are too heavy for a
viewer (too-high effective DPI and/or JPEG2000 encoding), republish the doc as
150 dpi JPEG pages — same page count, same page size in points, visually
indistinguishable when read, but ~16x cheaper to decode.

Never touches PDFs that carry a text layer (re-raster would lose the text and
thus units/cross-links). Colour is decided per page (grayscale for truly gray
pages, RGB when there is real colour like a stamp), by measuring channel spread.
"""
from __future__ import annotations
from pathlib import Path
import fitz  # PyMuPDF

TARGET_DPI = 150            # normalized raster resolution
HEAVY_DPI_THRESHOLD = 200   # source effective DPI above this -> too heavy
JPEG_QUALITY = 75
_COLOR_TOL = 24             # per-pixel max(RGB)-min(RGB) above this = a colour pixel
_COLOR_MIN_RATIO = 0.004    # >0.4% colour pixels on a page -> keep RGB

def _page_effective_dpi(page, img) -> float:
    page_in = (page.rect.width / 72.0) or 1.0
    return img[2] / page_in          # img[2] = stored image pixel width

def is_heavy_scan(pdf_path: Path) -> bool:
    """True if any page raster is too heavy for a phone viewer (high DPI or JPX).

    Metadata only (no page decode). Pages without images (truly blank) are light.
    """
    with fitz.open(stream=Path(pdf_path).read_bytes(), filetype="pdf") as doc:
        for page in doc:
            for img in page.get_images(full=True):
                if _page_effective_dpi(page, img) > HEAVY_DPI_THRESHOLD:
                    return True
                if "JPX" in (img[8] or ""):   # img[8] = filter, JPXDecode = JPEG2000
                    return True
    return False

def _render_dpi(page) -> int:
    # Cap at TARGET_DPI but never upscale a page that is already lower-res.
    page_in = (page.rect.width / 72.0) or 1.0
    src_dpi = max((img[2] / page_in for img in page.get_images(full=True)),
                  default=float(TARGET_DPI))
    return max(1, int(min(TARGET_DPI, src_dpi)))

def _page_is_gray(pix: "fitz.Pixmap") -> bool:
    if pix.n < 3:
        return True
    s = pix.samples
    n = pix.n
    total = len(s) // n
    if total == 0:
        return True
    step = max(1, total // 5000)      # ~5000 sampled pixels, plenty for a decision
    colored = counted = 0
    for i in range(0, total, step):
        o = i * n
        r, g, b = s[o], s[o + 1], s[o + 2]
        if max(r, g, b) - min(r, g, b) > _COLOR_TOL:
            colored += 1
        counted += 1
    return (colored / counted) < _COLOR_MIN_RATIO

def normalize_pdf(src_path: Path, out_path: Path) -> None:
    """Write a 150 dpi JPEG version of `src_path` to `out_path`.

    Preserves page count and page size (points). Gray pages -> grayscale JPEG,
    colour pages -> RGB JPEG. Opens from bytes so no OS handle lingers on src.
    """
    src_bytes = Path(src_path).read_bytes()
    out = fitz.open()
    try:
        with fitz.open(stream=src_bytes, filetype="pdf") as doc:
            for page in doc:
                pix = page.get_pixmap(dpi=_render_dpi(page), colorspace=fitz.csRGB)
                if _page_is_gray(pix):
                    pix = fitz.Pixmap(fitz.csGRAY, pix)
                img = pix.tobytes("jpeg", jpg_quality=JPEG_QUALITY)
                newpage = out.new_page(width=page.rect.width, height=page.rect.height)
                newpage.insert_image(newpage.rect, stream=img)
        out.save(str(out_path), garbage=4, deflate=True)
    finally:
        out.close()
