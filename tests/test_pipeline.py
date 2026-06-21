# tests/test_pipeline.py
import shutil
from pathlib import Path
from gu_library_worker.pipeline import process_one_file, Prepared
from gu_library_worker.schema import validate_sidecar

def _fake_convert(src, outdir, **kw):
    # for non-pdf, pretend LibreOffice rendered a 1-page pdf with the text
    import fitz
    out = outdir / (src.stem + ".pdf")
    doc = fitz.open(); page = doc.new_page()
    page.insert_text((72, 72), "Điều 1. Phạm vi điều chỉnh", fontsize=12)
    doc.save(out); doc.close()
    return out

def test_docx_pipeline_produces_valid_sidecar(make_docx, tmp_path):
    src = make_docx("[Luật X] luat.docx", [
        "Điều 1. Phạm vi điều chỉnh",
        "Luật này quy định về công chứng.",
    ])
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    assert isinstance(prepared, Prepared)
    assert prepared.subject == "Luật X"
    assert prepared.clean_name == "luat.docx"
    assert prepared.sidecar["sourceFormat"] == "docx"
    assert prepared.sidecar["source"] == "share"
    assert prepared.sidecar["kind"] == "legal"
    assert prepared.sidecar["pageCount"] >= 1
    assert prepared.sidecar["addedAt"].endswith("+07:00")
    assert validate_sidecar(prepared.sidecar) == []

def test_pdf_origin_keeps_original_as_canonical(make_pdf, tmp_path):
    src = make_pdf("[Luật Y] vb.pdf", ["Điều 1. Nội dung trang một."])
    prepared = process_one_file(src, tmp_workdir=tmp_path / "w", convert_fn=_fake_convert)
    assert prepared.sidecar["sourceFormat"] == "pdf"
    # canonical pdf is the original bytes (no reconvert)
    assert prepared.canonical_pdf.read_bytes() == src.read_bytes()
