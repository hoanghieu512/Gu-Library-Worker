# tests/conftest.py
import pytest
from docx import Document as Docx
from pptx import Presentation
from pptx.util import Inches
import fitz  # PyMuPDF

@pytest.fixture
def make_docx(tmp_path):
    def _make(name: str, paragraphs: list[str]) -> "pathlib.Path":
        d = Docx()
        for p in paragraphs:
            d.add_paragraph(p)
        out = tmp_path / name
        d.save(out)
        return out
    return _make

@pytest.fixture
def make_pptx(tmp_path):
    def _make(name: str, slide_texts: list[str]) -> "pathlib.Path":
        prs = Presentation()
        blank = prs.slide_layouts[6]
        for t in slide_texts:
            slide = prs.slides.add_slide(blank)
            box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(2))
            box.text_frame.text = t
        out = tmp_path / name
        prs.save(out)
        return out
    return _make

@pytest.fixture
def make_pdf(tmp_path):
    def _make(name: str, pages: list[str]) -> "pathlib.Path":
        doc = fitz.open()
        for body in pages:
            page = doc.new_page()
            page.insert_text((72, 72), body, fontsize=12)
        out = tmp_path / name
        doc.save(out)
        doc.close()
        return out
    return _make
