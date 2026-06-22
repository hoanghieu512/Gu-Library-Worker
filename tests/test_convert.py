# tests/test_convert.py
import subprocess
import pytest
from pathlib import Path
import gu_library_worker.convert as convert_mod
from gu_library_worker.convert import to_pdf, ConversionError, build_command, resolve_soffice

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

# --- soffice resolution (Bug 1: no PATH dependency on Windows) ---

def test_resolve_prefers_env_var(tmp_path, monkeypatch):
    fake = tmp_path / "soffice.exe"; fake.write_text("x")
    other = tmp_path / "other.exe"; other.write_text("y")
    monkeypatch.setenv("GULIB_SOFFICE", str(fake))
    monkeypatch.setattr(convert_mod, "_WINDOWS_SOFFICE_PATHS", (str(other),))
    assert resolve_soffice() == str(fake)        # env wins over standard paths

def test_resolve_uses_standard_install_when_no_env(tmp_path, monkeypatch):
    monkeypatch.delenv("GULIB_SOFFICE", raising=False)
    std = tmp_path / "soffice.exe"; std.write_text("x")
    monkeypatch.setattr(convert_mod, "_WINDOWS_SOFFICE_PATHS", (str(std),))
    assert resolve_soffice() == str(std)

def test_resolve_falls_back_to_path(tmp_path, monkeypatch):
    monkeypatch.delenv("GULIB_SOFFICE", raising=False)
    monkeypatch.setattr(convert_mod, "_WINDOWS_SOFFICE_PATHS", ())  # none on disk
    found = str(tmp_path / "soffice")
    monkeypatch.setattr(convert_mod.shutil, "which",
                        lambda name: found if name == "soffice" else None)
    assert resolve_soffice() == found

def test_resolve_raises_clear_error_when_missing(monkeypatch):
    monkeypatch.delenv("GULIB_SOFFICE", raising=False)
    monkeypatch.setattr(convert_mod, "_WINDOWS_SOFFICE_PATHS", ())
    monkeypatch.setattr(convert_mod.shutil, "which", lambda name: None)
    with pytest.raises(ConversionError) as exc:
        resolve_soffice()
    msg = str(exc.value)
    assert "GULIB_SOFFICE" in msg and "LibreOffice" in msg
    assert "WinError" not in msg                  # actionable, not a raw OSError

def test_to_pdf_auto_resolves_when_soffice_omitted(tmp_path, monkeypatch):
    src = tmp_path / "in.docx"; src.write_bytes(b"x")
    outdir = tmp_path / "out"; outdir.mkdir()
    expected = outdir / "in.pdf"
    fake_soffice = tmp_path / "soffice.exe"; fake_soffice.write_text("x")
    monkeypatch.setenv("GULIB_SOFFICE", str(fake_soffice))

    captured = {}
    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        expected.write_bytes(b"%PDF-1.4\n")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(subprocess, "run", fake_run)

    assert to_pdf(src, outdir) == expected        # no soffice arg -> resolved
    assert captured["cmd"][0] == str(fake_soffice)
