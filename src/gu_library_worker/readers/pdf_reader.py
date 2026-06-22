# src/gu_library_worker/readers/pdf_reader.py
from __future__ import annotations
from pathlib import Path
import re
import fitz  # PyMuPDF
from gu_library_worker.schema import Unit
from gu_library_worker.legal import has_legal_structure, parse_legal
from .base import Line, Extraction

# Top/bottom band (fraction of page height) where running headers/footers live.
_MARGIN_FRACTION = 0.12
_NUMERIC_RE = re.compile(r"\d+")

def _rect(bbox) -> list[float]:
    return [float(c) for c in bbox]

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).lower()

def _read_pages(path: Path) -> tuple[list[list[tuple[str, list[float], list]]], list[float]]:
    """Read each page into text blocks: (block_text, block_bbox, [(line_text, line_bbox)])."""
    page_blocks: list[list[tuple[str, list[float], list]]] = []
    page_heights: list[float] = []
    with fitz.open(str(path)) as doc:
        for page in doc:
            page_heights.append(float(page.rect.height))
            blocks: list[tuple[str, list[float], list]] = []
            for block in page.get_text("dict")["blocks"]:
                if "lines" not in block:
                    continue  # image / non-text block
                items = []
                for ln in block["lines"]:
                    ltext = "".join(span["text"] for span in ln["spans"]).strip()
                    if ltext:
                        items.append((ltext, _rect(ln["bbox"])))
                if items:
                    btext = "\n".join(t for t, _ in items)
                    blocks.append((btext, _rect(block["bbox"]), items))
            page_blocks.append(blocks)
    return page_blocks, page_heights

def _in_margin(bbox: list[float], height: float) -> bool:
    return bbox[1] < height * _MARGIN_FRACTION or bbox[3] > height * (1.0 - _MARGIN_FRACTION)

def _detect_running(page_blocks, page_heights) -> tuple[set[str], bool]:
    """Find running headers/footers by geometry + repetition.

    A margin block whose whitespace-normalized text repeats on >= threshold
    pages is running content (catches the công báo header, footers, watermark
    text — no hardcoded strings). Bare page numbers vary per page, so they are
    detected as a class and dropped only when present on >= threshold pages.
    Content outside the margin band is never considered, so a PDF without
    running headers (e.g. Bộ luật Dân sự) loses nothing.
    """
    num_pages = len(page_blocks)
    threshold = max(2, (num_pages + 1) // 2)  # majority of pages, min 2
    text_pages: dict[str, set[int]] = {}
    numeric_pages: set[int] = set()
    for pi, (blocks, height) in enumerate(zip(page_blocks, page_heights)):
        for btext, bbox, _ in blocks:
            if not _in_margin(bbox, height):
                continue
            if _NUMERIC_RE.fullmatch(btext.strip()):
                numeric_pages.add(pi)
            text_pages.setdefault(_norm(btext), set()).add(pi)
    running = {t for t, pages in text_pages.items() if len(pages) >= threshold}
    drop_numeric = len(numeric_pages) >= threshold
    return running, drop_numeric

def _is_running(btext: str, bbox: list[float], height: float,
                running: set[str], drop_numeric: bool) -> bool:
    if not _in_margin(bbox, height):
        return False  # never drop body content
    if _norm(btext) in running:
        return True
    if drop_numeric and _NUMERIC_RE.fullmatch(btext.strip()):
        return True
    return False

def _pdf_lines(path: Path) -> tuple[list[Line], list[tuple[str, int, list[float]]]]:
    """Return (line-level for legal parsing, block-level for prose degrade).

    Running headers/footers are stripped here, before any text reaches a unit,
    so they neither become junk units nor get injected into article text when
    an Điều/Khoản spans a page break.
    """
    page_blocks, page_heights = _read_pages(path)
    running, drop_numeric = _detect_running(page_blocks, page_heights)
    lines: list[Line] = []
    blocks_out: list[tuple[str, int, list[float]]] = []
    for pno, (blocks, height) in enumerate(zip(page_blocks, page_heights), start=1):
        for btext, bbox, items in blocks:
            if _is_running(btext, bbox, height, running, drop_numeric):
                continue
            blocks_out.append((btext, pno, bbox))
            for ltext, lbbox in items:
                lines.append(Line(text=ltext, page=pno, bbox=lbbox))
    return lines, blocks_out

def read_pdf(path: Path) -> Extraction:
    lines, blocks = _pdf_lines(path)
    if has_legal_structure(lines):
        return Extraction(kind="legal", units=parse_legal(lines))
    units = [Unit(type="paragraph", label="", path=[], text=text, page=pno, bbox=bbox)
             for text, pno, bbox in blocks]
    return Extraction(kind="prose", units=units)
