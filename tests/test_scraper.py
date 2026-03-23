"""
tests/test_scraper.py
Unit tests voor de helper-functies in scraper.py.
"""

import textwrap
from pathlib import Path

import pytest

from scraper import clean_url, is_in_scope, resolve_credentials


# ── clean_url ─────────────────────────────────────────────────────────────────

class TestCleanUrl:
    def test_verwijdert_fragment(self):
        assert clean_url("https://docs.example.com/page#section") == "https://docs.example.com/page"

    def test_verwijdert_trailing_slash(self):
        assert clean_url("https://docs.example.com/guide/") == "https://docs.example.com/guide"

    def test_behoudt_query_string(self):
        assert clean_url("https://docs.example.com/search?q=test") == "https://docs.example.com/search?q=test"

    def test_fragment_en_trailing_slash(self):
        assert clean_url("https://docs.example.com/guide/#top") == "https://docs.example.com/guide"

    def test_al_schoon(self):
        assert clean_url("https://docs.example.com/guide") == "https://docs.example.com/guide"


# ── is_in_scope ───────────────────────────────────────────────────────────────

class TestIsInScope:
    BASE = "https://docs.example.com"
    SCOPE = ["/guide", "/api"]

    def test_url_in_scope(self):
        assert is_in_scope(f"{self.BASE}/guide/intro", self.BASE, self.SCOPE) is True

    def test_url_api_in_scope(self):
        assert is_in_scope(f"{self.BASE}/api/v1/endpoints", self.BASE, self.SCOPE) is True

    def test_url_buiten_scope(self):
        assert is_in_scope(f"{self.BASE}/blog/post", self.BASE, self.SCOPE) is False

    def test_ander_domein(self):
        assert is_in_scope("https://other.com/guide/intro", self.BASE, self.SCOPE) is False

    def test_lege_scope(self):
        assert is_in_scope(f"{self.BASE}/anything", self.BASE, []) is False

    def test_root_scope(self):
        assert is_in_scope(f"{self.BASE}/whatever", self.BASE, ["/"]) is True


# ── resolve_credentials ───────────────────────────────────────────────────────

class TestResolveCredentials:
    def test_credentials_uit_cfg(self):
        cfg = {"username": "user@example.com", "password": "secret"}
        u, p = resolve_credentials(cfg)
        assert u == "user@example.com"
        assert p == "secret"

    def test_credentials_uit_env_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("MY_USER=alice\nMY_PASS=wonderland\n")
        cfg = {
            "env_file": str(env_file),
            "username_env": "MY_USER",
            "password_env": "MY_PASS",
        }
        u, p = resolve_credentials(cfg)
        assert u == "alice"
        assert p == "wonderland"

    def test_env_file_heeft_prioriteit_boven_cfg(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("MY_USER=env_user\nMY_PASS=env_pass\n")
        cfg = {
            "env_file": str(env_file),
            "username_env": "MY_USER",
            "password_env": "MY_PASS",
            "username": "cfg_user",
            "password": "cfg_pass",
        }
        u, p = resolve_credentials(cfg)
        assert u == "env_user"
        assert p == "env_pass"

    def test_geen_credentials(self):
        u, p = resolve_credentials({})
        assert u == ""
        assert p == ""

    def test_ontbrekend_env_sleutel_valt_terug_op_cfg(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("ANDERE_VAR=x\n")
        cfg = {
            "env_file": str(env_file),
            "username_env": "NIET_AANWEZIG",
            "password_env": "OOK_NIET",
            "username": "fallback_user",
            "password": "fallback_pass",
        }
        u, p = resolve_credentials(cfg)
        assert u == "fallback_user"
        assert p == "fallback_pass"
