# src/gu_library_worker/readers/pdf_reader.py
from __future__ import annotations
from pathlib import Path
import fitz  # PyMuPDF
from gu_library_worker.schema import Unit
from gu_library_worker.legal import has_legal_structure, parse_legal
from .base import Line, Extraction

def _rect(bbox) -> list[float]:
    return [float(c) for c in bbox]

def _pdf_lines(path: Path) -> tuple[list[Line], list[tuple[str, int, list[float]]]]:
    """Return (line-level for legal parsing, block-level for prose degrade).

    Uses get_text("dict") so each line/block carries its bbox (PDF points,
    top-left origin) — the source of the sidecar `bbox`.
    """
    lines: list[Line] = []
    blocks: list[tuple[str, int, list[float]]] = []
    with fitz.open(str(path)) as doc:
        for pno, page in enumerate(doc, start=1):
            for block in page.get_text("dict")["blocks"]:
                if "lines" not in block:
                    continue  # image / non-text block
                block_texts: list[str] = []
                for ln in block["lines"]:
                    ltext = "".join(span["text"] for span in ln["spans"]).strip()
                    if not ltext:
                        continue
                    lines.append(Line(text=ltext, page=pno, bbox=_rect(ln["bbox"])))
                    block_texts.append(ltext)
                if block_texts:
                    blocks.append(("\n".join(block_texts), pno, _rect(block["bbox"])))
    return lines, blocks

def read_pdf(path: Path) -> Extraction:
    lines, blocks = _pdf_lines(path)
    if has_legal_structure(lines):
        return Extraction(kind="legal", units=parse_legal(lines))
    units = [Unit(type="paragraph", label="", path=[], text=text, page=pno, bbox=bbox)
             for text, pno, bbox in blocks]
    return Extraction(kind="prose", units=units)
