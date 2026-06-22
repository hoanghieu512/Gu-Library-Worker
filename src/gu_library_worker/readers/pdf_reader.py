# src/gu_library_worker/readers/pdf_reader.py
from __future__ import annotations
from pathlib import Path
import re
import fitz  # PyMuPDF
from gu_library_worker.schema import Unit
from gu_library_worker.legal import has_legal_structure, parse_legal, _DIEU_RE, _CHUONG_RE
from .base import Line, Extraction

# Top/bottom bands (fraction of page height) where running headers/footers live.
# Bottom reaches up to 0.80 so the công báo footer cluster (page number + digital
# signature line, y0 ~= 700-745 on A4) is covered, not just the very edge.
_TOP_BAND = 0.12
_BOTTOM_BAND = 0.80
_DIGIT_RE = re.compile(r"\d+")

def _rect(bbox) -> list[float]:
    return [float(c) for c in bbox]

def _key(text: str) -> str:
    """Normalized + digit-masked key for repetition matching.

    Digits are masked so a header/footer whose only variation is numeric
    (`Số 363 + 364`, page number `4`, `Thời gian ký: 21.03.2024 ...`) collapses
    to one repeating key across pages.
    """
    return _DIGIT_RE.sub("#", re.sub(r"\s+", " ", text.strip()).lower())

def _is_structural(text: str) -> bool:
    """A line that starts a legal unit (Điều/Chương) is never running content."""
    return bool(_DIEU_RE.match(text) or _CHUONG_RE.match(text))

def _in_margin(y0: float, height: float) -> bool:
    return y0 < height * _TOP_BAND or y0 > height * _BOTTOM_BAND

def _read_pages(path: Path) -> tuple[list[list[list[tuple[str, list[float]]]]], list[float]]:
    """Read each page as a list of blocks; each block is a list of (line_text, line_bbox)."""
    page_blocks: list[list[list[tuple[str, list[float]]]]] = []
    page_heights: list[float] = []
    with fitz.open(str(path)) as doc:
        for page in doc:
            page_heights.append(float(page.rect.height))
            blocks: list[list[tuple[str, list[float]]]] = []
            for block in page.get_text("dict")["blocks"]:
                if "lines" not in block:
                    continue  # image / non-text block
                items: list[tuple[str, list[float]]] = []
                for ln in block["lines"]:
                    ltext = "".join(span["text"] for span in ln["spans"]).strip()
                    if ltext:
                        items.append((ltext, _rect(ln["bbox"])))
                if items:
                    blocks.append(items)
            page_blocks.append(blocks)
    return page_blocks, page_heights

def _detect_running(page_blocks, page_heights) -> set[str]:
    """Find running header/footer LINE keys by geometry + repetition.

    A non-structural line in the top/bottom margin band whose digit-masked key
    repeats on >= half the pages is running content. Working at line level (not
    block level) means a footer/signature/page-number/next-page-header that PyMuPDF
    reads between the last line of page N and the first of page N+1 is dropped
    BEFORE it can be stitched into a page-spanning Điều/Khoản. Content outside the
    bands, and any structural (Điều/Chương) line, is never considered — so a PDF
    without running headers (e.g. Bộ luật Dân sự) loses nothing.
    """
    num_pages = len(page_blocks)
    threshold = max(2, (num_pages + 1) // 2)  # majority of pages, min 2
    key_pages: dict[str, set[int]] = {}
    for pi, (blocks, height) in enumerate(zip(page_blocks, page_heights)):
        for block in blocks:
            for text, bbox in block:
                if _is_structural(text) or not _in_margin(bbox[1], height):
                    continue
                key_pages.setdefault(_key(text), set()).add(pi)
    return {k for k, pages in key_pages.items() if len(pages) >= threshold}

def _is_running(text: str, bbox: list[float], height: float, running: set[str]) -> bool:
    if _is_structural(text) or not _in_margin(bbox[1], height):
        return False  # never drop body content or a unit boundary
    return _key(text) in running

def _union(bboxes: list[list[float]]) -> list[float]:
    return [
        min(b[0] for b in bboxes), min(b[1] for b in bboxes),
        max(b[2] for b in bboxes), max(b[3] for b in bboxes),
    ]

def _pdf_lines(path: Path) -> tuple[list[Line], list[tuple[str, int, list[float]]]]:
    """Return (line-level for legal parsing, block-level for prose degrade).

    Running header/footer lines are removed per page at read time, so they
    never become junk units and never get injected into a unit whose text
    spans a page break.
    """
    page_blocks, page_heights = _read_pages(path)
    running = _detect_running(page_blocks, page_heights)
    lines: list[Line] = []
    blocks_out: list[tuple[str, int, list[float]]] = []
    for pno, (blocks, height) in enumerate(zip(page_blocks, page_heights), start=1):
        for block in blocks:
            kept = [(t, b) for (t, b) in block if not _is_running(t, b, height, running)]
            if not kept:
                continue
            for ltext, lbbox in kept:
                lines.append(Line(text=ltext, page=pno, bbox=lbbox))
            blocks_out.append(("\n".join(t for t, _ in kept), pno,
                               _union([b for _, b in kept])))
    return lines, blocks_out

def read_pdf(path: Path) -> Extraction:
    lines, blocks = _pdf_lines(path)
    if has_legal_structure(lines):
        return Extraction(kind="legal", units=parse_legal(lines))
    units = [Unit(type="paragraph", label="", path=[], text=text, page=pno, bbox=bbox)
             for text, pno, bbox in blocks]
    return Extraction(kind="prose", units=units)
