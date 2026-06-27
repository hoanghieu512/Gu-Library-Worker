# tests/test_logsetup.py
import logging
import pytest
from gu_library_worker.__main__ import run
from gu_library_worker.logsetup import attach_log_file

@pytest.fixture(autouse=True)
def _isolate_worker_logger():
    """Remove any file handlers this test added so handlers/paths don't leak."""
    logger = logging.getLogger("gu_library_worker")
    before = list(logger.handlers)
    level = logger.level
    yield
    for h in logger.handlers[:]:
        if h not in before:
            h.close()
            logger.removeHandler(h)
    logger.setLevel(level)

def test_run_writes_scan_report_to_worker_log(make_pdf, tmp_path):
    inbox = tmp_path / "_inbox"
    inbox.mkdir()
    f = make_pdf("x.pdf", ["Điều 1. Nội dung"])
    f.rename(inbox / "[Môn] x.pdf")

    rc = run(["--kho", str(tmp_path)])
    assert rc == 0

    log = (tmp_path / "_worker.log").read_text(encoding="utf-8")
    assert "scan starting" in log
    assert "processed" in log
    assert "done: processed=1 skipped=0 failed=0" in log   # ScanReport recorded

def test_skip_and_failure_reasons_logged(tmp_path):
    inbox = tmp_path / "_inbox"
    inbox.mkdir()
    (inbox / "junk.txt.tmp").write_bytes(b"x")             # gate-skip (temp/unsupported)
    (inbox / "[Môn] broken.pdf").write_bytes(b"not a real pdf")  # fails extraction

    run(["--kho", str(tmp_path)])
    log = (tmp_path / "_worker.log").read_text(encoding="utf-8")

    assert "skipped (unsupported/temp name): junk.txt.tmp" in log   # no longer silent
    assert "failed to process" in log and "broken.pdf" in log
    assert "Traceback" in log                                       # extraction error captured

def test_log_rotation_caps_size(tmp_path):
    handler = attach_log_file(tmp_path, max_bytes=500, backup_count=2)
    assert handler is not None
    logger = logging.getLogger("gu_library_worker")
    for i in range(200):
        logger.info("padding line %d ----------------------------------------", i)
    handler.flush()

    assert (tmp_path / "_worker.log").exists()
    assert (tmp_path / "_worker.log.1").exists()            # rotation happened
    assert (tmp_path / "_worker.log").stat().st_size <= 2000  # current file capped

def test_attach_is_idempotent(tmp_path):
    logger = logging.getLogger("gu_library_worker")
    n0 = len(logger.handlers)
    h1 = attach_log_file(tmp_path)
    h2 = attach_log_file(tmp_path)
    assert h1 is h2                                         # same handler reused
    assert len(logger.handlers) == n0 + 1                  # not stacked

def test_attach_returns_none_for_missing_dir(tmp_path):
    assert attach_log_file(tmp_path / "nope") is None

def test_worker_log_not_validated_as_sidecar(tmp_path):
    # _worker.log must be ignored by the smoke sidecar scan (not a .json, and the
    # leading underscore matches the existing _-prefix exclusion).
    from test_smoke_real import validate_document_sidecars
    (tmp_path / "_worker.log").write_text("2026 INFO done: processed=1", encoding="utf-8")
    mon = tmp_path / "Môn"
    mon.mkdir()
    (mon / "d.pdf").write_bytes(b"%PDF-1.4")
    (mon / "d.json").write_text(
        '{"schemaVersion":1,"title":"d","source":"share","addedAt":"x",'
        '"sourceFormat":"pdf","pageCount":1,"kind":"prose",'
        '"units":[{"type":"paragraph","label":"","path":[],"text":"t","page":1}]}',
        encoding="utf-8")
    assert validate_document_sidecars(tmp_path) == 1
