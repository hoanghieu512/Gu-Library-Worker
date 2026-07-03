# tests/test_normalize.py
import fitz
from gu_library_worker.normalize import is_heavy_scan, normalize_pdf, HEAVY_DPI_THRESHOLD

# Small pages/images keep the tests fast while still crossing the DPI threshold:
# a 150pt-wide page (2.083in) with a 500px image -> 240 dpi (> 200 = heavy).
def _scan(path, pages=2, img_w=500, colored=False):
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page(width=150, height=200)
        h = round(img_w * 200 / 150)
        pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, img_w, h))
        pm.set_rect(pm.irect, (235, 235, 235))
        if colored:
            pm.set_rect(fitz.IRect(10, 10, img_w // 2, h // 2), (210, 20, 20))  # stamp
        page.insert_image(page.rect, pixmap=pm)
    doc.save(path); doc.close()
    return path

def _max_img_width(pdf):
    with fitz.open(pdf) as d:
        return max(img[2] for page in d for img in page.get_images(full=True))

def test_high_dpi_scan_is_heavy(tmp_path):
    assert is_heavy_scan(_scan(tmp_path / "hi.pdf", img_w=500)) is True

def test_low_dpi_scan_is_light(tmp_path):
    assert is_heavy_scan(_scan(tmp_path / "lo.pdf", img_w=150)) is False   # ~72 dpi

def test_blank_pdf_is_not_heavy(tmp_path):
    doc = fitz.open(); doc.new_page(); doc.save(tmp_path / "blank.pdf"); doc.close()
    assert is_heavy_scan(tmp_path / "blank.pdf") is False

def test_normalize_preserves_pages_and_size(tmp_path):
    src = _scan(tmp_path / "s.pdf", pages=3)
    out = tmp_path / "o.pdf"
    normalize_pdf(src, out)
    with fitz.open(src) as a, fitz.open(out) as b:
        assert b.page_count == a.page_count == 3
        for pa, pb in zip(a, b):
            assert tuple(round(x, 1) for x in pb.rect) == tuple(round(x, 1) for x in pa.rect)

def test_normalize_reduces_raster_resolution(tmp_path):
    # the actual win: fewer pixels per page to decode (150 dpi cap)
    src = _scan(tmp_path / "s.pdf", pages=1, img_w=500)   # 240 dpi
    out = tmp_path / "o.pdf"
    normalize_pdf(src, out)
    assert _max_img_width(out) < _max_img_width(src)
    assert is_heavy_scan(out) is False                    # normalized is now light

def test_normalize_grayscale_vs_color_per_page(tmp_path):
    for colored, expect_channels in ((False, 1), (True, 3)):
        src = _scan(tmp_path / f"{colored}.pdf", pages=1, colored=colored)
        out = tmp_path / f"{colored}_n.pdf"
        normalize_pdf(src, out)
        with fitz.open(out) as b:
            xref = b[0].get_images(full=True)[0][0]
            assert b.extract_image(xref)["colorspace"] == expect_channels
