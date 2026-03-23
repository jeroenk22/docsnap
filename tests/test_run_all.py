"""
tests/test_run_all.py
Tests voor run_all.py — gebruikt mocks zodat geen echte scraper of PDF
wordt gestart.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

import run_all


def maak_config(tmp_path: Path, output: str = "out.md", title: str = "Docs") -> Path:
    cfg = {"title": title, "base_url": "https://example.com", "output": output}
    p = tmp_path / "test.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


class TestMain:
    def test_succesvol_pad(self, tmp_path, monkeypatch):
        config = maak_config(tmp_path)
        monkeypatch.setattr(sys, "argv", ["run_all.py", str(config)])

        ok = MagicMock(returncode=0)
        with patch("run_all.subprocess.run", return_value=ok) as mock_run:
            run_all.main()

        assert mock_run.call_count == 2

    def test_scraper_fout_stopt_uitvoering(self, tmp_path, monkeypatch):
        config = maak_config(tmp_path)
        monkeypatch.setattr(sys, "argv", ["run_all.py", str(config)])

        fail = MagicMock(returncode=1)
        with patch("run_all.subprocess.run", return_value=fail):
            with pytest.raises(SystemExit):
                run_all.main()

    def test_pdf_fout_stopt_uitvoering(self, tmp_path, monkeypatch):
        config = maak_config(tmp_path)
        monkeypatch.setattr(sys, "argv", ["run_all.py", str(config)])

        ok   = MagicMock(returncode=0)
        fail = MagicMock(returncode=1)
        with patch("run_all.subprocess.run", side_effect=[ok, fail]):
            with pytest.raises(SystemExit):
                run_all.main()

    def test_config_niet_gevonden_stopt(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["run_all.py", str(tmp_path / "bestaat_niet.yaml")])
        with pytest.raises(SystemExit):
            run_all.main()

    def test_visible_flag_wordt_doorgegeven(self, tmp_path, monkeypatch):
        config = maak_config(tmp_path)
        monkeypatch.setattr(sys, "argv", ["run_all.py", str(config), "--visible"])

        ok = MagicMock(returncode=0)
        with patch("run_all.subprocess.run", return_value=ok) as mock_run:
            run_all.main()

        scraper_call = mock_run.call_args_list[0]
        assert "--visible" in scraper_call.args[0]

    def test_title_uit_yaml(self, tmp_path, monkeypatch):
        config = maak_config(tmp_path, title="Mijn Titel")
        monkeypatch.setattr(sys, "argv", ["run_all.py", str(config)])

        ok = MagicMock(returncode=0)
        with patch("run_all.subprocess.run", return_value=ok) as mock_run:
            run_all.main()

        pdf_call = mock_run.call_args_list[1]
        assert "Mijn Titel" in pdf_call.args[0]

    def test_custom_title_overschrijft_yaml(self, tmp_path, monkeypatch):
        config = maak_config(tmp_path, title="YAML Titel")
        monkeypatch.setattr(sys, "argv", ["run_all.py", str(config), "--title", "Custom Titel"])

        ok = MagicMock(returncode=0)
        with patch("run_all.subprocess.run", return_value=ok) as mock_run:
            run_all.main()

        pdf_call = mock_run.call_args_list[1]
        assert "Custom Titel" in pdf_call.args[0]
