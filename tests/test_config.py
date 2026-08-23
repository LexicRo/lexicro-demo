import pytest
from app.config import load_settings, Settings


def test_load_settings_reads_environment(monkeypatch):
    monkeypatch.setenv("LEXICRO_API_BASE", "https://example.test")
    monkeypatch.setenv("LEXICRO_DEMO_KEY", "lxr_abc")
    monkeypatch.setenv("SESSION_SECRET", "s3cret")
    s = load_settings()
    assert s.api_base == "https://example.test"
    assert s.api_key == "lxr_abc"
    assert s.session_secret == "s3cret"
    assert s.max_chars == 500
    assert s.trust_proxy is True


def test_trailing_slash_is_stripped_from_base(monkeypatch):
    monkeypatch.setenv("LEXICRO_API_BASE", "https://example.test/")
    monkeypatch.setenv("LEXICRO_DEMO_KEY", "lxr_abc")
    monkeypatch.setenv("SESSION_SECRET", "s3cret")
    assert load_settings().api_base == "https://example.test"


def test_missing_key_fails_loudly_by_name(monkeypatch):
    monkeypatch.delenv("LEXICRO_DEMO_KEY", raising=False)
    monkeypatch.setenv("SESSION_SECRET", "s3cret")
    with pytest.raises(RuntimeError, match="LEXICRO_DEMO_KEY"):
        load_settings()


def test_settings_are_frozen(monkeypatch):
    monkeypatch.setenv("LEXICRO_DEMO_KEY", "lxr_abc")
    monkeypatch.setenv("SESSION_SECRET", "s3cret")
    s = load_settings()
    with pytest.raises(Exception):
        s.api_key = "other"


def test_cookie_secure_defaults_true_and_can_be_disabled(monkeypatch):
    monkeypatch.setenv("LEXICRO_DEMO_KEY", "lxr_abc")
    monkeypatch.setenv("SESSION_SECRET", "s3cret")
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    assert load_settings().cookie_secure is True
    monkeypatch.setenv("COOKIE_SECURE", "false")
    assert load_settings().cookie_secure is False
