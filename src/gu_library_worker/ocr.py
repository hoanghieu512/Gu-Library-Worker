# src/gu_library_worker/ocr.py
"""Tesseract OCR for one page image, plus the rules that decide what to keep.

Choices measured in the 2026-10-03 spike (Docs/spikes/2026-10-03-ocr-scope-and-engine.md):
- Tesseract 5 with the `vie` model from tessdata_BEST (the standard model makes
  twice the errors on photocopies). The file is pinned by hash, so a different
  model is reported as missing instead of silently lowering quality.
- Render at 200 dpi. 300 dpi made MORE diacritic errors on our 150/200 dpi scans;
  only small newspaper text needs it, recognisable by a median line height under
  30 px at 200 dpi -> re-render that page at 300 dpi.
- A page keeps its placeholder unless the result looks like real text: >= 20
  characters, mean line confidence >= 60, and <= 15 % of its words outside a
  fixed word list (garbage from a low-res photo passes the confidence test).
"""
from __future__ import annotations
import csv
import hashlib
import io
import os
import re
import shutil
import statistics
import subprocess
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from pathlib import Path

TESSDATA_BEST_VIE_SHA256 = "b6b49293d95d0b6dbd8780174627e82c75be957b6f4ed9862155540d6b00bb45"
BASE_DPI = 200
SMALL_TEXT_DPI = 300
SMALL_LINE_PX = 30          # median line height (px at BASE_DPI) below this -> SMALL_TEXT_DPI
LONG_LINE_CHARS = 15        # only lines this long count toward the median height
MIN_PAGE_CHARS = 20
MIN_PAGE_CONF = 60.0
MAX_PAGE_OOV = 0.15
PAGE_TIMEOUT_S = 300        # one page; a 300 dpi newspaper page took ~30 s
PSM = 3                     # Tesseract's automatic page segmentation

# Standard locations, checked directly (a Scheduled Task often has no user PATH).
# The per-user one is where a no-admin install of the official build lives; the
# home-based fallback covers a task environment without LOCALAPPDATA.
_LOCAL_APPDATA = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
_TESSERACT_PATHS = (
    str(Path(_LOCAL_APPDATA) / "Programs" / "Tesseract-OCR" / "tesseract.exe"),
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)

# Look-alike characters Tesseract emits for Vietnamese letters. The app folds
# only `đ`->`d` when searching, so an Icelandic eth would split "Ðiều" into the
# token "ieu" and the legal parser (which needs "Điều N.") would miss the article.
_CHAR_FIXES = str.maketrans({
    "\u00d0": "\u0110",   # Ð (eth)  -> Đ
    "\u00f0": "\u0111",   # ð (eth)  -> đ
})

_TOKEN_RE = re.compile(r"[^\W\d_]+")

@dataclass(frozen=True)
class Engine:
    exe: Path
    tessdata: Path
    version: str

    @property
    def key(self) -> str:
        """Identity of everything that shapes the raw OCR output (the cache key)."""
        return (f"tesseract {self.version}|vie-best {TESSDATA_BEST_VIE_SHA256[:12]}"
                f"|psm {PSM}|dpi {BASE_DPI}/{SMALL_TEXT_DPI}<{SMALL_LINE_PX}px")

@dataclass
class OcrLine:
    text: str                     # raw Tesseract text (clean_text is applied later)
    bbox: list[float]             # PDF points, top-left origin, on its page
    conf: float                   # mean word confidence, 0-100
    block: tuple[int, int]        # (Tesseract block, paragraph) -> one text block

@dataclass
class PageOcr:
    page: int
    dpi: int = BASE_DPI
    lines: list[OcrLine] = field(default_factory=list)
    error: str | None = None      # set when Tesseract failed on this page

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def _no_window() -> int:
    # The worker runs under pythonw.exe; don't flash a console per page.
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)

def find_engine() -> tuple[Engine | None, str]:
    """Locate Tesseract 5 + the pinned tessdata_best `vie` model.

    Returns (engine, "") or (None, reason). Priority for the binary:
    GULIB_TESSERACT env var > standard install dirs > PATH. The model is read
    from GULIB_TESSDATA if set, else the `tessdata` folder next to the binary.
    """
    candidates = [os.environ.get("GULIB_TESSERACT", ""), *_TESSERACT_PATHS]
    exe = next((Path(c) for c in candidates if c and Path(c).is_file()), None)
    if exe is None:
        found = shutil.which("tesseract")
        exe = Path(found) if found else None
    if exe is None:
        return None, ("tesseract not found (set GULIB_TESSERACT or install to "
                      + " / ".join(_TESSERACT_PATHS[:2]) + ")")
    tessdata = Path(os.environ.get("GULIB_TESSDATA") or exe.parent / "tessdata")
    model = tessdata / "vie.traineddata"
    if not model.is_file():
        return None, f"vie.traineddata not found in {tessdata}"
    if _sha256(model) != TESSDATA_BEST_VIE_SHA256:
        return None, f"{model} is not the tessdata_best vie model (sha256 mismatch)"
    try:
        out = subprocess.run([str(exe), "--version"], capture_output=True, text=True,
                             timeout=30, creationflags=_no_window())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"tesseract did not run ({exe}): {exc}"
    m = re.search(r"tesseract v?(\d+\.\d+\S*)", (out.stdout or "") + (out.stderr or ""))
    if not m:
        return None, f"could not read the tesseract version from {exe}"
    version = m.group(1)
    if not version.startswith("5."):
        return None, f"tesseract {version} found, version 5 required"
    return Engine(exe=exe, tessdata=tessdata, version=version), ""

def parse_tsv(tsv: str, dpi: int) -> list[OcrLine]:
    """Group Tesseract TSV words into lines (text, bbox in points, mean conf)."""
    rows = csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)
    lines: dict[tuple[int, int, int, int], dict] = {}
    for r in rows:
        if r.get("level") != "5":
            continue
        word = (r.get("text") or "").strip()
        try:
            conf = float(r["conf"])
            key = (int(r["page_num"]), int(r["block_num"]), int(r["par_num"]), int(r["line_num"]))
            left, top = int(r["left"]), int(r["top"])
            right, bottom = left + int(r["width"]), top + int(r["height"])
        except (KeyError, TypeError, ValueError):
            continue
        if not word or conf < 0:
            continue
        d = lines.setdefault(key, {"words": [], "confs": [], "box": [left, top, right, bottom]})
        d["words"].append(word)
        d["confs"].append(conf)
        b = d["box"]
        d["box"] = [min(b[0], left), min(b[1], top), max(b[2], right), max(b[3], bottom)]
    scale = 72.0 / dpi
    return [OcrLine(text=" ".join(d["words"]),
                    bbox=[round(c * scale, 2) for c in d["box"]],
                    conf=round(sum(d["confs"]) / len(d["confs"]), 2),
                    block=(key[1], key[2]))
            for key, d in sorted(lines.items())]

def median_line_height_px(lines: list[OcrLine], dpi: int) -> float | None:
    heights = [(l.bbox[3] - l.bbox[1]) * dpi / 72.0
               for l in lines if len(l.text) > LONG_LINE_CHARS]
    return statistics.median(heights) if heights else None

def run_tesseract(engine: Engine, image: Path, dpi: int) -> list[OcrLine]:
    """OCR one image file; raises RuntimeError on failure. Writes beside `image`."""
    outbase = image.with_suffix("")
    env = dict(os.environ, OMP_THREAD_LIMIT="1")   # we parallelise by process
    cmd = [str(engine.exe), str(image), str(outbase), "-l", "vie", "--psm", str(PSM),
           "--tessdata-dir", str(engine.tessdata), "tsv"]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                              timeout=PAGE_TIMEOUT_S, env=env, creationflags=_no_window())
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"tesseract timed out after {PAGE_TIMEOUT_S}s") from exc
    except OSError as exc:
        raise RuntimeError(f"tesseract did not run: {exc}") from exc
    tsv_path = outbase.with_name(outbase.name + ".tsv")
    try:
        if proc.returncode != 0 or not tsv_path.is_file():
            err = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
            raise RuntimeError(f"tesseract exit {proc.returncode}: {err[0]}")
        return parse_tsv(tsv_path.read_text(encoding="utf-8"), dpi)
    finally:
        tsv_path.unlink(missing_ok=True)

def ocr_page(engine: Engine, render, page_no: int, workdir: Path) -> PageOcr:
    """OCR one PDF page. `render(page_no, dpi, png_path)` draws the page image.

    Never raises: a failure is returned as PageOcr.error so one bad page can't
    stop the rest of the batch."""
    result = PageOcr(page=page_no)
    try:
        for dpi in (BASE_DPI, SMALL_TEXT_DPI):
            png = workdir / f"p{page_no}_{dpi}.png"
            try:
                render(page_no, dpi, png)
                lines = run_tesseract(engine, png, dpi)
            finally:
                png.unlink(missing_ok=True)
            result.dpi, result.lines = dpi, lines
            height = median_line_height_px(lines, dpi)
            if dpi == SMALL_TEXT_DPI or height is None or height >= SMALL_LINE_PX:
                break
    except Exception as exc:  # isolate per-page failure
        result.lines, result.error = [], str(exc) or type(exc).__name__
    return result

def clean_text(text: str) -> str:
    """Normalise recognised text for search: NFC + Vietnamese look-alike fixes.

    Deliberately NOT the VNI decoder used for text layers: Tesseract always
    emits Unicode, and stray Latin-1 letters in OCR noise would trip it."""
    return unicodedata.normalize("NFC", text).translate(_CHAR_FIXES)

@lru_cache(maxsize=1)
def lexicon() -> frozenset[str]:
    data = resources.files("gu_library_worker").joinpath("data/ocr_lexicon.txt")
    return frozenset(w for w in data.read_text(encoding="utf-8").split("\n") if w)

def page_verdict(lines: list[OcrLine], words: frozenset[str] | None = None
                 ) -> tuple[bool, str]:
    """(keep the text?, reason). `lines` must already be clean_text()-ed."""
    chars = sum(len("".join(l.text.split())) for l in lines)
    if chars < MIN_PAGE_CHARS:
        return False, f"too little text ({chars} chars)"
    conf = sum(l.conf for l in lines) / len(lines)
    if conf < MIN_PAGE_CONF:
        return False, f"low confidence ({conf:.0f})"
    tokens = [t.lower() for l in lines for t in _TOKEN_RE.findall(l.text)]
    if not tokens:
        return False, "no words"
    words = lexicon() if words is None else words
    oov = sum(1 for t in tokens if t not in words) / len(tokens)
    if oov > MAX_PAGE_OOV:
        return False, f"unrecognised words ({oov:.0%})"
    return True, ""
