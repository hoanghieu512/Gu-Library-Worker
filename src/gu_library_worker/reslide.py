# src/gu_library_worker/reslide.py
"""Rebuild slide structure in sidecars that came from a legacy .ppt source.

A legacy OLE .ppt can't be read by python-pptx, so the pipeline converts it with
LibreOffice and extracts from the resulting PDF. That path yields one
`paragraph` unit per text block with an empty label: readable, but structureless
— full-text search shows a wall of unlabelled fragments instead of "Slide 12".

The repair regroups the units the sidecar ALREADY holds, by their `page`. Every
unit keeps the page it was extracted with, so the anchor stays exactly as
accurate as it was and the PDF in the kho is never re-converted or touched. The
alternative — re-reading the archived .ppt — would derive `page` from a slide
index belonging to a freshly rendered PDF, which is not the PDF the app is
jumping into. Regrouping cannot drift that way, and it also repairs documents
whose original source was deleted before archiving existed.

`kind: "legal"` sidecars are never touched: a .ppt quoting law parses into real
Điều/Khoản units, which is better structure than slides, not worse.
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from .logsetup import kho_logging
from .schema import validate_sidecar

log = logging.getLogger("gu_library_worker")

# Folders under the kho that never hold documents: Syncthing internals, the
# worker's own inbox, and the print outbox (copies, not originals).
_SKIP_DIRS = {".stversions", ".stfolder", "_inbox", "_print"}
# Old sidecars are kept here (a sibling of the kho, so it is outside Syncthing
# and never syncs back to the phones) before anything is overwritten.
BACKUP_DIRNAME = "_sidecar_backup"


@dataclass
class ReslideReport:
    targets: int = 0          # degraded legacy-.ppt sidecars found
    rewritten: int = 0        # regrouped into slide units
    skipped_unsafe: int = 0   # a target whose regroup failed a safety check


def is_degraded_slide_sidecar(data: dict) -> bool:
    """True for a sidecar that came from a .ppt via the PDF reader and lost its
    slide structure.

    The fingerprint is exact rather than heuristic: `sourceFormat` is pptx (so
    the source really was a slide deck), `kind` is prose (a native .pptx always
    yields `slide`, so prose means it went through convert + PDF read), every
    unit is an unlabelled paragraph, and at least one carries a `bbox` — only
    the PDF reader emits coordinates, which confirms the path taken.
    """
    if data.get("sourceFormat") != "pptx" or data.get("kind") != "prose":
        return False
    units = data.get("units") or []
    if not units:
        return False
    if not all(u.get("type") == "paragraph" and not u.get("label") for u in units):
        return False
    return any("bbox" in u for u in units)


def _union(boxes: list[list[float]]) -> list[float]:
    return [
        min(b[0] for b in boxes), min(b[1] for b in boxes),
        max(b[2] for b in boxes), max(b[3] for b in boxes),
    ]


def group_blocks_into_slides(
    blocks: list[tuple[str, int, list[float] | None]], page_count: int,
) -> list[tuple[str, int, list[float] | None]] | None:
    """Merge (text, page, bbox) blocks into one entry per page that has text.

    `page` is carried through untouched — this never computes a page, it only
    keeps the one the block already had. Returns None rather than guessing when
    a block sits on a page the PDF doesn't have, or when nothing has text.
    """
    if not blocks or not isinstance(page_count, int) or page_count < 1:
        return None
    by_page: dict[int, list[tuple[str, int, list[float] | None]]] = {}
    for text, page, bbox in blocks:
        if not isinstance(page, int) or isinstance(page, bool) \
                or page < 1 or page > page_count:
            return None  # an anchor we can't trust -> leave the units alone
        by_page.setdefault(page, []).append((text, page, bbox))

    out: list[tuple[str, int, list[float] | None]] = []
    for page in sorted(by_page):
        group = by_page[page]
        text = "\n".join(t for t, _, _ in group if t and t.strip())
        if not text.strip():
            continue  # a page whose blocks are all blank contributes no unit
        boxes = [b for _, _, b in group if isinstance(b, list)]
        out.append((text, page, _union(boxes) if boxes else None))
    return out or None


def slide_units_from_pdf_blocks(units: list, page_count: int) -> list | None:
    """Slide-per-page `Unit`s built from the PDF reader's paragraph units.

    Used by the pipeline so a newly arriving .ppt gets slide structure straight
    away, anchored on the pages the PDF reader already produced.
    """
    from .schema import Unit  # local: schema must not import reslide back

    grouped = group_blocks_into_slides(
        [(u.text, u.page, u.bbox) for u in units], page_count)
    if grouped is None:
        return None
    return [Unit(type="slide", label=f"Slide {page}", path=[], text=text,
                 page=page, bbox=bbox) for text, page, bbox in grouped]


def regroup_slide_units(data: dict) -> dict | None:
    """Return a slide-structured copy of `data`, or None if it isn't safe.

    One unit per PDF page that has text, `page` copied verbatim from the units
    being merged. Returns None rather than guessing when the input is
    inconsistent (a page beyond the PDF, no text at all) or when the result
    would not satisfy the sidecar contract — a degraded sidecar that still
    jumps to the right page beats a pretty one that doesn't.
    """
    units = data.get("units") or []
    grouped = group_blocks_into_slides(
        [(u.get("text") or "", u.get("page"),
          u["bbox"] if isinstance(u.get("bbox"), list) else None) for u in units],
        data.get("pageCount"))
    if grouped is None:
        return None

    new_units: list[dict] = []
    for text, page, bbox in grouped:
        unit = {"type": "slide", "label": f"Slide {page}", "path": [],
                "text": text, "page": page}
        if bbox is not None:
            unit["bbox"] = bbox
        new_units.append(unit)

    out = dict(data)
    out["kind"] = "slide"
    out["units"] = new_units
    # `addedAt` deliberately keeps its original value: it records when Gú added
    # the document, which the app shows; this repair is not a re-import.
    return out if not validate_sidecar(out) else None


def _document_sidecars(kho_root: Path):
    """Yield every sidecar that belongs to a real document in the kho.

    A sidecar is paired with a same-stem PDF, which by itself rules out
    `_mon.json`, `_reading-*.json` and the `.print.json` / `.display.json`
    app-owned metadata files.
    """
    for path in sorted(kho_root.rglob("*.json")):
        rel = path.relative_to(kho_root)
        if any(part in _SKIP_DIRS for part in rel.parts[:-1]):
            continue
        if not (path.parent / (path.stem + ".pdf")).exists():
            continue
        yield path


def _write_atomic(path: Path, data: dict) -> None:
    """Write next to the target then replace, so Syncthing never picks up a
    half-written sidecar (the app would fail to parse it)."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def reslide_kho(kho_root, *, apply: bool = False) -> ReslideReport:
    """Regroup every degraded legacy-.ppt sidecar in one kho.

    With `apply=False` (the default) nothing is written — the report says what
    would change. With `apply=True` the previous sidecar is copied into
    `<kho>_archive/_sidecar_backup/` first, preserving the exact bytes the app
    is serving today in a place that is outside the synced folder.
    """
    kho_root = Path(kho_root)
    backup_root = kho_root.with_name(kho_root.name + "_archive") / BACKUP_DIRNAME
    report = ReslideReport()

    for path in _document_sidecars(kho_root):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("unreadable sidecar, skipping: %s: %s", path, exc)
            continue
        if not isinstance(data, dict) or not is_degraded_slide_sidecar(data):
            continue

        report.targets += 1
        rel = path.relative_to(kho_root)
        new = regroup_slide_units(data)
        if new is None:
            report.skipped_unsafe += 1
            log.warning("re-slide unsafe, sidecar left as-is: %s", rel)
            continue

        report.rewritten += 1
        log.info("re-slide %s: %d units -> %d slides (pages unchanged)",
                 rel, len(data["units"]), len(new["units"]))
        if not apply:
            continue
        backup = backup_root / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, backup)
        _write_atomic(path, new)

    return report


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gu-library-worker reslide",
        description="Rebuild slide structure in sidecars that came from legacy "
                    ".ppt sources. Reports only unless --apply is given.")
    p.add_argument("--kho", action="append", required=True, metavar="KHO_ROOT",
                   help="Path to a kho root folder. Repeat --kho for multiple "
                        "kho; they are processed sequentially in one process.")
    p.add_argument("--apply", action="store_true",
                   help="Write the rebuilt sidecars. Without it, nothing is "
                        "modified and the run is a report.")
    p.add_argument("--log-level", default="INFO")
    return p


def run(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    # One process, one kho at a time — same discipline as the scan pass, and one
    # kho's failure must not stop the rest.
    for kho_path in args.kho:
        kho_root = Path(kho_path)
        label = kho_root.parent.name or kho_root.name or str(kho_root)
        if not kho_root.is_dir():
            log.error("kho not found, skipping: %s", kho_root)
            continue
        with kho_logging(kho_root, label):
            log.info("re-slide %s: kho=%s", "APPLY" if args.apply else "DRY-RUN",
                     kho_root)
            try:
                report = reslide_kho(kho_root, apply=args.apply)
            except Exception as exc:
                log.exception("kho failed, skipping: %s: %s", kho_root, exc)
                continue
            log.info("done: targets=%d rewritten=%d skipped_unsafe=%d%s",
                     report.targets, report.rewritten, report.skipped_unsafe,
                     "" if args.apply else " (dry run, nothing written)")
    return 0


if __name__ == "__main__":
    sys.exit(run())
