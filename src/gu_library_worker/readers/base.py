# src/gu_library_worker/readers/base.py
from __future__ import annotations
from dataclasses import dataclass
from gu_library_worker.schema import Unit

@dataclass
class Line:
    text: str
    page: int
    bbox: list[float] | None = None  # PDF coords (top-left); None for docx/pptx

@dataclass
class Extraction:
    kind: str             # legal | slide | prose
    units: list[Unit]
