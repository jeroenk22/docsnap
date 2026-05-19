"""
docs-scraper/convert_to_pdf.py
Converteert een Markdown-bestand naar een nette PDF via Playwright (Chromium).
Geen externe systeembibliotheken nodig.

Gebruik:
    python convert_to_pdf.py mendrix_docs.md
    python convert_to_pdf.py output.md --out mijn_rapport.pdf
"""

import argparse
from html import escape
import sys
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

CSS = """
@page { size: A4; margin: 2.2cm 2.5cm; }
body {
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 10.5pt; line-height: 1.65; color: #1a1a2e;
}
h1 { font-size: 22pt; color: #0d47a1; border-bottom: 2px solid #1565c0;
     padding-bottom: 6pt; margin-top: 24pt; }
h2 { font-size: 16pt; color: #1565c0; margin-top: 18pt;
     border-bottom: 1px solid #bbdefb; padding-bottom: 4pt; }
h3 { font-size: 13pt; color: #1976d2; margin-top: 14pt; }
h4 { font-size: 11pt; color: #1e88e5; margin-top: 10pt; }
hr { border: none; border-top: 1px solid #e0e0e0; margin: 20pt 0; }
a  { color: #1565c0; text-decoration: none; }
blockquote {
    border-left: 3px solid #90caf9; margin: 0 0 10pt 0;
    padding: 4pt 10pt; background: #e3f2fd;
    color: #555; font-size: 9pt; border-radius: 2pt;
}
code {
    font-family: 'Consolas', monospace; font-size: 9pt;
    background: #f5f5f5; padding: 1pt 4pt;
    border-radius: 3pt; color: #c62828;
}
pre {
    background: #1e1e2e; color: #cdd6f4;
    padding: 10pt 12pt; border-radius: 5pt;
    font-size: 8.5pt; line-height: 1.5;
    border-left: 3px solid #89b4fa; margin: 8pt 0;
    white-space: pre-wrap; word-break: break-all;
}
pre code { background: transparent; color: inherit; padding: 0; }
table {
    border-collapse: collapse; width: 100%;
    margin: 8pt 0; font-size: 9.5pt;
}
th { background: #1565c0; color: white; padding: 5pt 8pt;
     text-align: left; font-weight: 600; }
td { padding: 4pt 8pt; border-bottom: 1px solid #e0e0e0; vertical-align: top; }
tr:nth-child(even) td { background: #f8f9fa; }
ul, ol { padding-left: 18pt; margin: 4pt 0; }
li { margin-bottom: 3pt; }
img { max-width: 100%; height: auto; }
p   { margin: 0 0 7pt 0; }
"""


def convert(input_md: Path, output_pdf: Path, title: str = "Documentatie") -> None:
    print(f"  [pdf] Lees {input_md} …")
    md_text = input_md.read_text(encoding="utf-8")
    escaped_title = escape(title)

    print("  [pdf] Markdown → HTML …")
    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br", "attr_list"],
    )

    html = f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="utf-8">
  <title>{escaped_title}</title>
  <style>{CSS}</style>
</head>
<body>{body}</body>
</html>"""

    print("  [pdf] Render PDF via Playwright …")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="networkidle")
        page.pdf(
            path=str(output_pdf),
            format="A4",
            margin={"top": "2.2cm", "bottom": "2.2cm", "left": "2.5cm", "right": "2.5cm"},
            display_header_footer=True,
            header_template=f'<div style="font-size:9pt;color:#888;width:100%;text-align:left;padding-left:2.5cm">{escaped_title}</div>',
            footer_template='<div style="font-size:9pt;color:#888;width:100%;text-align:right;padding-right:2.5cm">Pagina <span class="pageNumber"></span> van <span class="totalPages"></span></div>',
        )
        browser.close()

    mb = output_pdf.stat().st_size / 1_048_576
    print(f"✅  PDF → {output_pdf}  ({mb:.1f} MB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Markdown → PDF")
    parser.add_argument("input",   help="Markdown-bestand (bijv. mendrix_docs.md)")
    parser.add_argument("--out",   help="Output PDF-pad (standaard: zelfde naam als input)")
    parser.add_argument("--title", default="Documentatie", help="Titel in paginaheader")
    args = parser.parse_args()

    inp = Path(args.input)
    if not inp.exists():
        sys.exit(f"❌  Bestand niet gevonden: {inp}")

    out = Path(args.out) if args.out else inp.with_suffix(".pdf")
    convert(inp, out, title=args.title)
