"""
tests/test_convert_to_pdf.py
Tests voor convert_to_pdf.py.
Playwright wordt gemockt zodat de tests geen echte Chromium-run nodig hebben.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from convert_to_pdf import convert


@pytest.fixture
def mock_playwright():
    page = MagicMock()

    def write_pdf(path, **_):
        Path(path).write_bytes(b"%PDF-1.4 test")

    page.pdf.side_effect = write_pdf

    browser = MagicMock()
    browser.new_page.return_value = page

    chromium = MagicMock()
    chromium.launch.return_value = browser

    pw = MagicMock()
    pw.chromium = chromium

    manager = MagicMock()
    manager.__enter__.return_value = pw
    manager.__exit__.return_value = None

    with patch("convert_to_pdf.sync_playwright", return_value=manager) as patched:
        yield page, patched


class TestConvert:
    def test_maakt_pdf_aan(self, tmp_path, mock_playwright):
        md = tmp_path / "doc.md"
        md.write_text("# Hallo\n\nDit is een test.", encoding="utf-8")
        pdf = tmp_path / "doc.pdf"

        convert(md, pdf, title="Test")

        assert pdf.exists()
        assert pdf.stat().st_size > 0

    def test_output_pad_configureerbaar(self, tmp_path, mock_playwright):
        md = tmp_path / "input.md"
        md.write_text("# Test\n\nInhoud.", encoding="utf-8")
        pdf = tmp_path / "custom_output.pdf"

        convert(md, pdf, title="Custom")

        assert pdf.exists()

    def test_werkt_met_tabellen(self, tmp_path, mock_playwright):
        md = tmp_path / "table.md"
        md.write_text(
            "# Tabel\n\n"
            "| Naam | Waarde |\n"
            "| ---- | ------ |\n"
            "| foo  | 42     |\n",
            encoding="utf-8",
        )
        pdf = tmp_path / "table.pdf"
        convert(md, pdf, title="Tabel Test")
        assert pdf.exists()

    def test_werkt_met_codeblok(self, tmp_path, mock_playwright):
        md = tmp_path / "code.md"
        md.write_text("# Code\n\n```python\nprint('hello')\n```\n", encoding="utf-8")
        pdf = tmp_path / "code.pdf"
        convert(md, pdf, title="Code Test")
        assert pdf.exists()

    def test_lege_markdown(self, tmp_path, mock_playwright):
        md = tmp_path / "empty.md"
        md.write_text("", encoding="utf-8")
        pdf = tmp_path / "empty.pdf"
        convert(md, pdf, title="Leeg")
        assert pdf.exists()

    def test_html_aanroep_bevat_titel(self, tmp_path, mock_playwright):
        page, _ = mock_playwright
        md = tmp_path / "doc.md"
        md.write_text("# Test", encoding="utf-8")
        pdf = tmp_path / "doc.pdf"

        convert(md, pdf, title="Speciale Titel")

        html = page.set_content.call_args.args[0]
        pdf_kwargs = page.pdf.call_args.kwargs
        assert "<title>Speciale Titel</title>" in html
        assert "Speciale Titel" in pdf_kwargs["header_template"]

    def test_title_wordt_geescaped(self, tmp_path, mock_playwright):
        page, _ = mock_playwright
        md = tmp_path / "doc.md"
        md.write_text("# Test", encoding="utf-8")
        pdf = tmp_path / "doc.pdf"

        convert(md, pdf, title="Docs & <API>")

        html = page.set_content.call_args.args[0]
        pdf_kwargs = page.pdf.call_args.kwargs
        assert "<title>Docs &amp; &lt;API&gt;</title>" in html
        assert "Docs &amp; &lt;API&gt;" in pdf_kwargs["header_template"]
