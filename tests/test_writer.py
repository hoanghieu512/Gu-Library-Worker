# tests/test_writer.py
import json
import pathlib
from pathlib import Path
import pytest
from gu_library_worker.writer import write_pair, _unlink_with_retry

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

def test_pdf_rolled_back_if_json_write_fails(tmp_path, monkeypatch):
    original = tmp_path / "_inbox" / "x.pdf"
    original.parent.mkdir()
    original.write_bytes(b"orig")
    canonical_pdf = tmp_path / "tmp" / "x.pdf"
    canonical_pdf.parent.mkdir()
    canonical_pdf.write_bytes(b"%PDF-1.4 canonical")
    pdf_dst = tmp_path / "Môn" / "x.pdf"
    json_dst = tmp_path / "Môn" / "x.json"
    pdf_dst.parent.mkdir()

    def fail_write(self, *a, **kw):
        raise OSError("disk full")
    monkeypatch.setattr(pathlib.Path, "write_text", fail_write)

    with pytest.raises(OSError):
        write_pair(canonical_pdf, {"schemaVersion": 1}, pdf_dst, json_dst, original)

    assert original.exists()       # original preserved
    assert not pdf_dst.exists()    # partial PDF rolled back
    assert not json_dst.exists()   # no JSON written

def test_unlink_with_retry_recovers_from_transient_lock(tmp_path, monkeypatch):
    f = tmp_path / "x"
    f.write_bytes(b"1")
    real_unlink = pathlib.Path.unlink
    calls = {"n": 0}
    def flaky(self, *a, **k):
        calls["n"] += 1
        if calls["n"] < 3:               # locked for the first two attempts
            raise PermissionError("WinError 32: in use")
        return real_unlink(self)
    monkeypatch.setattr(pathlib.Path, "unlink", flaky)
    assert _unlink_with_retry(f, tries=5, delay=0, sleep=lambda s: None) is True
    assert calls["n"] == 3
    assert not f.exists()

def test_pair_rolled_back_if_original_cannot_be_removed(tmp_path, monkeypatch):
    # A permanently-locked original must NOT leave the pair behind, or the next
    # pass would create a duplicate. The pair is rolled back; original preserved.
    import gu_library_worker.writer as w
    original = tmp_path / "_inbox" / "[Môn] x.pdf"
    original.parent.mkdir()
    original.write_bytes(b"orig")
    canonical_pdf = tmp_path / "tmp" / "x.pdf"
    canonical_pdf.parent.mkdir()
    canonical_pdf.write_bytes(b"%PDF-1.4 canonical")
    pdf_dst = tmp_path / "Môn" / "x.pdf"
    json_dst = tmp_path / "Môn" / "x.json"
    pdf_dst.parent.mkdir()

    monkeypatch.setattr(w, "_unlink_with_retry", lambda p, **k: False)  # never frees
    with pytest.raises(RuntimeError):
        w.write_pair(canonical_pdf, {"schemaVersion": 1}, pdf_dst, json_dst, original)

    assert original.exists()        # never lost
    assert not pdf_dst.exists()     # pair rolled back -> no duplicate next pass
    assert not json_dst.exists()
