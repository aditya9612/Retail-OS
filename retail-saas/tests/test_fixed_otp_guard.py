import importlib
import sys
import os
import pytest


def reload_main(monkeypatch, env_vars):
    """Helper to reload app.main with given environment variables.
    Returns the imported module (or raises if import fails)."""
    from app.core.config import get_settings
    get_settings.cache_clear()
    for k, v in env_vars.items():
        monkeypatch.setenv(k, v)
    # Ensure previous import is cleared
    if "app.main" in sys.modules:
        del sys.modules["app.main"]
    # Import the module fresh
    res = importlib.import_module("app.main")
    get_settings.cache_clear()
    return res


def test_development_fixed_otp_allowed(monkeypatch):
    # Development (default) with fixed OTP enabled should load without error
    env = {"AUTH_FIXED_OTP_ENABLED": "true"}
    mod = reload_main(monkeypatch, env)
    assert mod is not None


def test_staging_fixed_otp_allowed(monkeypatch):
    env = {"APP_ENV": "staging", "AUTH_FIXED_OTP_ENABLED": "true"}
    mod = reload_main(monkeypatch, env)
    assert mod is not None


def test_production_fixed_otp_disabled_allowed(monkeypatch):
    env = {"APP_ENV": "production", "AUTH_FIXED_OTP_ENABLED": "false"}
    mod = reload_main(monkeypatch, env)
    assert mod is not None


def test_production_fixed_otp_enabled_fails(monkeypatch):
    env = {"APP_ENV": "production", "AUTH_FIXED_OTP_ENABLED": "true"}
    with pytest.raises(RuntimeError) as excinfo:
        reload_main(monkeypatch, env)
    assert "Fixed OTP must be disabled in production" in str(excinfo.value)
