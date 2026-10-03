# src/gu_library_worker/ocr_stage.py
"""OCR stage: give image pages real text, a few minutes at a time.

Runs after intake on every pass, only for a kho that opted in with
`<kho>_ocrcache/ocr.json` = {"enabled": true, "workers": 2}. Work is derived
from the filesystem like the rest of the worker: a sidecar that still has an
"image page" placeholder unit (and no text from anywhere but OCR) is a job.

- Priority: documents Gú has opened (from `_reading-*.json`), furthest-read
  first; then the rest, fewest pages first.
- Budget: page jobs stop being started once the pass's OCR time is used up; the
  next pass carries on. Every finished page is appended to a per-document cache
  in `<kho>_ocrcache/pages/`, keyed by the PDF's size+mtime and the engine, so
  an interrupted document resumes and a re-run never OCRs a page twice.
- A sidecar is rewritten ONCE, when every page is cached, and only if the
  result differs. Right before the swap the PDF and the old sidecar are checked
  again; if anything moved (the app renamed or replaced it), nothing is written.
  The new file is written in `<kho>_ocrcache/tmp/` and moved in with
  os.replace, so the kho never sees a temp or half-written file.
- Pages that fail the quality gate keep their placeholder unit unchanged.
"""
from __future__ import annotations
import hashlib
import json
import logging
import os
import threading
import time
import unicodedata
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import fitz  # PyMuPDF

from .config import Paths
from .logsetup import kho_logging
from .ocr import Engine, OcrLine, PageOcr, clean_text, find_engine, ocr_page, page_verdict
from .readers.pdf_reader import extract_from_page_blocks, is_marker_text, marker_unit
from .schema import Document, to_sidecar, validate_sidecar

log = logging.getLogger("gu_library_worker")

CONFIG_NAME = "ocr.json"
DEFAULT_WORKERS = 2
MAX_WORKERS = 8
DEFAULT_BUDGET_S = 120.0
LOCK_STALE_S = 45 * 60      # longer than the task's 30-minute execution limit
CACHE_VERSION = 1
_RENDER_LOCK = threading.Lock()   # MuPDF is not thread-safe; rendering is short

@dataclass(frozen=True)
class OcrConfig:
    workers: int = DEFAULT_WORKERS

@dataclass
class StageReport:
    pages_ocr: int = 0
    pages_failed: int = 0
    docs_written: int = 0
    docs_pending: int = 0
    pages_kept_marker: int = 0

@dataclass
class Candidate:
    json_path: Path
    pdf_path: Path
    rel: str                  # PDF path relative to the kho, "/"-separated, NFC
    rel_json: str
    pages: int

@dataclass
class _DocState:
    cand: Candidate
    pdf_sig: list[int]
    cache: "_DocCache"
    missing: list[int]
    workdir: Path
    renderer: "_Renderer | None" = None
    in_flight: int = 0

def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)

def _sig(path: Path) -> list[int]:
    st = path.stat()
    return [st.st_size, st.st_mtime_ns]

def _doc_id(rel: str) -> str:
    return hashlib.sha1(rel.encode("utf-8")).hexdigest()[:16]

def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)

# --------------------------------------------------------------------- config
def load_config(paths: Paths) -> OcrConfig | None:
    """The kho's OCR switch; None (= OCR off) unless ocr.json says enabled."""
    f = paths.ocr_dir / CONFIG_NAME
    if not f.is_file():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("ocr: unreadable %s (%s) - OCR off", f, exc)
        return None
    if not isinstance(data, dict) or data.get("enabled") is not True:
        return None
    workers = data.get("workers", DEFAULT_WORKERS)
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= MAX_WORKERS:
        log.warning("ocr: workers=%r in %s is not 1-%d - using %d",
                    workers, f, MAX_WORKERS, DEFAULT_WORKERS)
        workers = DEFAULT_WORKERS
    return OcrConfig(workers=workers)

# ----------------------------------------------------------------------- lock
class _Lock:
    """One OCR run per kho (a manual run must not race the scheduled one)."""

    def __init__(self, path: Path):
        self.path = path
        self.held = False

    def acquire(self) -> bool:
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    age = time.time() - self.path.stat().st_mtime
                except OSError:
                    continue
                if age < LOCK_STALE_S:
                    return False
                self.path.unlink(missing_ok=True)   # left by a killed run
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(f"{os.getpid()} {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.held = True
            return True
        return False

    def release(self) -> None:
        if self.held:
            self.path.unlink(missing_ok=True)
            self.held = False

# -------------------------------------------------------------- discovery
def _iter_sidecars(kho_root: Path):
    for dirpath, dirnames, filenames in os.walk(kho_root):
        rel = Path(dirpath).relative_to(kho_root)
        if rel.parts and rel.parts[0][:1] in ("_", "."):   # _inbox, _print, .stversions…
            dirnames[:] = []
            continue
        dirnames.sort()
        for name in sorted(filenames):
            if name.endswith(".json") and not name.startswith("_"):
                yield Path(dirpath) / name

def _inspect(json_path: Path) -> dict:
    """What OCR needs to know about a sidecar, cached in the index by size+mtime."""
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"marker": False, "foreign": False, "pages": 0}
    units = data.get("units") if isinstance(data, dict) else None
    if not isinstance(units, list):
        return {"marker": False, "foreign": False, "pages": 0}
    marker = foreign = False
    for u in units:
        text = u.get("text", "") if isinstance(u, dict) else ""
        if is_marker_text(text):
            marker = True
        elif not (isinstance(u, dict) and u.get("ocr") is True):
            foreign = True          # text from a text layer/docx: never OCR over it
    pages = data.get("pageCount")
    return {"marker": marker, "foreign": foreign,
            "pages": pages if isinstance(pages, int) and not isinstance(pages, bool) else 0}

def discover(paths: Paths, index: dict) -> list[Candidate]:
    old = index.get("files", {})
    files: dict[str, dict] = {}
    out: list[Candidate] = []
    for js in _iter_sidecars(paths.kho_root):
        rel_json = _nfc(js.relative_to(paths.kho_root).as_posix())
        try:
            sig = _sig(js)
        except OSError:
            continue
        entry = old.get(rel_json)
        if entry is None or entry.get("sig") != sig:
            entry = {"sig": sig, **_inspect(js), "done": None}
            if entry["marker"] and entry["foreign"]:
                log.warning("ocr: %s mixes text units and image placeholders - not OCR'd",
                            rel_json)
        files[rel_json] = entry
        pdf = js.with_suffix(".pdf")
        if entry["marker"] and not entry["foreign"] and entry["pages"] > 0 and pdf.is_file():
            out.append(Candidate(json_path=js, pdf_path=pdf, rel_json=rel_json,
                                 rel=_nfc(pdf.relative_to(paths.kho_root).as_posix()),
                                 pages=entry["pages"]))
    index["files"] = files
    return out

def reading_progress(kho_root: Path) -> dict[str, tuple[float, int]]:
    """PDF rel path -> (furthest page/total, last read) over every device's
    `_reading-*.json`; an entry is gone when any device tombstoned it later."""
    entries: list[tuple[str, dict]] = []
    tombstones: dict[str, int] = {}
    for f in sorted(kho_root.glob("_reading-*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        for key, ts in (data.get("tombstones") or {}).items():
            if isinstance(ts, (int, float)):
                tombstones[_nfc(key)] = max(tombstones.get(_nfc(key), 0), ts)
        for key, e in (data.get("entries") or {}).items():
            if isinstance(e, dict):
                entries.append((_nfc(key), e))
    out: dict[str, tuple[float, int]] = {}
    for key, e in entries:
        last = e.get("lastReadAt") or 0
        if key in tombstones and tombstones[key] >= last:
            continue
        page, total = e.get("page"), e.get("total")
        frac = page / total if isinstance(page, int) and isinstance(total, int) and total > 0 else 0.0
        prev = out.get(key, (0.0, 0))
        out[key] = (max(frac, prev[0]), max(last, prev[1]))
    return out

def order_candidates(cands: list[Candidate], progress: dict[str, tuple[float, int]]
                     ) -> list[Candidate]:
    opened = sorted((c for c in cands if c.rel in progress),
                    key=lambda c: (-progress[c.rel][0], -progress[c.rel][1], c.rel))
    rest = sorted((c for c in cands if c.rel not in progress), key=lambda c: (c.pages, c.rel))
    return opened + rest

# ------------------------------------------------------------------ cache
class _DocCache:
    """Append-only per-document page results (JSON lines), header first."""

    def __init__(self, path: Path, header: dict):
        self.path = path
        self.header = header
        self.pages: dict[int, dict] = {}
        if path.is_file():
            lines = path.read_text(encoding="utf-8").splitlines()
            try:
                stored = json.loads(lines[0]) if lines else None
            except ValueError:
                stored = None
            if stored == header:
                for line in lines[1:]:
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue            # a line cut short by a killed run
                    if isinstance(rec, dict) and isinstance(rec.get("page"), int):
                        self.pages[rec["page"]] = rec
                return
            path.unlink(missing_ok=True)    # PDF or engine changed: start over
        path.write_text(json.dumps(header, ensure_ascii=False) + "\n", encoding="utf-8")

    def add(self, rec: dict) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.pages[rec["page"]] = rec

def _record(res: PageOcr) -> dict:
    if res.error is not None:
        return {"page": res.page, "error": res.error}
    return {"page": res.page, "dpi": res.dpi,
            "lines": [[l.text, l.bbox, l.conf, list(l.block)] for l in res.lines]}

class _Renderer:
    def __init__(self, pdf_bytes: bytes):
        self.doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    def __call__(self, page_no: int, dpi: int, png: Path) -> None:
        with _RENDER_LOCK:
            pix = self.doc[page_no - 1].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
            pix.save(str(png))

    def close(self) -> None:
        with _RENDER_LOCK:
            self.doc.close()

def _cached_rects(cache_path: Path, rel: str, pdf_sig: list[int], engine: Engine):
    """Page rects from an existing cache header for this exact PDF, else None."""
    try:
        with open(cache_path, encoding="utf-8") as f:
            header = json.loads(f.readline())
    except (OSError, ValueError):
        return None
    if (isinstance(header, dict) and header.get("v") == CACHE_VERSION
            and header.get("rel") == rel and header.get("pdf") == pdf_sig
            and header.get("engine") == engine.key and isinstance(header.get("rects"), list)):
        return header["rects"]
    return None

def _clear_dir(path: Path) -> None:
    if not path.exists():
        return
    for leftover in sorted(path.rglob("*"), reverse=True):
        try:
            (leftover.rmdir if leftover.is_dir() else leftover.unlink)()
        except OSError:
            pass

def _prune_caches(ocr_dir: Path, index: dict) -> None:
    """Drop page caches of PDFs that no longer have a sidecar in the kho."""
    keep = {_doc_id(rel[:-len(".json")] + ".pdf") for rel in index.get("files", {})}
    for f in (ocr_dir / "pages").glob("*.jsonl"):
        if f.stem not in keep:
            f.unlink(missing_ok=True)

def _still_ocr_target(sidecar: dict) -> bool:
    units = sidecar.get("units") if isinstance(sidecar, dict) else None
    if not isinstance(units, list):
        return False
    has_marker = False
    for u in units:
        if not isinstance(u, dict):
            return False
        if is_marker_text(u.get("text", "")):
            has_marker = True
        elif u.get("ocr") is not True:
            return False
    return has_marker

# --------------------------------------------------------------- build/write
def build_sidecar(original: dict, cache_pages: dict[int, dict], rects: list[list[float]]
                  ) -> tuple[dict | None, list[int]]:
    """New sidecar from cached page results (None if no page passed the gate),
    plus the pages that keep their placeholder. Pure: same input, same output."""
    n = len(rects)
    page_blocks: list[list[list[tuple[str, list[float]]]]] = []
    kept_marker: list[int] = []
    for p in range(1, n + 1):
        rec = cache_pages[p]
        lines = [OcrLine(text=clean_text(t), bbox=b, conf=c, block=tuple(k))
                 for t, b, c, k in rec.get("lines", [])]
        lines = [l for l in lines if l.text.strip()]
        ok = "error" not in rec and bool(lines) and page_verdict(lines)[0]
        if not ok:
            kept_marker.append(p)
            page_blocks.append([])
            continue
        blocks: dict[tuple, list[tuple[str, list[float]]]] = {}
        for l in lines:
            blocks.setdefault(l.block, []).append((l.text, l.bbox))
        page_blocks.append(list(blocks.values()))
    extraction = extract_from_page_blocks(page_blocks, [r[3] - r[1] for r in rects])
    if extraction is None:
        return None, kept_marker
    units = list(extraction.units)
    for u in units:
        u.ocr = True
    units += [marker_unit(p, rects[p - 1]) for p in kept_marker]
    units.sort(key=lambda u: u.page)        # stable: reading order kept within a page
    doc = Document(title=original["title"], source=original["source"],
                   sourceFormat=original["sourceFormat"], kind=extraction.kind,
                   units=units, addedAt=original["addedAt"], pageCount=n)
    return to_sidecar(doc), kept_marker

def replace_if_unchanged(json_path: Path, expected: bytes, new_text: str,
                         pdf_path: Path, pdf_sig: list[int], tmpdir: Path) -> bool:
    """Swap in the new sidecar only if the PDF and the old sidecar are exactly as
    they were when the work started. Written outside the kho, moved in atomically."""
    try:
        if _sig(pdf_path) != pdf_sig or json_path.read_bytes() != expected:
            return False
    except OSError:
        return False
    tmp = tmpdir / (_doc_id(str(json_path)) + ".json")
    tmp.write_text(new_text, encoding="utf-8")   # same text-mode write as writer.py
    for attempt in range(5):
        try:
            os.replace(tmp, json_path)
            return True
        except PermissionError:                  # Syncthing/AV briefly holding it
            time.sleep(0.2)
    tmp.unlink(missing_ok=True)
    return False

def _finalize(st: _DocState, tmpdir: Path, entry: dict, engine: Engine,
              report: StageReport) -> None:
    cand = st.cand
    try:
        raw = cand.json_path.read_bytes()
        original = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("ocr: cannot re-read %s (%s) - retry next pass", cand.rel_json, exc)
        return
    if not _still_ocr_target(original):
        log.warning("ocr: %s no longer holds only image placeholders - not written",
                    cand.rel_json)
        return
    rects = st.cache.header["rects"]
    if original.get("pageCount") != len(rects):
        log.warning("ocr: %s pageCount %s != PDF pages %d - skipped",
                    cand.rel_json, original.get("pageCount"), len(rects))
        return
    new, kept = build_sidecar(original, st.cache.pages, rects)
    report.pages_kept_marker += len(kept)
    if new is None or new == original:
        entry["done"] = [engine.key, entry["sig"]]
        return
    errors = validate_sidecar(new)
    if errors:
        log.error("ocr: built an invalid sidecar for %s: %s - not written", cand.rel_json, errors)
        return
    text = json.dumps(new, ensure_ascii=False, indent=2)
    if not replace_if_unchanged(cand.json_path, raw, text, cand.pdf_path, st.pdf_sig, tmpdir):
        log.warning("ocr: %s or its PDF changed while OCR ran - not written, retry next pass",
                    cand.rel_json)
        return
    entry["sig"] = _sig(cand.json_path)
    entry["done"] = [engine.key, entry["sig"]]
    report.docs_written += 1
    log.info("ocr: wrote %s (%d/%d pages with text, %d kept placeholder, kind=%s)",
             cand.rel_json, len(rects) - len(kept), len(rects), len(kept), new["kind"])

# ---------------------------------------------------------------- the stage
def ocr_kho(paths: Paths, cfg: OcrConfig, engine: Engine, deadline: float, *,
            ocr_fn: Callable[..., PageOcr] = ocr_page,
            clock: Callable[[], float] = time.monotonic) -> StageReport:
    report = StageReport()
    ocr_dir = paths.ocr_dir
    (ocr_dir / "pages").mkdir(parents=True, exist_ok=True)
    tmpdir = ocr_dir / "tmp"
    lock = _Lock(ocr_dir / "lock")
    if not lock.acquire():
        log.info("ocr: another OCR run holds %s - skipped this pass", lock.path)
        return report
    started = clock()
    try:
        _clear_dir(tmpdir)                       # leftovers of a killed run
        tmpdir.mkdir(exist_ok=True)
        index_path = ocr_dir / "index.json"
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            index = {}
        if index.get("v") != CACHE_VERSION:
            index = {"v": CACHE_VERSION}
        cands = order_candidates(discover(paths, index), reading_progress(paths.kho_root))
        todo = [c for c in cands
                if index["files"][c.rel_json].get("done") != [engine.key, index["files"][c.rel_json]["sig"]]]
        states = _run_pages(todo, cfg, engine, deadline, tmpdir, ocr_dir, ocr_fn, clock, report)
        for st in states:
            if st.renderer is not None:
                st.renderer.close()
            if all(p in st.cache.pages for p in range(1, st.cand.pages + 1)):
                _finalize(st, tmpdir, index["files"][st.cand.rel_json], engine, report)
            else:
                report.docs_pending += 1
        report.docs_pending += max(0, len(todo) - len(states))
        _write_atomic(index_path, json.dumps(index, ensure_ascii=False))
        _prune_caches(ocr_dir, index)
    finally:
        _clear_dir(tmpdir)
        lock.release()
    if report.pages_ocr or report.docs_written or report.docs_pending:
        log.info("ocr: %d pages OCR'd (%d failed) in %.0fs, %d docs written, %d docs pending",
                 report.pages_ocr, report.pages_failed, clock() - started,
                 report.docs_written, report.docs_pending)
    return report

def _open_state(cand: Candidate, engine: Engine, ocr_dir: Path, tmpdir: Path) -> _DocState | None:
    cache_path = ocr_dir / "pages" / f"{_doc_id(cand.rel)}.jsonl"
    try:
        pdf_sig = _sig(cand.pdf_path)
        rects = _cached_rects(cache_path, cand.rel, pdf_sig, engine)
        if rects is None:
            with fitz.open(stream=cand.pdf_path.read_bytes(), filetype="pdf") as doc:
                rects = [[float(c) for c in page.rect] for page in doc]
    except Exception as exc:
        log.warning("ocr: cannot open %s (%s) - skipped", cand.rel, exc)
        return None
    if len(rects) != cand.pages:
        log.warning("ocr: %s has %d pages but its sidecar says %d - skipped",
                    cand.rel, len(rects), cand.pages)
        return None
    header = {"v": CACHE_VERSION, "rel": cand.rel, "pdf": pdf_sig, "engine": engine.key,
              "rects": rects}
    cache = _DocCache(cache_path, header)
    missing = [p for p in range(1, len(rects) + 1) if p not in cache.pages]
    workdir = tmpdir / _doc_id(cand.rel)
    return _DocState(cand=cand, pdf_sig=pdf_sig, cache=cache, missing=missing, workdir=workdir)

def _run_pages(todo: list[Candidate], cfg: OcrConfig, engine: Engine, deadline: float,
               tmpdir: Path, ocr_dir: Path, ocr_fn, clock, report: StageReport) -> list[_DocState]:
    """OCR missing pages across documents in priority order until the deadline.

    Returns the state of every document looked at (fully cached ones included)."""
    states: list[_DocState] = []
    queue = iter(todo)
    current: _DocState | None = None
    in_flight: dict = {}

    def next_job():
        nonlocal current
        while True:
            if current is not None and current.missing:
                return current, current.missing.pop(0)
            cand = next(queue, None)
            if cand is None:
                return None
            st = _open_state(cand, engine, ocr_dir, tmpdir)
            if st is not None:
                states.append(st)
                current = st

    with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
        while True:
            while len(in_flight) < cfg.workers and clock() < deadline:
                job = next_job()
                if job is None:
                    break
                st, page = job
                if st.renderer is None:
                    st.renderer = _Renderer(st.cand.pdf_path.read_bytes())
                    st.workdir.mkdir(parents=True, exist_ok=True)
                in_flight[pool.submit(ocr_fn, engine, st.renderer, page, st.workdir)] = st
            if not in_flight:
                break
            done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
            for fut in done:
                st = in_flight.pop(fut)
                res = fut.result()
                st.cache.add(_record(res))
                report.pages_ocr += 1
                if res.error is not None:
                    report.pages_failed += 1
                    log.warning("ocr: %s page %d failed: %s", st.cand.rel, res.page, res.error)
    # documents not reached before the deadline are picked up on a later pass
    return states

def run_stage(kho_roots: list[Path], budget_s: float, label_of: Callable[[Path], str], *,
              find: Callable[[], tuple[Engine | None, str]] = find_engine,
              ocr_fn: Callable[..., PageOcr] = ocr_page,
              clock: Callable[[], float] = time.monotonic) -> None:
    """Run OCR for every opted-in kho, sharing one time budget for the pass."""
    deadline = clock() + budget_s
    engine: Engine | None = None
    reason = ""
    looked = False
    for kho_root in kho_roots:
        paths = Paths(kho_root=kho_root)
        if not (paths.ocr_dir / CONFIG_NAME).is_file():
            continue                              # not opted in: stay silent
        with kho_logging(kho_root, label_of(kho_root)):
            cfg = load_config(paths)
            if cfg is None:
                continue
            if not looked:
                engine, reason = find()
                looked = True
            if engine is None:
                log.warning("ocr skipped: %s", reason)
                continue
            try:
                ocr_kho(paths, cfg, engine, deadline, ocr_fn=ocr_fn, clock=clock)
            except Exception as exc:              # OCR must never break the pass
                log.exception("ocr failed, skipping this kho: %s", exc)
