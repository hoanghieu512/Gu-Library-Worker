# src/gu_library_worker/readers/pdf_reader.py
from __future__ import annotations
from pathlib import Path
import fitz  # PyMuPDF
from gu_library_worker.schema import Unit
from gu_library_worker.legal import has_legal_structure, parse_legal
from .base import Line, Extraction

def _pdf_lines(path: Path) -> tuple[list[Line], list[tuple[str, int]]]:
    """Return (line-level for legal parsing, block-level for prose degrade)."""
    lines: list[Line] = []
    blocks: list[tuple[str, int]] = []
    with fitz.open(str(path)) as doc:
        for pno, page in enumerate(doc, start=1):
            for block in page.get_text("blocks"):
                btext = block[4].strip()
                if not btext:
                    continue
                blocks.append((btext, pno))
                for raw in btext.splitlines():
                    line = raw.strip()
                    if line:
                        lines.append(Line(text=line, page=pno))
    return lines, blocks

def read_pdf(path: Path) -> Extraction:
    lines, blocks = _pdf_lines(path)
    if has_legal_structure(lines):
        return Extraction(kind="legal", units=parse_legal(lines))
    units = [Unit(type="paragraph", label="", path=[], text=text, page=pno)
             for text, pno in blocks]
    return Extraction(kind="prose", units=units)
