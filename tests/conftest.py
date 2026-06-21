# tests/conftest.py
import html as _html_module
from pathlib import Path
import pytest
from docx import Document as Docx
from pptx import Presentation
from pptx.util import Inches
import fitz  # PyMuPDF

@pytest.fixture
def make_docx(tmp_path):
    def _make(name: str, paragraphs: list[str]) -> Path:
        d = Docx()
        for p in paragraphs:
            d.add_paragraph(p)
        out = tmp_path / name
        d.save(out)
        return out
    return _make

@pytest.fixture
def make_pptx(tmp_path):
    def _make(name: str, slide_texts: list[str]) -> Path:
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
    def _make(name: str, pages: list[str]) -> Path:
        # Use fitz.Story + DocumentWriter so Vietnamese Unicode survives the
        # roundtrip. Page.insert_text() only supports the PDF base-14 Latin
        # character set and silently corrupts Vietnamese glyphs.
        out = tmp_path / name
        mb = fitz.paper_rect("a4")
        where = mb + (36, 36, -36, -36)
        writer = fitz.DocumentWriter(str(out))
        for body in pages:
            safe = _html_module.escape(body).replace("\n", "<br>")
            story = fitz.Story(html=f"<p>{safe}</p>")
            dev = writer.begin_page(mb)
            story.place(where)
            story.draw(dev, None)
            writer.end_page()
        writer.close()
        return out
    return _make
