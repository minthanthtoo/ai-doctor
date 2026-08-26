"""9router env-contract drills: NINE_ROUTER_* fills generic gateway vars."""

from __future__ import annotations

from ai_doctor.nine_router import apply_nine_router_defaults
from ai_doctor.settings import Settings


def test_nine_router_fills_endpoint_and_key(monkeypatch):
    monkeypatch.setenv("NINE_ROUTER_BASE_URL", "http://localhost:4000/v1")
    monkeypatch.setenv("NINE_ROUTER_API_KEY", "test-key-123")
    monkeypatch.setenv("AI_DOCTOR_MODEL_GATEWAY_MODEL", "free")
    settings = Settings.from_env()
    assert settings.model_gateway_endpoint == "http://localhost:4000/v1/chat/completions"
    assert settings.model_gateway_api_key == "test-key-123"
    assert settings.model_gateway_model == "free"


def test_explicit_gateway_vars_win_over_nine_router(monkeypatch):
    monkeypatch.setenv("NINE_ROUTER_BASE_URL", "http://localhost:4000/v1")
    monkeypatch.setenv("NINE_ROUTER_API_KEY", "nine-key")
    monkeypatch.setenv("AI_DOCTOR_MODEL_GATEWAY_ENDPOINT", "http://127.0.0.1:9999/v1/chat/completions")
    monkeypatch.setenv("AI_DOCTOR_MODEL_GATEWAY_API_KEY", "explicit-key")
    monkeypatch.setenv("AI_DOCTOR_MODEL_GATEWAY_MODEL", "free")
    settings = Settings.from_env()
    assert settings.model_gateway_endpoint == "http://127.0.0.1:9999/v1/chat/completions"
    assert settings.model_gateway_api_key == "explicit-key"


def test_no_nine_router_vars_is_noop(monkeypatch):
    monkeypatch.delenv("NINE_ROUTER_BASE_URL", raising=False)
    monkeypatch.delenv("NINE_ROUTER_API_KEY", raising=False)
    env = {"NINE_ROUTER_API_KEY": ""}
    apply_nine_router_defaults(env)  # must not raise, must not set anything
    assert "AI_DOCTOR_MODEL_GATEWAY_ENDPOINT" not in (env or {})


def test_enabled_gateway_via_nine_router_passes_validation(monkeypatch):
    """Full loop: 9router vars + enabled flag satisfy Settings validation."""
    monkeypatch.setenv("AI_DOCTOR_ENV", "preclinical")
    monkeypatch.setenv("NINE_ROUTER_BASE_URL", "http://localhost:4000/v1")
    monkeypatch.setenv("NINE_ROUTER_API_KEY", "k")
    monkeypatch.setenv("AI_DOCTOR_MODEL_GATEWAY_MODEL", "free")
    monkeypatch.setenv("AI_DOCTOR_MODEL_GATEWAY_ENABLED", "true")
    settings = Settings.from_env()  # raises if validation rejects localhost http
    assert settings.model_gateway_enabled is True


def test_chat_completions_suffix_not_duplicated(monkeypatch):
    from ai_doctor.nine_router import apply_nine_router_defaults

    env = {
        "NINE_ROUTER_BASE_URL": "http://localhost:4000/v1/chat/completions",
        "NINE_ROUTER_API_KEY": "k",
    }
    apply_nine_router_defaults(env)
    assert env["AI_DOCTOR_MODEL_GATEWAY_ENDPOINT"].count("chat/completions") == 1
