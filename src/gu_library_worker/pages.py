# src/gu_library_worker/pages.py
from __future__ import annotations
from pathlib import Path
import re
import fitz  # PyMuPDF
from gu_library_worker.schema import Unit

def page_count(pdf_path: Path) -> int:
    with fitz.open(str(pdf_path)) as doc:
        return doc.page_count

def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()

def anchor_pages(units: list[Unit], pdf_path: Path) -> None:
    """Assign each unit's `page` by locating its leading text in the PDF.

    Units are in reading order, so search forward and keep the last hit as a
    monotonic floor. Mutates units in place. Fallback is the floor (>=1).
    """
    with fitz.open(str(pdf_path)) as doc:
        page_texts = [_normalize(page.get_text()) for page in doc]
    floor = 1
    for u in units:
        snippet = _normalize(u.text)[:40]
        found = None
        if snippet:
            for pno in range(floor - 1, len(page_texts)):
                if snippet in page_texts[pno]:
                    found = pno + 1
                    break
        if found is not None:
            u.page = found
            floor = found
        else:
            u.page = floor
