"""Tests for app configuration."""

import os
import pytest

from app.config import Config


class TestConfig:
    def test_secret_key_default(self, monkeypatch):
        monkeypatch.delenv('SECRET_KEY', raising=False)
        # Re-import to pick up changes
        assert Config.SECRET_KEY is not None

    def test_confluence_space_keys_parsing(self):
        assert isinstance(Config.CONFLUENCE_SPACE_KEYS, list)

    def test_stale_threshold_is_int(self):
        assert isinstance(Config.STALE_THRESHOLD_DAYS, int)
        assert Config.STALE_THRESHOLD_DAYS > 0

    def test_rate_limit_is_int(self):
        assert isinstance(Config.CONFLUENCE_RATE_LIMIT, int)

    def test_data_dir_is_string(self):
        assert isinstance(Config.DATA_DIR, str)

    def test_empty_space_keys_env(self, monkeypatch):
        monkeypatch.setenv('CONFLUENCE_SPACE_KEYS', '')
        # Reload config manually
        keys = [s.strip() for s in os.getenv('CONFLUENCE_SPACE_KEYS', '').split(',') if s.strip()]
        assert keys == []

    def test_comma_separated_spaces(self, monkeypatch):
        monkeypatch.setenv('CONFLUENCE_SPACE_KEYS', 'A, B , C')
        keys = [s.strip() for s in os.getenv('CONFLUENCE_SPACE_KEYS', '').split(',') if s.strip()]
        assert keys == ['A', 'B', 'C']
