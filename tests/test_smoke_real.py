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

def validate_document_sidecars(kho_root: Path) -> int:
    """Validate every DOCUMENT sidecar under `kho_root`; return how many checked.

    A document sidecar is a `.json` paired with a same-stem `.pdf`. Folder
    metadata like `_mon.json` (color/order only, no `schemaVersion`) has no
    sibling pdf and is skipped, so it never trips a KeyError. `_inbox`/`_print`
    are excluded. Real assertions are unchanged: schemaVersion==1, non-empty
    units, each unit's text non-empty, page>=1.
    """
    checked = 0
    for sidecar in kho_root.rglob("*.json"):
        if sidecar.parent.name in ("_inbox", "_print"):
            continue
        if sidecar.name.startswith("_"):
            continue  # _mon.json and other folder metadata, not a sidecar
        if not sidecar.with_suffix(".pdf").exists():
            continue  # only validate sidecars paired with their PDF
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert data["schemaVersion"] == 1, f"bad schemaVersion in {sidecar}"
        assert data["units"], f"empty units in {sidecar}"
        for u in data["units"]:
            assert u["text"].strip(), f"empty unit text in {sidecar}"
            assert u["page"] >= 1, f"bad page in {sidecar}"
        checked += 1
    return checked

def test_smoke_processes_real_inbox():
    assert KHO, "GULIB_SMOKE_KHO must be set"  # guard if skip ever fails to fire
    paths = Paths(kho_root=Path(KHO))
    before = sorted(p.name for p in paths.inbox.iterdir())
    report = scan_once(paths)  # real LibreOffice + real files
    print("scan report:", report)

    checked = validate_document_sidecars(paths.kho_root)
    assert checked > 0, "no document sidecars found to validate"

    # .tmp decoy stays untouched
    remaining = sorted(p.name for p in paths.inbox.iterdir())
    assert any(n.endswith(".tmp") for n in remaining), \
        "expected the .tmp decoy to be left behind"
    print("inbox before:", before)
    print("inbox after :", remaining)
