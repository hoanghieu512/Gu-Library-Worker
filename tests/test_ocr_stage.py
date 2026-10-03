# tests/test_ocr_stage.py
import html
import json
import os
import time
from pathlib import Path

import fitz
import pytest

from gu_library_worker import ocr_stage
from gu_library_worker.config import Paths
from gu_library_worker.ocr import Engine, OcrLine, PageOcr, find_engine
from gu_library_worker.ocr_stage import (
    Candidate, OcrConfig, ocr_kho, order_candidates, reading_progress,
    replace_if_unchanged, run_stage,
)
from gu_library_worker.readers.pdf_reader import IMAGE_PAGE_MARKER, read_pdf
from gu_library_worker.schema import Document, to_sidecar, validate_sidecar

FAKE_ENGINE = Engine(exe=Path("tesseract.exe"), tessdata=Path("tessdata"), version="5.4.0.test")
REL_JSON = "Hình sự/VBQPPL/Luật scan.json"

def _image_pdf(path: Path, pages: int) -> Path:
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()                     # no text layer: an image page to the worker
    doc.save(path)
    doc.close()
    return path

def _sidecar_for(pdf: Path) -> dict:
    ext = read_pdf(pdf)
    return to_sidecar(Document(title=pdf.stem, source="share", sourceFormat="pdf",
                               kind=ext.kind, units=ext.units,
                               addedAt="2026-07-02T19:02:00+07:00", pageCount=len(ext.units)))

def _make_kho(tmp_path: Path, pages: int = 3, workers: int = 1, rel_json: str = REL_JSON,
              enable: bool = True) -> tuple[Paths, Path, Path]:
    kho = tmp_path / "kho"
    js = kho / rel_json
    js.parent.mkdir(parents=True, exist_ok=True)
    pdf = _image_pdf(js.with_suffix(".pdf"), pages)
    js.write_text(json.dumps(_sidecar_for(pdf), ensure_ascii=False, indent=2), encoding="utf-8")
    paths = Paths(kho_root=kho)
    if enable:
        paths.ocr_dir.mkdir(parents=True, exist_ok=True)
        (paths.ocr_dir / "ocr.json").write_text(
            json.dumps({"enabled": True, "workers": workers}), encoding="utf-8")
    return paths, pdf, js

PAGE_TEXT = {
    1: [("Ðiều 1. Phạm vi điều chỉnh", [72, 100, 400, 115]),       # eth, as Tesseract emits it
        ("Luật này quy định về tội phạm và hình phạt đối với người phạm tội.", [72, 120, 520, 135])],
    2: [("1. Người nào phạm tội thì phải chịu trách nhiệm hình sự theo quy định.", [72, 100, 520, 115])],
    3: [("x7", [72, 100, 90, 115])],                               # too little text: keeps marker
}

class FakeOcr:
    """Stands in for Tesseract: fixed lines per page, optional fake clock tick."""

    def __init__(self, text=PAGE_TEXT, clock=None, tick=0.0):
        self.text, self.clock, self.tick, self.calls = text, clock, tick, []

    def __call__(self, engine, render, page_no, workdir):
        self.calls.append(page_no)
        if self.clock is not None:
            self.clock.now += self.tick
        lines = [OcrLine(t, list(b), 92.0, (1, i)) for i, (t, b) in enumerate(self.text.get(page_no, []))]
        return PageOcr(page=page_no, lines=lines)

class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

def _run(paths, fake, budget=1e9, clock=None):
    clock = clock or FakeClock()
    return ocr_kho(paths, OcrConfig(workers=1), FAKE_ENGINE, clock() + budget,
                   ocr_fn=fake, clock=clock)

def test_ocr_fills_text_and_keeps_marker_for_failed_page(tmp_path):
    paths, pdf, js = _make_kho(tmp_path)
    before = json.loads(js.read_text(encoding="utf-8"))
    report = _run(paths, FakeOcr())
    sc = json.loads(js.read_text(encoding="utf-8"))
    assert report.docs_written == 1
    assert validate_sidecar(sc) == []
    assert sc["kind"] == "legal"                                   # prose -> legal
    for key in ("title", "source", "addedAt", "sourceFormat", "pageCount"):
        assert sc[key] == before[key]
    dieu = sc["units"][0]
    assert dieu["type"] == "dieu" and dieu["label"] == "Điều 1"    # Ð fixed before parsing
    assert dieu["text"].startswith("Điều 1. Phạm vi điều chỉnh") and "Ð" not in dieu["text"]
    assert dieu["page"] == 1 and dieu["ocr"] is True
    assert dieu["bbox"] == [72.0, 100.0, 400.0, 115.0]
    khoan = [u for u in sc["units"] if u["type"] == "khoan"]
    assert khoan and khoan[0]["page"] == 2 and khoan[0]["path"] == ["Điều 1"]
    marker = sc["units"][-1]
    assert marker == before["units"][2]                            # page 3 unchanged placeholder
    assert marker["text"] == f"{IMAGE_PAGE_MARKER} (trang 3)" and "ocr" not in marker
    # nothing but the pair in the kho folder; work files live outside the kho
    assert sorted(p.name for p in js.parent.iterdir()) == sorted([js.name, pdf.name])
    assert list((paths.ocr_dir / "pages").glob("*.jsonl"))

def test_budget_stops_midway_and_next_pass_resumes_without_partial_write(tmp_path):
    paths, pdf, js = _make_kho(tmp_path)
    original = js.read_bytes()
    clock = FakeClock()
    first = FakeOcr(clock=clock, tick=10.0)
    _run(paths, first, budget=15.0, clock=clock)                  # pages 1, 2 fit; 3 does not
    assert first.calls == [1, 2]
    assert js.read_bytes() == original                             # never a partial sidecar
    second = FakeOcr()
    report = _run(paths, second)
    assert second.calls == [3]                                     # cached pages not redone
    assert report.docs_written == 1 and js.read_bytes() != original

def test_rerun_is_a_no_op(tmp_path, monkeypatch):
    paths, pdf, js = _make_kho(tmp_path)
    _run(paths, FakeOcr())
    written = js.read_bytes()
    replaced = []
    real_replace = os.replace
    monkeypatch.setattr(ocr_stage.os, "replace",
                        lambda a, b: (replaced.append(Path(b)), real_replace(a, b)))
    again = FakeOcr()
    report = _run(paths, again)
    assert again.calls == [] and report.docs_written == 0
    assert js.read_bytes() == written and js not in replaced

def test_index_loss_rebuilds_from_cache_to_the_same_bytes(tmp_path):
    paths, pdf, js = _make_kho(tmp_path)
    _run(paths, FakeOcr())
    written = js.read_bytes()
    (paths.ocr_dir / "index.json").unlink()
    again = FakeOcr()
    _run(paths, again)
    assert again.calls == [] and js.read_bytes() == written

def test_changed_pdf_invalidates_its_cache(tmp_path):
    paths, pdf, js = _make_kho(tmp_path, pages=3)
    _run(paths, FakeOcr())
    _image_pdf(pdf, 3)                                             # same pages, new file
    os.utime(pdf, ns=(time.time_ns(), time.time_ns() + 5_000_000_000))
    js.write_text(json.dumps(_sidecar_for(pdf), ensure_ascii=False, indent=2), encoding="utf-8")
    again = FakeOcr()
    _run(paths, again)
    assert again.calls == [1, 2, 3]

def test_sidecar_changed_during_run_is_not_overwritten(tmp_path, monkeypatch):
    paths, pdf, js = _make_kho(tmp_path)
    real_build = ocr_stage.build_sidecar

    def build_then_someone_edits(*args, **kw):
        result = real_build(*args, **kw)
        js.write_text(js.read_text(encoding="utf-8").replace("Luật scan", "Đổi tên"),
                      encoding="utf-8")                            # e.g. the app touched it
        return result

    monkeypatch.setattr(ocr_stage, "build_sidecar", build_then_someone_edits)
    report = _run(paths, FakeOcr())
    assert report.docs_written == 0
    assert "Đổi tên" in js.read_text(encoding="utf-8")

def test_replace_if_unchanged_checks_pdf_and_sidecar(tmp_path):
    js, pdf, tmpdir = tmp_path / "a.json", tmp_path / "a.pdf", tmp_path / "tmp"
    tmpdir.mkdir()
    js.write_bytes(b"old")
    pdf.write_bytes(b"%PDF")
    sig = ocr_stage._sig(pdf)
    assert not replace_if_unchanged(js, b"something else", "new", pdf, sig, tmpdir)
    assert not replace_if_unchanged(js, b"old", "new", pdf, [sig[0] + 1, sig[1]], tmpdir)
    assert js.read_bytes() == b"old"
    assert replace_if_unchanged(js, b"old", "new", pdf, sig, tmpdir)
    assert js.read_text(encoding="utf-8") == "new" and not list(tmpdir.iterdir())

def test_document_with_text_layer_units_is_never_ocrd(tmp_path):
    paths, pdf, js = _make_kho(tmp_path)
    sc = json.loads(js.read_text(encoding="utf-8"))
    sc["units"][1] = {"type": "paragraph", "label": "", "path": [], "text": "chữ thật", "page": 2}
    js.write_text(json.dumps(sc, ensure_ascii=False, indent=2), encoding="utf-8")
    fake = FakeOcr()
    _run(paths, fake)
    assert fake.calls == []

def test_all_pages_failing_leaves_sidecar_untouched(tmp_path):
    paths, pdf, js = _make_kho(tmp_path, pages=2)
    original = js.read_bytes()
    _run(paths, FakeOcr(text={1: [("x", [0, 0, 5, 5])]}))
    assert js.read_bytes() == original

def test_fresh_lock_skips_and_stale_lock_is_broken(tmp_path):
    paths, pdf, js = _make_kho(tmp_path)
    lock = paths.ocr_dir / "lock"
    lock.write_text("123", encoding="utf-8")
    fake = FakeOcr()
    _run(paths, fake)
    assert fake.calls == []
    old = time.time() - ocr_stage.LOCK_STALE_S - 60
    os.utime(lock, (old, old))
    _run(paths, fake)
    assert fake.calls == [1, 2, 3] and not lock.exists()

def test_reading_progress_orders_documents(tmp_path):
    kho = tmp_path / "kho"
    kho.mkdir()
    (kho / "_reading-a.json").write_text(json.dumps({
        "deviceId": "a",
        "entries": {
            "S/luat.pdf": {"path": "S/luat.pdf", "page": 38, "total": 48, "lastReadAt": 1_782_000_000_000_000},
            "S/gt.pdf": {"path": "S/gt.pdf", "page": 1, "total": 398, "lastReadAt": 1_785_000_000_000_000},
            "S/xoa.pdf": {"path": "S/xoa.pdf", "page": 9, "total": 10, "lastReadAt": 1_781_000_000_000_000},
        },
        "tombstones": {}}), encoding="utf-8")
    (kho / "_reading-b.json").write_text(json.dumps({
        "deviceId": "b", "entries": {},
        "tombstones": {"S/xoa.pdf": 1_781_000_000_000_001}}), encoding="utf-8")   # deleted
    progress = reading_progress(kho)
    assert set(progress) == {"S/luat.pdf", "S/gt.pdf"}

    def cand(rel, pages):
        return Candidate(json_path=kho / rel, pdf_path=kho / rel, rel=rel, rel_json=rel, pages=pages)

    cands = [cand("S/bao.pdf", 1), cand("S/gt.pdf", 398), cand("S/xoa.pdf", 10), cand("S/luat.pdf", 48)]
    assert [c.rel for c in order_candidates(cands, progress)] == \
        ["S/luat.pdf", "S/gt.pdf", "S/bao.pdf", "S/xoa.pdf"]

def test_run_stage_is_silent_for_kho_without_switch(tmp_path):
    paths, pdf, js = _make_kho(tmp_path, enable=False)
    original = js.read_bytes()
    run_stage([paths.kho_root], 60, lambda p: "T", find=lambda: pytest.fail("looked for engine"))
    assert js.read_bytes() == original and not paths.ocr_dir.exists()

def test_run_stage_without_engine_logs_one_line_and_leaves_kho_alone(tmp_path):
    paths, pdf, js = _make_kho(tmp_path)
    original = js.read_bytes()
    run_stage([paths.kho_root], 60, lambda p: "QA", find=lambda: (None, "tesseract not found"))
    log = (paths.kho_root / "_worker.log").read_text(encoding="utf-8")
    assert log.count("ocr skipped: tesseract not found") == 1
    assert js.read_bytes() == original

def test_run_stage_disabled_switch_is_off(tmp_path):
    paths, pdf, js = _make_kho(tmp_path)
    (paths.ocr_dir / "ocr.json").write_text(json.dumps({"enabled": False}), encoding="utf-8")
    run_stage([paths.kho_root], 60, lambda p: "T", find=lambda: pytest.fail("looked for engine"))

# ------------------------------------------------------------ real Tesseract
ENGINE, WHY = find_engine()
needs_tesseract = pytest.mark.skipif(ENGINE is None, reason=f"no OCR engine: {WHY}")

def _scanned_pdf(path: Path, pages: list[str], scratch: Path) -> Path:
    """Typeset Vietnamese text, then keep only a 200 dpi picture of each page."""
    text_pdf = scratch / (path.stem + "_text.pdf")
    writer = fitz.DocumentWriter(str(text_pdf))
    for body in pages:
        story = fitz.Story(html=f'<p style="font-size:14pt">{html.escape(body).replace(chr(10), "<br>")}</p>')
        dev = writer.begin_page(fitz.paper_rect("a4"))
        story.place(fitz.paper_rect("a4") + (60, 60, -60, -60))
        story.draw(dev, None)
        writer.end_page()
    writer.close()
    out = fitz.open()
    with fitz.open(stream=text_pdf.read_bytes(), filetype="pdf") as src:
        for page in src:
            pix = page.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
            new = out.new_page(width=page.rect.width, height=page.rect.height)
            new.insert_image(new.rect, stream=pix.tobytes("png"))
    out.save(path)
    out.close()
    return path

@needs_tesseract
def test_real_tesseract_end_to_end(tmp_path):
    kho = tmp_path / "kho"
    js = kho / "Môn" / "Nghị quyết.json"
    js.parent.mkdir(parents=True)
    pdf = _scanned_pdf(js.with_suffix(".pdf"), [
        "Điều 1. Phạm vi điều chỉnh\nNghị quyết này hướng dẫn áp dụng quy định về án treo.",
        "Điều 2. Điều kiện cho người bị xử phạt tù được hưởng án treo\n"
        "Người bị xử phạt tù có thể được xem xét cho hưởng án treo khi có đủ các điều kiện.",
    ], scratch=tmp_path)
    assert read_pdf(pdf).image_pdf                                  # really a picture-only PDF
    js.write_text(json.dumps(_sidecar_for(pdf), ensure_ascii=False, indent=2), encoding="utf-8")
    paths = Paths(kho_root=kho)
    report = ocr_kho(paths, OcrConfig(workers=2), ENGINE, time.monotonic() + 600)
    sc = json.loads(js.read_text(encoding="utf-8"))
    assert report.docs_written == 1 and validate_sidecar(sc) == []
    dieu = {u["label"]: u for u in sc["units"] if u["type"] == "dieu"}
    assert set(dieu) == {"Điều 1", "Điều 2"}
    assert dieu["Điều 1"]["page"] == 1 and dieu["Điều 2"]["page"] == 2
    assert "án treo" in dieu["Điều 1"]["text"]
    for u in sc["units"]:
        assert u["ocr"] is True
        x0, y0, x1, y1 = u["bbox"]
        assert 0 <= x0 < x1 <= 595.3 and 0 <= y0 < y1 <= 842
    assert sorted(p.name for p in js.parent.iterdir()) == sorted([js.name, pdf.name])
