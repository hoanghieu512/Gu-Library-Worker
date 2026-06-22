# src/gu_library_worker/legal.py
from __future__ import annotations
import re
from .schema import Unit
from .readers.base import Line

# An article boundary requires a dot right after the number ("Điều 201.").
# A reference such as "Điều 201 của Luật này" has no dot and is plain text,
# so it never starts a new `dieu` unit. (Applies to all VN legal text;
# DOCX articles also use the dotted form, so this does not change DOCX output.)
_DIEU_RE = re.compile(r"^\s*Điều\s+(\d+)\.\s*(.*)$")
_CHUONG_RE = re.compile(r"^\s*(Chương\s+[IVXLCDM\d]+)\b\s*(.*)$", re.IGNORECASE)
_KHOAN_RE = re.compile(r"^\s*(\d+)\s*[\.\)]\s+(.+)$")

def has_legal_structure(lines: list[Line]) -> bool:
    return any(_DIEU_RE.match(ln.text) for ln in lines)

def _chuong_label(raw: str) -> str:
    # normalize "Chương   I" -> "Chương I"
    return re.sub(r"\s+", " ", raw).strip()

def parse_legal(lines: list[Line]) -> list[Unit]:
    units: list[Unit] = []
    ancestors: list[str] = []          # e.g. ["Chương I"]
    cur_dieu: Unit | None = None        # open article (collecting lead text)
    cur_khoan: Unit | None = None       # open clause (collecting body)
    dieu_label: str | None = None       # label of the article khoản belong to

    def flush_open():
        nonlocal cur_dieu, cur_khoan
        cur_dieu = None
        cur_khoan = None

    for ln in lines:
        text = ln.text.strip()
        if not text:
            continue

        m_ch = _CHUONG_RE.match(text)
        if m_ch:
            label = _chuong_label(m_ch.group(1))
            units.append(Unit(type="heading", label=label,
                              path=list(ancestors), text=text, page=ln.page,
                              bbox=ln.bbox))
            ancestors = [label]
            dieu_label = None
            flush_open()
            continue

        m_d = _DIEU_RE.match(text)
        if m_d:
            dieu_label = f"Điều {m_d.group(1)}"
            cur_dieu = Unit(type="dieu", label=dieu_label,
                            path=list(ancestors), text=text, page=ln.page,
                            bbox=ln.bbox)
            units.append(cur_dieu)
            cur_khoan = None
            continue

        m_k = _KHOAN_RE.match(text)
        if m_k and dieu_label is not None:
            k_label = f"Khoản {m_k.group(1)}"
            cur_khoan = Unit(type="khoan", label=k_label,
                             path=ancestors + [dieu_label], text=text, page=ln.page,
                             bbox=ln.bbox)
            units.append(cur_khoan)
            continue

        # continuation line: append to the most recent open unit
        target = cur_khoan or cur_dieu
        if target is not None:
            target.text = f"{target.text}\n{text}"
        else:
            # text before any Điều (preamble) -> keep as paragraph, never lose it
            units.append(Unit(type="paragraph", label="",
                              path=list(ancestors), text=text, page=ln.page,
                              bbox=ln.bbox))
    return units
