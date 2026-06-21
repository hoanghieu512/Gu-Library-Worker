# tests/test_cli.py
import pytest
from gu_library_worker.__main__ import build_arg_parser, run

def test_arg_parser_requires_kho():
    parser = build_arg_parser()
    args = parser.parse_args(["--kho", "/some/kho"])
    assert args.kho == "/some/kho"

def test_arg_parser_errors_without_kho():
    parser = build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])

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
