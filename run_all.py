"""
run_all.py  —  Scrape + PDF in één stap.

Gebruik:
    python run_all.py sites/mendrix.yaml
    python run_all.py sites/example.yaml --visible --title "Example Docs"
"""

import argparse
import subprocess
import sys
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape + PDF in één stap")
    parser.add_argument("config",  help="YAML-config (bijv. sites/mendrix.yaml)")
    parser.add_argument("--visible", action="store_true", help="Browser zichtbaar")
    parser.add_argument("--title",   default=None, help="Titel in PDF-header")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        sys.exit(f"❌  Config niet gevonden: {config_path}")

    # Lees output-pad en titel uit YAML
    cfg       = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    output_md = Path(cfg.get("output", "output.md"))
    title     = args.title or cfg.get("title", "Documentatie")

    # ── Stap 1: scrapen ───────────────────────────────────────────────────────
    print("=" * 60)
    print(f"  Stap 1/2 — Documentatie scrapen  ({config_path.name})")
    print("=" * 60)
    scrape_cmd = [sys.executable, "scraper.py", str(config_path)]
    if args.visible:
        scrape_cmd.append("--visible")

    r1 = subprocess.run(scrape_cmd)
    if r1.returncode != 0:
        sys.exit("❌  Scraper mislukt.")

    # ── Stap 2: PDF ───────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  Stap 2/2 — PDF genereren")
    print("=" * 60)
    pdf_cmd = [
        sys.executable, "convert_to_pdf.py", str(output_md),
        "--title", title,
    ]
    r2 = subprocess.run(pdf_cmd)
    if r2.returncode != 0:
        sys.exit("❌  PDF conversie mislukt.")

    print()
    print(f"🎉  Klaar!  →  {output_md}  +  {output_md.with_suffix('.pdf')}")


if __name__ == "__main__":
    main()
