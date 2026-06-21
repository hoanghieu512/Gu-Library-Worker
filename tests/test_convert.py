# tests/test_convert.py
import subprocess
import pytest
from pathlib import Path
from gu_library_worker.convert import to_pdf, ConversionError, build_command

def test_build_command_shape(tmp_path):
    cmd = build_command(tmp_path / "in.docx", tmp_path, soffice="soffice")
    assert cmd[0] == "soffice"
    assert "--headless" in cmd and "--convert-to" in cmd
    assert "--outdir" in cmd and str(tmp_path) in cmd
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
