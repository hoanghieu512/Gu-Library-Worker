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
