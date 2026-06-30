# tests/test_multikho.py
# v0.8.0: one process watches N kho, scanned sequentially, isolated, per-kho log.
import logging
import pytest
from gu_library_worker.__main__ import run

@pytest.fixture(autouse=True)
def _isolate_worker_logger():
    logger = logging.getLogger("gu_library_worker")
    before = list(logger.handlers)
    level = logger.level
    yield
    for h in logger.handlers[:]:
        if h not in before:
            h.close()
            logger.removeHandler(h)
    logger.setLevel(level)

def _make_kho(parent, env_name, make_pdf, inbox_name):
    """Create <parent>/<env_name>/kho/_inbox with one prefixed pdf inside."""
    kho = parent / env_name / "kho"
    (kho / "_inbox").mkdir(parents=True)
    src = make_pdf(f"{env_name}.pdf", ["Điều 1. Nội dung"])
    src.rename(kho / "_inbox" / inbox_name)
    return kho

def test_two_kho_both_processed_with_labeled_logs(make_pdf, tmp_path):
    a = _make_kho(tmp_path, "GuLibrary", make_pdf, "[Môn A] a.pdf")
    b = _make_kho(tmp_path, "GuLibrary-Prod", make_pdf, "[Môn B] b.pdf")

    rc = run(["--kho", str(a), "--kho", str(b)])
    assert rc == 0

    # each kho filed its own document AND cleared its inbox (no PDF-origin file
    # left stuck — the v0.8.1 WinError-32 regression that made only kho A process)
    assert (a / "Môn A" / "a.pdf").exists() and (a / "Môn A" / "a.json").exists()
    assert (b / "Môn B" / "b.pdf").exists() and (b / "Môn B" / "b.json").exists()
    assert list((a / "_inbox").iterdir()) == []
    assert list((b / "_inbox").iterdir()) == []

    # each kho's log exists and is labeled with ITS env, not the other's
    log_a = (a / "_worker.log").read_text(encoding="utf-8")
    log_b = (b / "_worker.log").read_text(encoding="utf-8")
    assert "[GuLibrary]" in log_a and "[GuLibrary-Prod]" not in log_a
    assert "[GuLibrary-Prod]" in log_b and "[GuLibrary]" not in log_b
    assert "done: processed=1" in log_a and "done: processed=1" in log_b

def test_missing_kho_skipped_others_continue(make_pdf, tmp_path, caplog):
    good = _make_kho(tmp_path, "GuLibrary", make_pdf, "[Môn] g.pdf")
    missing = tmp_path / "GuLibrary-Prod" / "kho"   # never created

    with caplog.at_level(logging.INFO, logger="gu_library_worker"):
        rc = run(["--kho", str(missing), "--kho", str(good)])
    assert rc == 0

    # the present kho still processed despite the missing one being first
    assert (good / "Môn" / "g.pdf").exists()
    # the skip is logged with the kho path
    assert any("kho not found" in r.message and str(missing) in r.message
               for r in caplog.records)

def test_one_kho_failure_does_not_abort_the_rest(make_pdf, tmp_path, monkeypatch, caplog):
    import gu_library_worker.__main__ as m
    good = _make_kho(tmp_path, "GuLibrary", make_pdf, "[Môn] g.pdf")
    prod = _make_kho(tmp_path, "GuLibrary-Prod", make_pdf, "[Môn] p.pdf")
    real_scan = m.scan_once

    def flaky_scan(paths, **kw):
        if paths.kho_root == prod:
            raise RuntimeError("boom mid-scan")
        return real_scan(paths, **kw)
    monkeypatch.setattr(m, "scan_once", flaky_scan)

    with caplog.at_level(logging.INFO, logger="gu_library_worker"):
        rc = run(["--kho", str(prod), "--kho", str(good)])
    assert rc == 0
    assert (good / "Môn" / "g.pdf").exists()                  # good kho still done
    assert any("kho failed, skipping" in r.message and str(prod) in r.message
               for r in caplog.records)

def test_single_kho_unchanged(make_pdf, tmp_path):
    # backward compatibility: one --kho behaves exactly like before.
    a = _make_kho(tmp_path, "GuLibrary", make_pdf, "[Môn] x.pdf")
    rc = run(["--kho", str(a)])
    assert rc == 0
    assert (a / "Môn" / "x.pdf").exists() and (a / "Môn" / "x.json").exists()
    assert (a / "_worker.log").exists()
