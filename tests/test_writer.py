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
