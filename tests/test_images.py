# tests/test_images.py
import fitz
from gu_library_worker.images import image_to_single_page_pdf

def _jpeg(w, h):
    pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, w, h))
    pm.set_rect(pm.irect, (210, 190, 170))
    pm.set_rect(fitz.IRect(10, 10, min(w, 120), min(h, 120)), (30, 110, 190))  # detail
    return pm.tobytes("jpeg", jpg_quality=88)

def test_portrait_image_gives_portrait_page(tmp_path):
    src = tmp_path / "p.jpg"; src.write_bytes(_jpeg(600, 900))
    out = tmp_path / "p.pdf"; image_to_single_page_pdf(src, out)
    with fitz.open(out) as d:
        assert d.page_count == 1
        r = d[0].rect
        assert r.height > r.width                         # portrait
        assert abs(r.width / r.height - 600 / 900) < 0.01  # aspect preserved

def test_landscape_image_gives_landscape_page(tmp_path):
    src = tmp_path / "l.jpg"; src.write_bytes(_jpeg(900, 600))
    out = tmp_path / "l.pdf"; image_to_single_page_pdf(src, out)
    with fitz.open(out) as d:
        r = d[0].rect
        assert r.width > r.height                         # landscape, not forced portrait
        assert abs(r.width / r.height - 900 / 600) < 0.01

def test_jpeg_embedded_losslessly(tmp_path):
    jpg = _jpeg(500, 700)
    src = tmp_path / "a.jpg"; src.write_bytes(jpg)
    out = tmp_path / "a.pdf"; image_to_single_page_pdf(src, out)
    with fitz.open(out) as d:
        info = d.extract_image(d[0].get_images(full=True)[0][0])
    assert info["ext"] == "jpeg"
    assert info["image"] == jpg                           # byte-identical -> no re-encode
