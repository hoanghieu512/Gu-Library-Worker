# Gú's Library — M7 Mini-PC Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a stateless Python worker that polls `kho/_inbox/`, converts each valid original to a canonical PDF, extracts a schema-v1 sidecar JSON (text + Điều/Khoản structure + page anchors), and places the `.pdf`+`.json` pair into the correct subject folder — never losing text, never overwriting, never wrong-deleting.

**Architecture:** One scan pass = list `_inbox/` → input gate (extension/temp/hidden filter + size-stability check) → for each valid file: read subject prefix, convert to PDF (LibreOffice headless; original PDFs kept as-is), extract sidecar via a per-format reader (docx/pptx native, pdf direct), anchor pages against the canonical PDF, validate against the schema, then atomically write the pair into the subject folder (dedup with ` (1)` suffix) and delete the original. State is derived purely from the filesystem; the worker keeps no ledger. Heavy I/O (LibreOffice, real files) is isolated behind thin, mockable wrappers so the whole pipeline is unit-testable without LibreOffice installed.

**Tech Stack:** Python 3.11+, PyMuPDF (`pymupdf`/`fitz`), `python-docx`, `python-pptx`, LibreOffice headless (via `subprocess`), `pytest`.

---

## Schema contract (locked — from `Docs/gu-library-sidecar-schema.md`)

Document level (all required): `schemaVersion` (=1), `title` (filename minus `[môn]` prefix, minus extension), `source` (`share`|`watch`), `addedAt` (ISO-8601 with +07:00), `sourceFormat` (`pdf`|`docx`|`pptx`), `pageCount` (canonical PDF page count), `kind` (`legal`|`slide`|`prose`).

Unit level (every `units[]`, all required): `type` (`dieu`|`khoan`|`diem`|`slide`|`heading`|`paragraph`), `label` (may be `""`), `path` (list of ancestor labels, may be `[]`), `text` (never empty if the unit has text), `page` (1-indexed start page in the canonical PDF).

Three content kinds:
- **legal** — chain of `dieu`/`khoan` units, `path` carries `Chương`/`Điều`.
- **slide** (pptx origin) — one `slide` unit per slide, `label` `"Slide N"`, `page` = slide index (1 slide ≈ 1 PDF page), `path` `[]`.
- **prose** — `heading` + `paragraph` units, `path` carries chapter/section if detected else `[]`.

**Locked design decisions for this build (resolve ambiguity in the spec):**
1. **Legal granularity (no text duplication):** one `dieu` unit per article whose `text` = the article's lead text (from `Điều N…` up to the first clause; the *whole* article body if it has no numbered clauses); one `khoan` unit per numbered clause (`text` = clause body **including its điểm a)/b) inline** — điểm are not separate units in Phase 1, YAGNI). `Chương …` lines → one `heading` unit and pushed onto the ancestor stack for following articles. Text is partitioned across units, never duplicated, never lost.
2. **Page anchoring:** pptx → `page` = slide index; pdf → `page` from PyMuPDF directly; **docx → page resolved by searching the converted canonical PDF** for each unit's leading text (python-docx has no page info). Fallback `page = 1` (with last-found page as a monotonic floor).
3. **`source` derivation:** filename has a recognizable `[…]` prefix → `source = "share"`; no prefix → `source = "watch"` and the file goes to the `Chưa phân loại` subject.
4. **Legacy binary `.doc`/`.ppt`:** native libs cannot read them → convert to PDF and extract via the PDF reader (degrade path); `sourceFormat` normalized to `docx`/`pptx`.
5. **`bbox` is OUT** of this build (Task 0 decides whether a follow-up adds it).

---

## File Structure

```
gu-library-worker/
  pyproject.toml                       # deps + pytest config
  .gitignore
  README.md
  src/gu_library_worker/
    __init__.py
    config.py                          # Paths + constants (extensions, temp suffixes, stability interval)
    prefix.py                          # parse [<môn>] prefix → subject + clean name + source
    intake.py                          # input gate: name filter + size-stability check
    schema.py                          # Unit/Document models, to_sidecar, validate_sidecar
    legal.py                           # text-lines → dieu/khoan/heading units (shared, Vietnamese law)
    readers/
      __init__.py
      base.py                          # Extraction dataclass + Line dataclass
      docx_reader.py                   # python-docx → Extraction (page=0 placeholder)
      pptx_reader.py                   # python-pptx → slide Extraction
      pdf_reader.py                    # PyMuPDF → legal-or-prose Extraction (page set)
    pages.py                           # anchor_pages() for docx + page_count()
    convert.py                         # LibreOffice headless subprocess wrapper
    naming.py                          # target path resolution + (1) dedup with in-scan reservations
    writer.py                          # write pair + delete original (outputs-before-delete)
    pipeline.py                        # process_one_file(): read→anchor→build→validate
    scan.py                            # scan_once(): list inbox, gate, dispatch, error isolation
    __main__.py                        # CLI entry: python -m gu_library_worker --kho <path>
  scripts/
    register-task.ps1                  # Windows Scheduled Task registration
  tests/
    conftest.py                        # fixture builders (make_docx, make_pptx, make_pdf, kho)
    test_prefix.py
    test_intake.py
    test_schema.py
    test_legal.py
    test_docx_reader.py
    test_pptx_reader.py
    test_pdf_reader.py
    test_pages.py
    test_convert.py
    test_naming.py
    test_writer.py
    test_scan.py                       # end-to-end with mocked converter
    test_smoke_real.py                 # 5 real files (skipped unless GULIB_SMOKE_KHO set)
```

---

## Task 0: Highlight spike — decide `bbox` (decision gate, no worker code)

This runs in the **app** repo's Viewer, in parallel; it does **not** block Tasks 1–19. It must be resolved before the schema is declared "final".

- [ ] **Step 1: Run the spike**

In the Gú's Library app Viewer, attempt to draw a highlight overlay on a known text span of one PDF (use the PDF render library already chosen for M5). PyMuPDF can emit per-span text coordinates (`page.get_text("dict")` → `spans[].bbox`), so the worker *can* produce coordinates if the Viewer can consume them.

- [ ] **Step 2: Record the decision**

Append the outcome to `Docs/gu-library-sidecar-schema.md` under "Đã CHỐT / để NGỎ":
- **Feasible** → schema gains a `bbox` field → do the follow-up "Task 20: add `bbox`" and re-run the worker over the ~5-file kho.
- **Not feasible** → drop highlight from Phase 2; schema stays anchored at `page`; close this gate.

- [ ] **Step 3: Commit the decision**

```bash
git add Docs/gu-library-sidecar-schema.md
git commit -m "docs: record bbox/highlight spike decision"
```

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `README.md`
- Create: `src/gu_library_worker/__init__.py`, `src/gu_library_worker/readers/__init__.py`
- Create: `tests/conftest.py` (empty stub for now)

- [ ] **Step 1: Create the package metadata**

`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "gu-library-worker"
version = "0.1.0"
description = "Gú's Library mini-PC worker: convert + extract sidecar JSON"
requires-python = ">=3.11"
dependencies = [
    "pymupdf>=1.24",
    "python-docx>=1.1",
    "python-pptx>=0.6.23",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.gitignore`**

```gitignore
__pycache__/
*.pyc
.venv/
.pytest_cache/
*.egg-info/
build/
dist/
/tmp/
```

- [ ] **Step 3: Create empty package files**

`src/gu_library_worker/__init__.py`:
```python
"""Gú's Library mini-PC worker."""
__version__ = "0.1.0"
```

`src/gu_library_worker/readers/__init__.py`:
```python
```

`tests/conftest.py`:
```python
```

`README.md`:
```markdown
# gu-library-worker

Mini-PC worker for Gú's Library: polls `kho/_inbox/`, converts originals to PDF,
extracts a schema-v1 sidecar JSON, and files the pair into the subject folder.

See `Docs/superpowers/plans/2026-06-21-gu-library-m7-worker.md` and
`Docs/gu-library-sidecar-schema.md`.
```

- [ ] **Step 4: Create venv, install, verify pytest collects nothing**

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest -q
```
Expected: `no tests ran` (exit 0 or 5), and `import gu_library_worker` works.

- [ ] **Step 5: Commit**

```bash
git init
git add -A
git commit -m "chore: scaffold gu-library-worker python package"
```

---

## Task 2: Config module (paths + constants)

**Files:**
- Create: `src/gu_library_worker/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from pathlib import Path
from gu_library_worker.config import Paths, ACCEPTED_EXTENSIONS, TEMP_SUFFIXES, UNCLASSIFIED

def test_paths_derive_inbox_from_kho(tmp_path):
    p = Paths(kho_root=tmp_path)
    assert p.inbox == tmp_path / "_inbox"

def test_subject_dir_creates_under_kho(tmp_path):
    p = Paths(kho_root=tmp_path)
    assert p.subject_dir("Luật Công chứng") == tmp_path / "Luật Công chứng"
    assert p.subject_dir(UNCLASSIFIED) == tmp_path / "Chưa phân loại"

def test_constants_shapes():
    assert ACCEPTED_EXTENSIONS == {".pdf", ".doc", ".docx", ".ppt", ".pptx"}
    assert ".tmp" in TEMP_SUFFIXES and ".crdownload" in TEMP_SUFFIXES
    assert UNCLASSIFIED == "Chưa phân loại"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: gu_library_worker.config`.

- [ ] **Step 3: Write the implementation**

```python
# src/gu_library_worker/config.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

ACCEPTED_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx"}
TEMP_SUFFIXES = {".tmp", ".crdownload"}
# names containing this token are Syncthing in-progress temp files
SYNCTHING_TOKEN = ".syncthing."
UNCLASSIFIED = "Chưa phân loại"

# stability check: read size twice this many seconds apart
STABILITY_INTERVAL_SECONDS = 3.0

# map original extension -> sourceFormat enum (pdf|docx|pptx)
SOURCE_FORMAT = {
    ".pdf": "pdf",
    ".doc": "docx",
    ".docx": "docx",
    ".ppt": "pptx",
    ".pptx": "pptx",
}

@dataclass(frozen=True)
class Paths:
    kho_root: Path

    @property
    def inbox(self) -> Path:
        return self.kho_root / "_inbox"

    def subject_dir(self, subject: str) -> Path:
        return self.kho_root / subject
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/gu_library_worker/config.py tests/test_config.py
git commit -m "feat: config paths and constants"
```

---

## Task 3: Prefix parser

**Files:**
- Create: `src/gu_library_worker/prefix.py`
- Test: `tests/test_prefix.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prefix.py
from gu_library_worker.prefix import parse_prefix, Parsed

def test_share_prefix():
    r = parse_prefix("[Tố tụng Hình sự] bai-giang.pdf")
    assert r == Parsed(subject="Tố tụng Hình sự", clean_name="bai-giang.pdf", source="share")

def test_unclassified_prefix():
    r = parse_prefix("[Chưa phân loại] x.docx")
    assert r.subject == "Chưa phân loại"
    assert r.source == "share"
    assert r.clean_name == "x.docx"

def test_no_prefix_is_watch_and_unclassified():
    r = parse_prefix("ngau-nhien.pdf")
    assert r.subject == "Chưa phân loại"
    assert r.source == "watch"
    assert r.clean_name == "ngau-nhien.pdf"

def test_prefix_with_extra_spaces():
    r = parse_prefix("[Luật Công chứng]   spaced.pdf")
    assert r.subject == "Luật Công chứng"
    assert r.clean_name == "spaced.pdf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_prefix.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

```python
# src/gu_library_worker/prefix.py
from __future__ import annotations
import re
from dataclasses import dataclass
from .config import UNCLASSIFIED

_PREFIX_RE = re.compile(r"^\[(?P<subject>[^\]]+)\]\s*(?P<rest>.+)$")

@dataclass(frozen=True)
class Parsed:
    subject: str
    clean_name: str
    source: str  # "share" | "watch"

def parse_prefix(filename: str) -> Parsed:
    m = _PREFIX_RE.match(filename)
    if m:
        return Parsed(
            subject=m.group("subject").strip(),
            clean_name=m.group("rest").strip(),
            source="share",
        )
    return Parsed(subject=UNCLASSIFIED, clean_name=filename, source="watch")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_prefix.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/gu_library_worker/prefix.py tests/test_prefix.py
git commit -m "feat: parse subject prefix and derive source"
```

---

## Task 4: Intake gate (name filter + stability check)

**Files:**
- Create: `src/gu_library_worker/intake.py`
- Test: `tests/test_intake.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_intake.py
from gu_library_worker.intake import is_candidate_name, wait_until_stable

def test_accepts_supported_extensions():
    assert is_candidate_name("[Môn] a.pdf")
    assert is_candidate_name("b.docx")
    assert is_candidate_name("c.PPTX")  # case-insensitive

def test_rejects_temp_and_unknown():
    assert not is_candidate_name("a.pdf.tmp")
    assert not is_candidate_name("b.crdownload")
    assert not is_candidate_name("notes.txt")
    assert not is_candidate_name("archive.zip")

def test_rejects_syncthing_and_hidden():
    assert not is_candidate_name(".syncthing.a.pdf.tmp")
    assert not is_candidate_name(".hidden.pdf")

def test_stability_true_when_size_holds(tmp_path):
    f = tmp_path / "x.pdf"
    f.write_bytes(b"1234")
    sizes = iter([4, 4])
    assert wait_until_stable(f, sleep=lambda s: None,
                             _stat_size=lambda p: next(sizes)) is True

def test_stability_false_when_size_changes(tmp_path):
    f = tmp_path / "x.pdf"
    f.write_bytes(b"1234")
    sizes = iter([4, 9])
    assert wait_until_stable(f, sleep=lambda s: None,
                             _stat_size=lambda p: next(sizes)) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_intake.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

```python
# src/gu_library_worker/intake.py
from __future__ import annotations
import os
import time
from pathlib import Path
from typing import Callable
from .config import ACCEPTED_EXTENSIONS, TEMP_SUFFIXES, SYNCTHING_TOKEN, STABILITY_INTERVAL_SECONDS

def is_candidate_name(name: str) -> bool:
    """Pure filename gate. No filesystem access."""
    if name.startswith("."):
        return False
    lower = name.lower()
    if SYNCTHING_TOKEN in lower:
        return False
    for suffix in TEMP_SUFFIXES:
        if lower.endswith(suffix):
            return False
    return Path(lower).suffix in ACCEPTED_EXTENSIONS

def wait_until_stable(
    path: Path,
    *,
    interval: float = STABILITY_INTERVAL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    _stat_size: Callable[[Path], int] = lambda p: os.path.getsize(p),
) -> bool:
    """True if the file size is identical across two reads `interval` apart."""
    try:
        first = _stat_size(path)
        sleep(interval)
        second = _stat_size(path)
    except OSError:
        return False
    return first == second
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_intake.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/gu_library_worker/intake.py tests/test_intake.py
git commit -m "feat: input gate name filter and stability check"
```

---

## Task 5: Schema model + validator

**Files:**
- Create: `src/gu_library_worker/schema.py`
- Test: `tests/test_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_schema.py
from gu_library_worker.schema import (
    Unit, Document, to_sidecar, validate_sidecar, SCHEMA_VERSION,
)

def _doc():
    return Document(
        title="Luật X", source="share", sourceFormat="docx", kind="legal",
        addedAt="2026-06-21T10:30:00+07:00", pageCount=3,
        units=[Unit(type="dieu", label="Điều 1", path=["Chương I"], text="Nội dung", page=1)],
    )

def test_to_sidecar_shape():
    d = to_sidecar(_doc())
    assert d["schemaVersion"] == SCHEMA_VERSION
    assert d["title"] == "Luật X"
    assert d["units"][0] == {
        "type": "dieu", "label": "Điều 1", "path": ["Chương I"],
        "text": "Nội dung", "page": 1,
    }

def test_validate_accepts_good():
    assert validate_sidecar(to_sidecar(_doc())) == []

def test_validate_flags_missing_field():
    bad = to_sidecar(_doc())
    del bad["pageCount"]
    errors = validate_sidecar(bad)
    assert any("pageCount" in e for e in errors)

def test_validate_flags_bad_unit_type_and_empty_text():
    bad = to_sidecar(_doc())
    bad["units"][0]["type"] = "nonsense"
    bad["units"][0]["text"] = ""
    errors = validate_sidecar(bad)
    assert any("type" in e for e in errors)
    assert any("text" in e for e in errors)

def test_validate_flags_non_positive_page():
    bad = to_sidecar(_doc())
    bad["units"][0]["page"] = 0
    assert any("page" in e for e in validate_sidecar(bad))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_schema.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

```python
# src/gu_library_worker/schema.py
from __future__ import annotations
from dataclasses import dataclass, field

SCHEMA_VERSION = 1
VALID_UNIT_TYPES = {"dieu", "khoan", "diem", "slide", "heading", "paragraph"}
VALID_KINDS = {"legal", "slide", "prose"}
VALID_SOURCE_FORMATS = {"pdf", "docx", "pptx"}
VALID_SOURCES = {"share", "watch"}

@dataclass
class Unit:
    type: str
    label: str
    path: list[str]
    text: str
    page: int

@dataclass
class Document:
    title: str
    source: str
    sourceFormat: str
    kind: str
    units: list[Unit] = field(default_factory=list)
    addedAt: str = ""
    pageCount: int = 0

def to_sidecar(doc: Document) -> dict:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "title": doc.title,
        "source": doc.source,
        "addedAt": doc.addedAt,
        "sourceFormat": doc.sourceFormat,
        "pageCount": doc.pageCount,
        "kind": doc.kind,
        "units": [
            {
                "type": u.type,
                "label": u.label,
                "path": list(u.path),
                "text": u.text,
                "page": u.page,
            }
            for u in doc.units
        ],
    }

def validate_sidecar(data: dict) -> list[str]:
    """Return a list of human-readable errors; empty means valid."""
    errors: list[str] = []
    required = {
        "schemaVersion": int, "title": str, "source": str, "addedAt": str,
        "sourceFormat": str, "pageCount": int, "kind": str, "units": list,
    }
    for key, typ in required.items():
        if key not in data:
            errors.append(f"missing field: {key}")
        elif not isinstance(data[key], typ):
            errors.append(f"field {key} wrong type: expected {typ.__name__}")
    if errors:
        return errors  # shape broken; deeper checks unsafe

    if data["schemaVersion"] != SCHEMA_VERSION:
        errors.append(f"schemaVersion must be {SCHEMA_VERSION}")
    if data["source"] not in VALID_SOURCES:
        errors.append(f"source invalid: {data['source']}")
    if data["sourceFormat"] not in VALID_SOURCE_FORMATS:
        errors.append(f"sourceFormat invalid: {data['sourceFormat']}")
    if data["kind"] not in VALID_KINDS:
        errors.append(f"kind invalid: {data['kind']}")
    if data["pageCount"] < 1:
        errors.append("pageCount must be >= 1")
    if not data["units"]:
        errors.append("units must not be empty")

    for i, u in enumerate(data["units"]):
        where = f"units[{i}]"
        for key, typ in {"type": str, "label": str, "path": list, "text": str, "page": int}.items():
            if key not in u:
                errors.append(f"{where} missing {key}")
            elif not isinstance(u[key], typ):
                errors.append(f"{where} {key} wrong type")
        if u.get("type") not in VALID_UNIT_TYPES:
            errors.append(f"{where} type invalid: {u.get('type')}")
        if not u.get("text"):
            errors.append(f"{where} text must not be empty")
        if isinstance(u.get("page"), int) and u["page"] < 1:
            errors.append(f"{where} page must be >= 1")
    return errors
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_schema.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/gu_library_worker/schema.py tests/test_schema.py
git commit -m "feat: sidecar schema model and validator"
```

---

## Task 6: Legal parser (text-lines → units)

**Files:**
- Create: `src/gu_library_worker/readers/base.py`
- Create: `src/gu_library_worker/legal.py`
- Test: `tests/test_legal.py`

The parser consumes ordered `Line(text, page)` items and emits `Unit`s per the locked granularity rule. `has_legal_structure()` tells callers whether legal parsing applies (≥1 `Điều`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_legal.py
from gu_library_worker.readers.base import Line
from gu_library_worker.legal import has_legal_structure, parse_legal

def _lines(texts):
    return [Line(text=t, page=1) for t in texts]

def test_detects_legal():
    assert has_legal_structure(_lines(["Chương I", "Điều 1. Phạm vi"]))
    assert not has_legal_structure(_lines(["Mở đầu", "Một đoạn văn xuôi."]))

def test_article_without_clauses_is_one_dieu():
    units = parse_legal(_lines([
        "Chương I QUY ĐỊNH CHUNG",
        "Điều 1. Phạm vi điều chỉnh",
        "Luật này quy định về công chứng.",
    ]))
    types = [(u.type, u.label) for u in units]
    assert ("heading", "Chương I") in types
    dieu = [u for u in units if u.type == "dieu"]
    assert len(dieu) == 1 and dieu[0].label == "Điều 1"
    assert dieu[0].path == ["Chương I"]
    assert "Phạm vi điều chỉnh" in dieu[0].text

def test_article_with_clauses_splits_into_khoan():
    units = parse_legal(_lines([
        "Điều 2. Giải thích từ ngữ",
        "Trong Luật này, các từ ngữ được hiểu như sau:",
        "1. Công chứng là việc công chứng viên chứng nhận.",
        "2. Công chứng viên là người đủ điều kiện.",
    ]))
    dieu = [u for u in units if u.type == "dieu"]
    khoan = [u for u in units if u.type == "khoan"]
    assert len(dieu) == 1 and dieu[0].label == "Điều 2"
    assert [k.label for k in khoan] == ["Khoản 1", "Khoản 2"]
    assert khoan[0].path == ["Điều 2"]
    assert "Công chứng là việc" in khoan[0].text
    # lead text stays on the dieu, clause text does not duplicate onto it
    assert "Công chứng là việc" not in dieu[0].text

def test_no_text_lost_total_chars():
    src = ["Điều 1. Tiêu đề", "1. Một.", "2. Hai."]
    units = parse_legal(_lines(src))
    joined = " ".join(u.text for u in units)
    for token in ["Tiêu đề", "Một", "Hai"]:
        assert token in joined
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_legal.py -q`
Expected: FAIL — modules not found.

- [ ] **Step 3: Write the base types**

```python
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
```

- [ ] **Step 4: Write the legal parser**

```python
# src/gu_library_worker/legal.py
from __future__ import annotations
import re
from .schema import Unit
from .readers.base import Line

_DIEU_RE = re.compile(r"^\s*Điều\s+(\d+)\b[\.\:]?\s*(.*)$")
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
            title = m_ch.group(2).strip()
            units.append(Unit(type="heading", label=label,
                              path=list(ancestors), text=text, page=ln.page))
            ancestors = [label]
            dieu_label = None
            flush_open()
            continue

        m_d = _DIEU_RE.match(text)
        if m_d:
            dieu_label = f"Điều {m_d.group(1)}"
            cur_dieu = Unit(type="dieu", label=dieu_label,
                            path=list(ancestors), text=text, page=ln.page)
            units.append(cur_dieu)
            cur_khoan = None
            continue

        m_k = _KHOAN_RE.match(text)
        if m_k and dieu_label is not None:
            k_label = f"Khoản {m_k.group(1)}"
            cur_khoan = Unit(type="khoan", label=k_label,
                             path=ancestors + [dieu_label], text=text, page=ln.page)
            units.append(cur_khoan)
            continue

        # continuation line: append to the most recent open unit
        target = cur_khoan or cur_dieu
        if target is not None:
            target.text = f"{target.text}\n{text}"
        else:
            # text before any Điều (preamble) -> keep as paragraph, never lose it
            units.append(Unit(type="paragraph", label="",
                              path=list(ancestors), text=text, page=ln.page))
    return units
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_legal.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add src/gu_library_worker/readers/base.py src/gu_library_worker/legal.py tests/test_legal.py
git commit -m "feat: vietnamese legal text-line parser"
```

---

## Task 7: DOCX reader

**Files:**
- Create: `src/gu_library_worker/readers/docx_reader.py`
- Test: `tests/test_docx_reader.py`
- Modify: `tests/conftest.py` (add `make_docx` builder)

DOCX units get `page = 0` (placeholder); Task 10 anchors them against the converted PDF.

- [ ] **Step 1: Add the fixture builder to conftest**

```python
# tests/conftest.py
import pytest
from docx import Document as Docx
from pptx import Presentation
from pptx.util import Inches
import fitz  # PyMuPDF

@pytest.fixture
def make_docx(tmp_path):
    def _make(name: str, paragraphs: list[str]) -> "pathlib.Path":
        d = Docx()
        for p in paragraphs:
            d.add_paragraph(p)
        out = tmp_path / name
        d.save(out)
        return out
    return _make

@pytest.fixture
def make_pptx(tmp_path):
    def _make(name: str, slide_texts: list[str]) -> "pathlib.Path":
        prs = Presentation()
        blank = prs.slide_layouts[6]
        for t in slide_texts:
            slide = prs.slides.add_slide(blank)
            box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(2))
            box.text_frame.text = t
        out = tmp_path / name
        prs.save(out)
        return out
    return _make

@pytest.fixture
def make_pdf(tmp_path):
    def _make(name: str, pages: list[str]) -> "pathlib.Path":
        doc = fitz.open()
        for body in pages:
            page = doc.new_page()
            page.insert_text((72, 72), body, fontsize=12)
        out = tmp_path / name
        doc.save(out)
        doc.close()
        return out
    return _make
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_docx_reader.py
from gu_library_worker.readers.docx_reader import read_docx

def test_legal_docx_yields_dieu_and_khoan(make_docx):
    path = make_docx("law.docx", [
        "Chương I QUY ĐỊNH CHUNG",
        "Điều 1. Phạm vi điều chỉnh",
        "Luật này quy định về công chứng.",
        "Điều 2. Giải thích từ ngữ",
        "1. Công chứng là việc chứng nhận.",
        "2. Công chứng viên là người đủ điều kiện.",
    ])
    ext = read_docx(path)
    assert ext.kind == "legal"
    labels = [(u.type, u.label) for u in ext.units]
    assert ("dieu", "Điều 1") in labels
    assert ("dieu", "Điều 2") in labels
    assert ("khoan", "Khoản 1") in labels
    assert all(u.page == 0 for u in ext.units)  # not anchored yet

def test_prose_docx_degrades_to_paragraphs(make_docx):
    path = make_docx("notes.docx", [
        "Giới thiệu môn học",
        "Đây là đoạn mở đầu của giáo trình.",
        "Đoạn thứ hai tiếp tục nội dung.",
    ])
    ext = read_docx(path)
    assert ext.kind == "prose"
    assert all(u.type in {"paragraph", "heading"} for u in ext.units)
    joined = " ".join(u.text for u in ext.units)
    assert "đoạn mở đầu" in joined
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_docx_reader.py -q`
Expected: FAIL — module not found.

- [ ] **Step 4: Write the implementation**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_docx_reader.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add src/gu_library_worker/readers/docx_reader.py tests/test_docx_reader.py tests/conftest.py
git commit -m "feat: docx reader with legal and prose paths"
```

---

## Task 8: PPTX reader

**Files:**
- Create: `src/gu_library_worker/readers/pptx_reader.py`
- Test: `tests/test_pptx_reader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pptx_reader.py
from gu_library_worker.readers.pptx_reader import read_pptx

def test_one_unit_per_slide_with_page_anchor(make_pptx):
    path = make_pptx("deck.pptx", ["Slide một nội dung", "Slide hai nội dung", "Slide ba"])
    ext = read_pptx(path)
    assert ext.kind == "slide"
    assert len(ext.units) == 3
    assert [u.label for u in ext.units] == ["Slide 1", "Slide 2", "Slide 3"]
    assert [u.page for u in ext.units] == [1, 2, 3]
    assert all(u.type == "slide" and u.path == [] for u in ext.units)
    assert "Slide một" in ext.units[0].text

def test_empty_slide_keeps_unit_with_placeholder_text(make_pptx):
    path = make_pptx("deck.pptx", [""])
    ext = read_pptx(path)
    assert len(ext.units) == 1
    assert ext.units[0].text  # never empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_pptx_reader.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

```python
# src/gu_library_worker/readers/pptx_reader.py
from __future__ import annotations
from pathlib import Path
from pptx import Presentation
from gu_library_worker.schema import Unit
from .base import Extraction

def _slide_text(slide) -> str:
    parts: list[str] = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                line = "".join(run.text for run in para.runs).strip()
                if line:
                    parts.append(line)
    return "\n".join(parts)

def read_pptx(path: Path) -> Extraction:
    prs = Presentation(str(path))
    units: list[Unit] = []
    for i, slide in enumerate(prs.slides, start=1):
        text = _slide_text(slide) or f"Slide {i}"  # never empty
        units.append(Unit(type="slide", label=f"Slide {i}",
                          path=[], text=text, page=i))
    return Extraction(kind="slide", units=units)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_pptx_reader.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/gu_library_worker/readers/pptx_reader.py tests/test_pptx_reader.py
git commit -m "feat: pptx reader, one unit per slide"
```

---

## Task 9: PDF reader (direct extraction + degrade)

**Files:**
- Create: `src/gu_library_worker/readers/pdf_reader.py`
- Test: `tests/test_pdf_reader.py`

PDF is the hardest case: extract text lines with their real page from PyMuPDF, try legal parsing, else degrade to one `paragraph` per text block — never losing text.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pdf_reader.py
from gu_library_worker.readers.pdf_reader import read_pdf

def test_legal_pdf_extracts_dieu(make_pdf):
    path = make_pdf("law.pdf", [
        "Điều 1. Phạm vi điều chỉnh\nLuật này quy định về công chứng.",
        "Điều 2. Giải thích từ ngữ\n1. Công chứng là việc chứng nhận.",
    ])
    ext = read_pdf(path)
    assert ext.kind == "legal"
    dieu = [u for u in ext.units if u.type == "dieu"]
    assert {u.label for u in dieu} == {"Điều 1", "Điều 2"}
    # page anchors come from the real PDF pages
    assert dieu[0].page == 1
    assert dieu[1].page == 2

def test_prose_pdf_degrades_without_losing_text(make_pdf):
    path = make_pdf("doc.pdf", [
        "Giới thiệu chung về môn học.\nĐoạn nội dung đầu tiên.",
        "Trang hai có thêm nội dung quan trọng.",
    ])
    ext = read_pdf(path)
    assert ext.kind == "prose"
    assert all(u.type == "paragraph" for u in ext.units)
    joined = " ".join(u.text for u in ext.units)
    assert "Đoạn nội dung đầu tiên" in joined
    assert "Trang hai" in joined
    # page anchors preserved
    assert any(u.page == 2 for u in ext.units)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_pdf_reader.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_pdf_reader.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/gu_library_worker/readers/pdf_reader.py tests/test_pdf_reader.py
git commit -m "feat: pdf reader with legal extraction and prose degrade"
```

---

## Task 10: Page anchoring + page count

**Files:**
- Create: `src/gu_library_worker/pages.py`
- Test: `tests/test_pages.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pages.py
from gu_library_worker.schema import Unit
from gu_library_worker.pages import anchor_pages, page_count

def test_page_count(make_pdf):
    path = make_pdf("x.pdf", ["a", "b", "c"])
    assert page_count(path) == 3

def test_anchor_assigns_pages_by_text_search(make_pdf):
    pdf = make_pdf("x.pdf", [
        "Điều 1. Phạm vi điều chỉnh nằm ở trang một.",
        "Điều 2. Giải thích từ ngữ nằm ở trang hai.",
    ])
    units = [
        Unit(type="dieu", label="Điều 1", path=[], text="Điều 1. Phạm vi điều chỉnh", page=0),
        Unit(type="dieu", label="Điều 2", path=[], text="Điều 2. Giải thích từ ngữ", page=0),
    ]
    anchor_pages(units, pdf)
    assert units[0].page == 1
    assert units[1].page == 2

def test_anchor_falls_back_to_floor_when_not_found(make_pdf):
    pdf = make_pdf("x.pdf", ["chỉ một trang nội dung"])
    units = [Unit(type="paragraph", label="", path=[], text="văn bản không có trong pdf", page=0)]
    anchor_pages(units, pdf)
    assert units[0].page == 1  # fallback never below 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_pages.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_pages.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/gu_library_worker/pages.py tests/test_pages.py
git commit -m "feat: docx page anchoring and pdf page count"
```

---

## Task 11: Converter (LibreOffice headless wrapper)

**Files:**
- Create: `src/gu_library_worker/convert.py`
- Test: `tests/test_convert.py`

Thin, mockable subprocess wrapper. Unit tests mock `subprocess.run` and the filesystem; real conversion runs in the smoke test on the mini PC.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_convert.py
import subprocess
import pytest
from pathlib import Path
from gu_library_worker.convert import to_pdf, ConversionError, build_command

def test_build_command_shape(tmp_path):
    cmd = build_command(tmp_path / "in.docx", tmp_path, soffice="soffice")
    assert cmd[0] == "soffice"
    assert "--headless" in cmd and "--convert-to" in cmd
    assert str(tmp_path / "in.docx") in cmd

def test_to_pdf_returns_output_path(tmp_path, monkeypatch):
    src = tmp_path / "in.docx"
    src.write_bytes(b"x")
    outdir = tmp_path / "out"
    outdir.mkdir()
    expected = outdir / "in.pdf"

    def fake_run(cmd, **kw):
        expected.write_bytes(b"%PDF-1.4\n")  # simulate LibreOffice output
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert to_pdf(src, outdir, soffice="soffice") == expected

def test_to_pdf_raises_when_no_output(tmp_path, monkeypatch):
    src = tmp_path / "in.docx"
    src.write_bytes(b"x")
    outdir = tmp_path / "out"
    outdir.mkdir()
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", ""))
    with pytest.raises(ConversionError):
        to_pdf(src, outdir, soffice="soffice")

def test_to_pdf_raises_on_nonzero(tmp_path, monkeypatch):
    src = tmp_path / "in.docx"
    src.write_bytes(b"x")
    outdir = tmp_path / "out"
    outdir.mkdir()
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "boom"))
    with pytest.raises(ConversionError):
        to_pdf(src, outdir, soffice="soffice")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_convert.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

```python
# src/gu_library_worker/convert.py
from __future__ import annotations
import subprocess
from pathlib import Path

DEFAULT_SOFFICE = "soffice"  # on PATH; override via CLI/env on the mini PC

class ConversionError(RuntimeError):
    pass

def build_command(src: Path, outdir: Path, soffice: str = DEFAULT_SOFFICE) -> list[str]:
    return [
        soffice, "--headless", "--norestore",
        "--convert-to", "pdf",
        "--outdir", str(outdir),
        str(src),
    ]

def to_pdf(src: Path, outdir: Path, soffice: str = DEFAULT_SOFFICE,
           timeout: float = 180.0) -> Path:
    """Convert `src` to a PDF in `outdir`. Returns the output path or raises."""
    cmd = build_command(src, outdir, soffice)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ConversionError(f"LibreOffice failed to run: {exc}") from exc
    if result.returncode != 0:
        raise ConversionError(f"LibreOffice exit {result.returncode}: {result.stderr}")
    out = outdir / (src.stem + ".pdf")
    if not out.exists() or out.stat().st_size == 0:
        raise ConversionError(f"expected PDF not produced: {out}")
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_convert.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/gu_library_worker/convert.py tests/test_convert.py
git commit -m "feat: libreoffice headless pdf converter wrapper"
```

---

## Task 12: Naming + dedup

**Files:**
- Create: `src/gu_library_worker/naming.py`
- Test: `tests/test_naming.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_naming.py
from gu_library_worker.naming import resolve_target_stems, Reservations

def test_basic_pair_names(tmp_path):
    subject = tmp_path / "Môn"
    subject.mkdir()
    res = Reservations()
    pdf, js = resolve_target_stems(subject, "bai-giang.pdf", res)
    assert pdf.name == "bai-giang.pdf"
    assert js.name == "bai-giang.json"

def test_suffix_when_disk_collision(tmp_path):
    subject = tmp_path / "Môn"
    subject.mkdir()
    (subject / "bai-giang.pdf").write_bytes(b"x")
    res = Reservations()
    pdf, js = resolve_target_stems(subject, "bai-giang.pdf", res)
    assert pdf.name == "bai-giang (1).pdf"
    assert js.name == "bai-giang (1).json"

def test_suffix_when_reserved_same_scan(tmp_path):
    subject = tmp_path / "Môn"
    subject.mkdir()
    res = Reservations()
    resolve_target_stems(subject, "x.pdf", res)        # reserves "x"
    pdf, js = resolve_target_stems(subject, "x.pdf", res)
    assert pdf.name == "x (1).pdf"
    assert js.name == "x (1).json"

def test_suffix_increments(tmp_path):
    subject = tmp_path / "Môn"
    subject.mkdir()
    (subject / "x.pdf").write_bytes(b"a")
    (subject / "x (1).pdf").write_bytes(b"b")
    res = Reservations()
    pdf, _ = resolve_target_stems(subject, "x.pdf", res)
    assert pdf.name == "x (2).pdf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_naming.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

```python
# src/gu_library_worker/naming.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Reservations:
    """Names claimed earlier in the SAME scan pass (not yet on disk)."""
    taken: set[tuple[str, str]] = field(default_factory=set)  # (subject_path, stem)

def _is_free(subject: Path, stem: str, res: Reservations) -> bool:
    if (str(subject), stem) in res.taken:
        return False
    if (subject / f"{stem}.pdf").exists():
        return False
    if (subject / f"{stem}.json").exists():
        return False
    return True

def resolve_target_stems(subject: Path, clean_name: str,
                         res: Reservations) -> tuple[Path, Path]:
    """Return (pdf_path, json_path) for `clean_name`, suffixing ` (n)` on
    collision with disk or same-scan reservations. Reserves the chosen stem."""
    base = Path(clean_name).stem
    stem = base
    n = 0
    while not _is_free(subject, stem, res):
        n += 1
        stem = f"{base} ({n})"
    res.taken.add((str(subject), stem))
    return subject / f"{stem}.pdf", subject / f"{stem}.json"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_naming.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/gu_library_worker/naming.py tests/test_naming.py
git commit -m "feat: target naming with (n) dedup and in-scan reservations"
```

---

## Task 13: Writer (write pair, delete original)

**Files:**
- Create: `src/gu_library_worker/writer.py`
- Test: `tests/test_writer.py`

Safety rule: write outputs and verify them **before** deleting the original.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_writer.py
import json
from pathlib import Path
from gu_library_worker.writer import write_pair

def test_writes_pair_and_deletes_original(tmp_path):
    original = tmp_path / "_inbox" / "[Môn] x.pdf"
    original.parent.mkdir()
    original.write_bytes(b"orig")
    canonical_pdf = tmp_path / "tmp" / "x.pdf"
    canonical_pdf.parent.mkdir()
    canonical_pdf.write_bytes(b"%PDF-1.4 canonical")
    pdf_dst = tmp_path / "Môn" / "x.pdf"
    json_dst = tmp_path / "Môn" / "x.json"
    pdf_dst.parent.mkdir()

    write_pair(canonical_pdf, {"schemaVersion": 1}, pdf_dst, json_dst, original)

    assert pdf_dst.read_bytes() == b"%PDF-1.4 canonical"
    assert json.loads(json_dst.read_text(encoding="utf-8"))["schemaVersion"] == 1
    assert not original.exists()

def test_original_kept_if_pdf_write_fails(tmp_path, monkeypatch):
    original = tmp_path / "_inbox" / "x.pdf"
    original.parent.mkdir()
    original.write_bytes(b"orig")
    canonical_pdf = tmp_path / "missing.pdf"  # does not exist -> copy fails
    pdf_dst = tmp_path / "Môn" / "x.pdf"
    json_dst = tmp_path / "Môn" / "x.json"
    pdf_dst.parent.mkdir()

    try:
        write_pair(canonical_pdf, {"schemaVersion": 1}, pdf_dst, json_dst, original)
    except Exception:
        pass
    assert original.exists()           # original never deleted on failure
    assert not json_dst.exists()       # no half-written pair
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_writer.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

```python
# src/gu_library_worker/writer.py
from __future__ import annotations
import json
import shutil
from pathlib import Path

def write_pair(canonical_pdf: Path, sidecar: dict,
               pdf_dst: Path, json_dst: Path, original: Path) -> None:
    """Place the PDF+JSON pair, then delete the original.

    Outputs are written and confirmed before the original is removed, so a
    failure never loses data (the original stays, app keeps showing ⏳)."""
    pdf_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(canonical_pdf, pdf_dst)
    try:
        json_dst.write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pdf_dst.unlink(missing_ok=True)  # roll back partial pair
        raise
    if not (pdf_dst.exists() and json_dst.exists()):
        raise RuntimeError("pair not fully written; original preserved")
    original.unlink(missing_ok=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_writer.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/gu_library_worker/writer.py tests/test_writer.py
git commit -m "feat: writer places pair before deleting original"
```

---

## Task 14: Pipeline (process one file end-to-end)

**Files:**
- Create: `src/gu_library_worker/pipeline.py`
- Test: `tests/test_pipeline.py`

`process_one_file` ties reading + anchoring + metadata + validation together. It takes an injectable `convert_fn` so tests don't need LibreOffice. It does NOT write to the subject folder (that is `scan`'s job) — it returns a `Prepared(canonical_pdf, sidecar, clean_name, subject)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py
import shutil
from pathlib import Path
from gu_library_worker.pipeline import process_one_file, Prepared
from gu_library_worker.schema import validate_sidecar

def _fake_convert(src, outdir, **kw):
    # for non-pdf, pretend LibreOffice rendered a 1-page pdf with the text
    import fitz
    out = outdir / (src.stem + ".pdf")
    doc = fitz.open(); page = doc.new_page()
    page.insert_text((72, 72), "Điều 1. Phạm vi điều chỉnh", fontsize=12)
    doc.save(out); doc.close()
    return out

def test_docx_pipeline_produces_valid_sidecar(make_docx, tmp_path):
    src = make_docx("[Luật X] luat.docx", [
        "Điều 1. Phạm vi điều chỉnh",
        "Luật này quy định về công chứng.",
    ])
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    assert isinstance(prepared, Prepared)
    assert prepared.subject == "Luật X"
    assert prepared.clean_name == "luat.docx"
    assert prepared.sidecar["sourceFormat"] == "docx"
    assert prepared.sidecar["source"] == "share"
    assert prepared.sidecar["kind"] == "legal"
    assert prepared.sidecar["pageCount"] >= 1
    assert prepared.sidecar["addedAt"].endswith("+07:00")
    assert validate_sidecar(prepared.sidecar) == []

def test_pdf_origin_keeps_original_as_canonical(make_pdf, tmp_path):
    src = make_pdf("[Luật Y] vb.pdf", ["Điều 1. Nội dung trang một."])
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    assert prepared.sidecar["sourceFormat"] == "pdf"
    # canonical pdf is the original bytes (no reconvert)
    assert prepared.canonical_pdf.read_bytes() == src.read_bytes()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_pipeline.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the implementation**

```python
# src/gu_library_worker/pipeline.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable

from .config import SOURCE_FORMAT
from .prefix import parse_prefix
from .schema import Document, to_sidecar
from .readers.base import Extraction
from .readers.docx_reader import read_docx
from .readers.pptx_reader import read_pptx
from .readers.pdf_reader import read_pdf
from .pages import anchor_pages, page_count
from .convert import to_pdf as default_convert

VN_TZ = timezone(timedelta(hours=7))

@dataclass
class Prepared:
    canonical_pdf: Path
    sidecar: dict
    subject: str
    clean_name: str

def _now_iso() -> str:
    return datetime.now(VN_TZ).isoformat(timespec="seconds")

def _read(src: Path, ext: str) -> Extraction:
    if ext == ".docx":
        return read_docx(src)
    if ext == ".pptx":
        return read_pptx(src)
    if ext == ".pdf":
        return read_pdf(src)
    # legacy .doc/.ppt: native libs can't read -> handled via PDF after convert
    raise ValueError(f"native read unsupported for {ext}")

def process_one_file(
    src: Path,
    *,
    tmp_workdir: Path,
    convert_fn: Callable[..., Path] = default_convert,
) -> Prepared:
    tmp_workdir.mkdir(parents=True, exist_ok=True)
    parsed = parse_prefix(src.name)
    ext = src.suffix.lower()
    source_format = SOURCE_FORMAT[ext]

    if ext == ".pdf":
        canonical_pdf = src
        extraction = read_pdf(src)
    elif ext in (".docx", ".pptx"):
        canonical_pdf = convert_fn(src, tmp_workdir)
        extraction = _read(src, ext)
        if ext == ".docx":
            anchor_pages(extraction.units, canonical_pdf)  # pptx already anchored
    else:  # .doc / .ppt legacy -> convert then extract from the PDF
        canonical_pdf = convert_fn(src, tmp_workdir)
        extraction = read_pdf(canonical_pdf)

    doc = Document(
        title=Path(parsed.clean_name).stem,
        source=parsed.source,
        sourceFormat=source_format,
        kind=extraction.kind,
        units=extraction.units,
        addedAt=_now_iso(),
        pageCount=page_count(canonical_pdf),
    )
    return Prepared(
        canonical_pdf=canonical_pdf,
        sidecar=to_sidecar(doc),
        subject=parsed.subject,
        clean_name=parsed.clean_name,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_pipeline.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/gu_library_worker/pipeline.py tests/test_pipeline.py
git commit -m "feat: per-file pipeline read+anchor+build+validate"
```

---

## Task 15: Scan orchestration (one pass)

**Files:**
- Create: `src/gu_library_worker/scan.py`
- Test: `tests/test_scan.py`

`scan_once` lists `_inbox/`, applies the gate, prepares each file, validates, writes the pair, and dedups — isolating errors per file (one bad file never aborts the pass). Returns a `ScanReport`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scan.py
import json
from pathlib import Path
from gu_library_worker.config import Paths
from gu_library_worker.scan import scan_once

def _convert(src, outdir, **kw):
    import fitz
    out = outdir / (src.stem + ".pdf")
    doc = fitz.open(); page = doc.new_page()
    page.insert_text((72, 72), "Điều 1. Nội dung", fontsize=12)
    doc.save(out); doc.close()
    return out

def _kho(tmp_path):
    inbox = tmp_path / "_inbox"
    inbox.mkdir()
    return Paths(kho_root=tmp_path), inbox

def test_docx_filed_into_subject_and_original_removed(make_docx, tmp_path):
    paths, inbox = _kho(tmp_path)
    src = make_docx("law.docx", ["Điều 1. Phạm vi", "Nội dung điều một."])
    src.rename(inbox / "[Luật Công chứng] law.docx")
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    subject = tmp_path / "Luật Công chứng"
    assert (subject / "law.pdf").exists()
    assert (subject / "law.json").exists()
    assert not (inbox / "[Luật Công chứng] law.docx").exists()
    assert report.processed == 1

def test_tmp_file_is_skipped_and_left(tmp_path):
    paths, inbox = _kho(tmp_path)
    (inbox / "junk.pdf.tmp").write_bytes(b"x")
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert (inbox / "junk.pdf.tmp").exists()  # left for manual cleanup
    assert report.processed == 0

def test_duplicate_target_gets_suffix(make_pdf, tmp_path):
    paths, inbox = _kho(tmp_path)
    a = make_pdf("a.pdf", ["Điều 1. Một"])
    a.rename(inbox / "[Môn] doc.pdf")
    b = make_pdf("b.pdf", ["Điều 1. Hai"])
    b.rename(inbox / "[Môn] doc copy.pdf")  # different inbox name...
    # ...but app guarantees clean_name uniqueness only per subject; force same clean name:
    (inbox / "[Môn] doc copy.pdf").rename(inbox / "[Môn] doc.pdf".replace("doc", "doc"))
    # simpler: two files that both clean to "doc.pdf"
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    subject = tmp_path / "Môn"
    names = sorted(p.name for p in subject.glob("*.pdf"))
    assert "doc.pdf" in names

def test_unclassified_goes_to_its_folder(make_pdf, tmp_path):
    paths, inbox = _kho(tmp_path)
    f = make_pdf("x.pdf", ["Điều 1. Nội dung"])
    f.rename(inbox / "[Chưa phân loại] x.pdf")
    scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert (tmp_path / "Chưa phân loại" / "x.pdf").exists()

def test_one_bad_file_does_not_abort_others(make_pdf, tmp_path):
    paths, inbox = _kho(tmp_path)
    good = make_pdf("g.pdf", ["Điều 1. Tốt"])
    good.rename(inbox / "[Môn] good.pdf")
    (inbox / "[Môn] broken.pdf").write_bytes(b"not a real pdf")
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert (tmp_path / "Môn" / "good.pdf").exists()
    assert report.processed == 1
    assert report.failed >= 1
    assert (inbox / "[Môn] broken.pdf").exists()  # failed file left in place
```

> Note for the implementer: the duplicate-name test above is awkward to set up via two inbox files (the app guarantees unique inbox names). The dedup *logic* is already proven in `test_naming.py`; in `test_scan.py` simplify `test_duplicate_target_gets_suffix` to pre-create `Môn/doc.pdf` on disk, then drop one `[Môn] doc.pdf` into the inbox and assert the result is `doc (1).pdf`. Use that simpler form.

- [ ] **Step 2: Simplify the duplicate test as noted**

Replace `test_duplicate_target_gets_suffix` with:

```python
def test_duplicate_target_gets_suffix(make_pdf, tmp_path):
    paths, inbox = _kho(tmp_path)
    subject = tmp_path / "Môn"
    subject.mkdir()
    (subject / "doc.pdf").write_bytes(b"%PDF-1.4 existing")
    f = make_pdf("src.pdf", ["Điều 1. Nội dung mới"])
    f.rename(inbox / "[Môn] doc.pdf")
    scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert (subject / "doc.pdf").exists()        # original kept
    assert (subject / "doc (1).pdf").exists()     # new pair suffixed
    assert (subject / "doc (1).json").exists()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_scan.py -q`
Expected: FAIL — module not found.

- [ ] **Step 4: Write the implementation**

```python
# src/gu_library_worker/scan.py
from __future__ import annotations
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import Paths
from .intake import is_candidate_name, wait_until_stable
from .naming import Reservations, resolve_target_stems
from .pipeline import process_one_file
from .schema import validate_sidecar
from .writer import write_pair
from .convert import to_pdf as default_convert

log = logging.getLogger("gu_library_worker")

@dataclass
class ScanReport:
    processed: int = 0
    skipped: int = 0
    failed: int = 0

def scan_once(paths: Paths, *, convert_fn: Callable[..., Path] = default_convert,
              sleep=None) -> ScanReport:
    report = ScanReport()
    inbox = paths.inbox
    if not inbox.exists():
        return report

    reservations = Reservations()
    stable_kwargs = {} if sleep is None else {"sleep": sleep}

    for entry in sorted(inbox.iterdir()):
        if not entry.is_file():
            continue
        if not is_candidate_name(entry.name):
            report.skipped += 1
            continue
        if not wait_until_stable(entry, **stable_kwargs):
            log.info("not stable yet, leaving: %s", entry.name)
            report.skipped += 1
            continue
        try:
            with tempfile.TemporaryDirectory() as td:
                prepared = process_one_file(entry, tmp_workdir=Path(td),
                                            convert_fn=convert_fn)
                errors = validate_sidecar(prepared.sidecar)
                if errors:
                    raise ValueError(f"sidecar invalid: {errors}")
                subject_dir = paths.subject_dir(prepared.subject)
                pdf_dst, json_dst = resolve_target_stems(
                    subject_dir, prepared.clean_name, reservations)
                write_pair(prepared.canonical_pdf, prepared.sidecar,
                           pdf_dst, json_dst, entry)
            report.processed += 1
            log.info("processed %s -> %s", entry.name, pdf_dst)
        except Exception as exc:  # isolate per-file failure; leave original
            report.failed += 1
            log.exception("failed to process %s: %s", entry.name, exc)
    return report
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_scan.py -q`
Expected: PASS (5 passed).

- [ ] **Step 6: Run the whole suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: PASS (all tasks green).

- [ ] **Step 7: Commit**

```bash
git add src/gu_library_worker/scan.py tests/test_scan.py
git commit -m "feat: stateless single-pass scan orchestration with per-file isolation"
```

---

## Task 16: CLI entry point + logging

**Files:**
- Create: `src/gu_library_worker/__main__.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
from gu_library_worker.__main__ import build_arg_parser, run

def test_arg_parser_requires_kho():
    parser = build_arg_parser()
    args = parser.parse_args(["--kho", "/some/kho"])
    assert args.kho == "/some/kho"

def test_run_invokes_scan_once(tmp_path, monkeypatch):
    (tmp_path / "_inbox").mkdir()
    called = {}
    import gu_library_worker.__main__ as m
    def fake_scan(paths, **kw):
        called["root"] = paths.kho_root
        from gu_library_worker.scan import ScanReport
        return ScanReport(processed=0)
    monkeypatch.setattr(m, "scan_once", fake_scan)
    rc = run(["--kho", str(tmp_path)])
    assert rc == 0
    assert called["root"] == tmp_path
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_cli.py -q`
Expected: FAIL — module/attr not found.

- [ ] **Step 3: Write the implementation**

```python
# src/gu_library_worker/__main__.py
from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path

from .config import Paths
from .convert import DEFAULT_SOFFICE, to_pdf
from .scan import scan_once

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gu-library-worker",
                                description="Scan kho/_inbox once and file outputs.")
    p.add_argument("--kho", required=True, help="Path to the kho root folder")
    p.add_argument("--soffice", default=DEFAULT_SOFFICE,
                   help="LibreOffice soffice executable path")
    p.add_argument("--log-level", default="INFO")
    return p

def run(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    paths = Paths(kho_root=Path(args.kho))
    convert_fn = lambda src, outdir, **kw: to_pdf(src, outdir, soffice=args.soffice)
    report = scan_once(paths, convert_fn=convert_fn)
    logging.getLogger("gu_library_worker").info(
        "done: processed=%d skipped=%d failed=%d",
        report.processed, report.skipped, report.failed,
    )
    return 0

if __name__ == "__main__":
    sys.exit(run())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_cli.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/gu_library_worker/__main__.py tests/test_cli.py
git commit -m "feat: CLI entry point with --kho and logging"
```

---

## Task 17: Synthetic acceptance test (assert-tight integration)

**Files:**
- Create: `tests/test_acceptance_synthetic.py`

This is the "Tổng hợp (assert chặt)" fixture tier — it pins the M7 acceptance rows that don't need real LibreOffice.

- [ ] **Step 1: Write the test**

```python
# tests/test_acceptance_synthetic.py
import json
from pathlib import Path
from gu_library_worker.config import Paths
from gu_library_worker.scan import scan_once

def _convert(src, outdir, **kw):
    import fitz
    out = outdir / (src.stem + ".pdf")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Điều 1. Phạm vi điều chỉnh", fontsize=12)
    doc.save(out); doc.close()
    return out

def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))

def test_word_law_yields_dieu_khoan_with_pages(make_docx, tmp_path):
    paths = Paths(kho_root=tmp_path)
    (tmp_path / "_inbox").mkdir()
    src = make_docx("law.docx", [
        "Chương I QUY ĐỊNH CHUNG",
        "Điều 1. Phạm vi điều chỉnh",
        "Luật này quy định về công chứng.",
        "Điều 2. Giải thích từ ngữ",
        "1. Công chứng là việc chứng nhận.",
    ])
    src.rename(tmp_path / "_inbox" / "[Luật Công chứng] law.docx")
    scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    sc = _read_json(tmp_path / "Luật Công chứng" / "law.json")
    assert sc["kind"] == "legal"
    types = {(u["type"], u["label"]) for u in sc["units"]}
    assert ("dieu", "Điều 1") in types
    assert ("dieu", "Điều 2") in types
    assert ("khoan", "Khoản 1") in types
    assert all(u["page"] >= 1 for u in sc["units"])
    assert not (tmp_path / "_inbox" / "[Luật Công chứng] law.docx").exists()

def test_pptx_one_unit_per_slide(make_pptx, tmp_path):
    paths = Paths(kho_root=tmp_path)
    (tmp_path / "_inbox").mkdir()
    # 3-page canonical pdf so slide pages 1..3 anchor cleanly
    def convert3(src, outdir, **kw):
        import fitz
        out = outdir / (src.stem + ".pdf")
        doc = fitz.open()
        for i in range(3):
            doc.new_page().insert_text((72, 72), f"Slide {i+1}", fontsize=12)
        doc.save(out); doc.close()
        return out
    src = make_pptx("deck.pptx", ["A", "B", "C"])
    src.rename(tmp_path / "_inbox" / "[Hiến pháp] deck.pptx")
    scan_once(paths, convert_fn=convert3, sleep=lambda s: None)
    sc = _read_json(tmp_path / "Hiến pháp" / "deck.json")
    assert sc["kind"] == "slide"
    assert [u["label"] for u in sc["units"]] == ["Slide 1", "Slide 2", "Slide 3"]
    assert [u["page"] for u in sc["units"]] == [1, 2, 3]

def test_real_pdf_origin_not_reconverted(make_pdf, tmp_path):
    paths = Paths(kho_root=tmp_path)
    (tmp_path / "_inbox").mkdir()
    src = make_pdf("vb.pdf", [
        "Điều 1. Nội dung trang một.",
        "Đoạn văn xuôi trang hai không có cấu trúc điều khoản.",
    ])
    original_bytes = src.read_bytes()
    src.rename(tmp_path / "_inbox" / "[Luật X] vb.pdf")
    scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    out_pdf = tmp_path / "Luật X" / "vb.pdf"
    assert out_pdf.read_bytes() == original_bytes  # canonical = original, no reconvert
    sc = _read_json(tmp_path / "Luật X" / "vb.json")
    assert sc["sourceFormat"] == "pdf"
    joined = " ".join(u["text"] for u in sc["units"])
    assert "trang một" in joined and "trang hai" in joined  # no text lost

def test_tmp_file_left_alone(tmp_path):
    paths = Paths(kho_root=tmp_path)
    (tmp_path / "_inbox").mkdir()
    (tmp_path / "_inbox" / "[Môn] x.pdf.tmp").write_bytes(b"half written")
    report = scan_once(paths, convert_fn=_convert, sleep=lambda s: None)
    assert (tmp_path / "_inbox" / "[Môn] x.pdf.tmp").exists()
    assert report.processed == 0
```

- [ ] **Step 2: Run the test**

Run: `.venv/Scripts/python -m pytest tests/test_acceptance_synthetic.py -q`
Expected: PASS (4 passed).

- [ ] **Step 3: Run full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_acceptance_synthetic.py
git commit -m "test: synthetic acceptance covering M7 checklist rows"
```

---

## Task 18: Real smoke test (5 real files — acceptance)

**Files:**
- Create: `tests/test_smoke_real.py`

Runs only when `GULIB_SMOKE_KHO` points at a kho whose `_inbox/` holds Gú's 5 real files (3 legal PDFs + 1 Word + 1 PPTX) and a `.tmp` decoy, on the mini PC with LibreOffice installed. This is the human-eyeball acceptance gate.

- [ ] **Step 1: Write the smoke test**

```python
# tests/test_smoke_real.py
import json
import os
from pathlib import Path
import pytest
from gu_library_worker.config import Paths
from gu_library_worker.scan import scan_once

KHO = os.environ.get("GULIB_SMOKE_KHO")

pytestmark = pytest.mark.skipif(
    not KHO, reason="set GULIB_SMOKE_KHO to the real kho root to run the smoke test"
)

def test_smoke_processes_real_inbox():
    paths = Paths(kho_root=Path(KHO))
    before = sorted(p.name for p in paths.inbox.iterdir())
    report = scan_once(paths)  # real LibreOffice + real files
    print("scan report:", report)

    # every produced sidecar validates and has non-empty text
    for sidecar in paths.kho_root.rglob("*.json"):
        if sidecar.parent.name in ("_inbox", "_print"):
            continue
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert data["schemaVersion"] == 1
        assert data["units"], f"empty units in {sidecar}"
        for u in data["units"]:
            assert u["text"].strip(), f"empty unit text in {sidecar}"
            assert u["page"] >= 1

    # .tmp decoy stays untouched
    remaining = sorted(p.name for p in paths.inbox.iterdir())
    assert any(n.endswith(".tmp") for n in remaining), \
        "expected the .tmp decoy to be left behind"
    print("inbox before:", before)
    print("inbox after :", remaining)
```

- [ ] **Step 2: Verify it skips cleanly without the env var**

Run: `.venv/Scripts/python -m pytest tests/test_smoke_real.py -q`
Expected: `1 skipped`.

- [ ] **Step 3: Run for real on the mini PC**

On the mini PC (LibreOffice installed, 5 real files + a `.tmp` decoy staged in `_inbox/`):

```bash
GULIB_SMOKE_KHO="D:/path/to/kho" .venv/Scripts/python -m pytest tests/test_smoke_real.py -s -q
```
Expected: PASS. Then **eyeball** each produced `.json`: legal PDFs show `dieu`/`khoan` (or clean `paragraph` degrade with no lost text), the PPTX shows one `slide` per slide with 1-1 pages, the Word law shows Điều/Khoản with sensible pages. Confirm the `.tmp` decoy is still in `_inbox/`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_smoke_real.py
git commit -m "test: real-file smoke acceptance (opt-in via GULIB_SMOKE_KHO)"
```

---

## Task 19: Scheduled Task registration + README run guide

**Files:**
- Create: `scripts/register-task.ps1`
- Modify: `README.md`

- [ ] **Step 1: Write the registration script**

```powershell
# scripts/register-task.ps1
# Registers the worker to run every few minutes on the mini PC.
param(
    [Parameter(Mandatory = $true)][string]$KhoRoot,
    [string]$RepoRoot = (Resolve-Path "$PSScriptRoot\.."),
    [int]$IntervalMinutes = 3,
    [string]$Soffice = "C:\Program Files\LibreOffice\program\soffice.exe",
    [string]$TaskName = "GuLibraryWorker"
)

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$arguments = "-m gu_library_worker --kho `"$KhoRoot`" --soffice `"$Soffice`""

$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Gú's Library: convert + extract _inbox" -Force

Write-Host "Registered '$TaskName' every $IntervalMinutes min. Test one pass now:"
Write-Host "  $python -m gu_library_worker --kho `"$KhoRoot`" --soffice `"$Soffice`""
```

- [ ] **Step 2: Append the run guide to README.md**

```markdown
## Running on the mini PC

One pass manually:

    .venv\Scripts\python -m gu_library_worker --kho "D:\path\to\kho" --soffice "C:\Program Files\LibreOffice\program\soffice.exe"

Register the Scheduled Task (every 3 minutes, restarts after reboot):

    powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1 -KhoRoot "D:\path\to\kho"

The worker is stateless: each run scans `_inbox/` once and exits. Files it can't
handle (wrong extension, still being written, broken) are left in place on
purpose — the app shows ⏳ as the signal to clean up by hand.
```

- [ ] **Step 3: Verify the task registers and a manual pass runs**

On the mini PC:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1 -KhoRoot "D:\path\to\kho"
Get-ScheduledTask -TaskName GuLibraryWorker
```
Expected: task listed; the printed manual command runs one pass with `processed/skipped/failed` logged.

- [ ] **Step 4: Commit**

```bash
git add scripts/register-task.ps1 README.md
git commit -m "chore: scheduled task registration and run guide"
```

---

## Task 20 (conditional on Task 0): Add `bbox` to the schema

Do this **only if** the Task 0 highlight spike came back feasible. Skip otherwise.

**Files:**
- Modify: `Docs/gu-library-sidecar-schema.md` (document the `bbox` field)
- Modify: `src/gu_library_worker/schema.py` (`Unit.bbox`, `to_sidecar`, `validate_sidecar`)
- Modify: `src/gu_library_worker/readers/pdf_reader.py` (emit span bbox via `page.get_text("dict")`)
- Modify: `src/gu_library_worker/pages.py` (capture bbox for docx units during search)
- Test: extend `tests/test_schema.py`, `tests/test_pdf_reader.py`

- [ ] **Step 1: Write failing tests for the bbox field** (shape `[x0, y0, x1, y1]` floats; optional/nullable for units where no coordinate is resolvable so text is still never lost).
- [ ] **Step 2: Add `bbox` to `Unit`, `to_sidecar`, and `validate_sidecar`** (validate as a 4-number list or `None`).
- [ ] **Step 3: Populate bbox in the PDF reader** from the first span of each unit (`get_text("dict")` → `blocks[].lines[].spans[].bbox`).
- [ ] **Step 4: Run the suite, then re-run the worker over the ~5-file kho** (cheap now) so existing sidecars gain bbox.
- [ ] **Step 5: Commit** `feat: add bbox coordinates to sidecar (highlight spike feasible)`.

---

## Self-Review (completed against the input + spec)

**Spec coverage — every M7 acceptance row maps to a task:**
- Spike highlight → decide `bbox` → **Task 0** + conditional **Task 20**.
- Word law → PDF+JSON in subject, original deleted, sidecar has Điều/Khoản + pages → **Tasks 7, 10, 14, 15, 17** (`test_word_law_yields_dieu_khoan_with_pages`).
- PPTX → one `slide` unit per slide, 1-1 pages → **Tasks 8, 17** (`test_pptx_one_unit_per_slide`).
- Real PDF (no reconvert) → extract direct, clean degrade, no text lost → **Tasks 9, 14, 17** (`test_real_pdf_origin_not_reconverted`) + **Task 18** smoke.
- `.tmp` left alone → **Tasks 4, 15, 17** (`test_tmp_file_left_alone`).
- Duplicate target name → ` (1)` on the pair, no overwrite → **Tasks 12, 15** (`test_duplicate_target_gets_suffix`).
- "Chưa phân loại" → its folder → **Tasks 3, 15** (`test_unclassified_goes_to_its_folder`).
- Observe `.syncthing.*.tmp` flicker → filter already excludes the token (Task 4); the observation step lives in **Task 18** smoke output (`inbox before/after` print).

**Hard constraints covered:** schema conformance (validator gates every write, Task 5/15); never lose text (degrade to paragraph/slide; continuation lines appended — Tasks 6–9; smoke asserts non-empty unit text); never overwrite/wrong-delete (dedup Task 12; write-before-delete Task 13; junk left in place Task 15); stateless (no ledger; `scan_once` derives from `_inbox/` each pass); `bbox` deferred (Task 0/20).

**Placeholder scan:** no "TBD"/"add error handling"/"write tests for the above" — every code step shows code; every test step shows assertions.

**Type/name consistency:** `Unit`/`Document`/`to_sidecar`/`validate_sidecar` (schema.py) used identically everywhere; `Extraction`/`Line` (readers/base.py); `read_docx`/`read_pptx`/`read_pdf`; `anchor_pages`/`page_count`; `to_pdf`/`build_command`/`ConversionError`; `Reservations`/`resolve_target_stems`; `write_pair`; `process_one_file`/`Prepared`; `scan_once`/`ScanReport`. Pipeline injects `convert_fn`; scan and CLI pass it through consistently.

**One open item flagged for the implementer:** `process_one_file` anchors pages for `.docx` only (pptx/pdf set pages at read time); legacy `.doc`/`.ppt` route through the PDF reader on the converted PDF (documented decision #4). If real `.doc`/`.ppt` files turn out common, revisit converting `.doc→.docx`/`.ppt→.pptx` first to keep clean structure.
