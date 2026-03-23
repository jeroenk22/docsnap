"""
tests/test_convert_to_pdf.py
Tests voor convert_to_pdf.py.
WeasyPrint wordt gemockt omdat het GTK-systeembibliotheken vereist die
niet in alle omgevingen aanwezig zijn.
"""

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


# ── WeasyPrint mocken vóór import ─────────────────────────────────────────────

def _mock_weasyprint():
    wp = ModuleType("weasyprint")
    wp.HTML = MagicMock()
    wp.CSS  = MagicMock()
    # HTML(...).write_pdf(...) schrijft een minimale PDF-byte-string
    mock_html_instance = MagicMock()
    mock_html_instance.write_pdf = MagicMock(side_effect=lambda path, **_: Path(path).write_bytes(b"%PDF-1.4 test"))
    wp.HTML.return_value = mock_html_instance
    sys.modules["weasyprint"] = wp


_mock_weasyprint()

from convert_to_pdf import convert  # noqa: E402  (import na mock)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestConvert:
    def test_maakt_pdf_aan(self, tmp_path):
        md = tmp_path / "doc.md"
        md.write_text("# Hallo\n\nDit is een test.", encoding="utf-8")
        pdf = tmp_path / "doc.pdf"

        convert(md, pdf, title="Test")

        assert pdf.exists()
        assert pdf.stat().st_size > 0

    def test_output_pad_configureerbaar(self, tmp_path):
        md = tmp_path / "input.md"
        md.write_text("# Test\n\nInhoud.", encoding="utf-8")
        pdf = tmp_path / "custom_output.pdf"

        convert(md, pdf, title="Custom")

        assert pdf.exists()

    def test_werkt_met_tabellen(self, tmp_path):
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

    def test_werkt_met_codeblok(self, tmp_path):
        md = tmp_path / "code.md"
        md.write_text("# Code\n\n```python\nprint('hello')\n```\n", encoding="utf-8")
        pdf = tmp_path / "code.pdf"
        convert(md, pdf, title="Code Test")
        assert pdf.exists()

    def test_lege_markdown(self, tmp_path):
        md = tmp_path / "empty.md"
        md.write_text("", encoding="utf-8")
        pdf = tmp_path / "empty.pdf"
        convert(md, pdf, title="Leeg")
        assert pdf.exists()

    def test_html_aanroep_bevat_titel(self, tmp_path):
        """CSS-template moet de opgegeven titel bevatten."""
        import weasyprint
        md = tmp_path / "doc.md"
        md.write_text("# Test", encoding="utf-8")
        pdf = tmp_path / "doc.pdf"

        convert(md, pdf, title="Speciale Titel")

        css_call = weasyprint.CSS.call_args
        assert css_call is not None
        css_string = css_call.kwargs.get("string", "") or (css_call.args[0] if css_call.args else "")
        assert "Speciale Titel" in css_string
