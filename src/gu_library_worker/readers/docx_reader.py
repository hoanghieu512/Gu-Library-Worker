# src/gu_library_worker/readers/docx_reader.py
from __future__ import annotations
from pathlib import Path
from docx import Document as Docx
from gu_library_worker.schema import Unit
from gu_library_worker.legal import has_legal_structure, parse_legal
from .base import Line, Extraction

def _docx_lines(path: Path) -> list[Line]:
    doc = Docx(str(path))
    lines: list[Line] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            lines.append(Line(text=text, page=0))  # page anchored later
    return lines

def read_docx(path: Path) -> Extraction:
    lines = _docx_lines(path)
    if has_legal_structure(lines):
        return Extraction(kind="legal", units=parse_legal(lines))
    return Extraction(kind="prose", units=_prose_units(lines))

def _prose_units(lines: list[Line]) -> list[Unit]:
    units: list[Unit] = []
    for ln in lines:
        # short line with no terminal punctuation -> heading; else paragraph
        is_heading = len(ln.text) <= 60 and not ln.text.endswith((".", "?", "!", ":"))
        units.append(Unit(
            type="heading" if is_heading else "paragraph",
            label="", path=[], text=ln.text, page=0,
        ))
    return units
