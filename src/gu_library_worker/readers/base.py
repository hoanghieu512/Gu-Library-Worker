# src/gu_library_worker/readers/base.py
from __future__ import annotations
from dataclasses import dataclass
from gu_library_worker.schema import Unit

@dataclass
class Line:
    text: str
    page: int

@dataclass
class Extraction:
    kind: str             # legal | slide | prose
    units: list[Unit]
