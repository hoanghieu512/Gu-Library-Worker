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
