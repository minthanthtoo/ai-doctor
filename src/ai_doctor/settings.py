from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse


@dataclass(frozen=True)
class Settings:
    environment: str
    database_path: Path
    emergency_service_label: str
    tokens: Dict[str, Dict[str, str]]
    protocol_path: Optional[Path] = None
    protocol_public_keys: Dict[str, str] = field(default_factory=dict)
    allow_test_protocols: bool = False
    model_gateway_enabled: bool = False
    model_gateway_endpoint: Optional[str] = None
    model_gateway_model: Optional[str] = None
    model_gateway_api_key: Optional[str] = None
    model_gateway_timeout_seconds: float = 20.0
    model_gateway_release: str = "optional-diagnosis-model-0.1.0"
    model_gateway_allowed_hosts: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.emergency_service_label.strip() or len(self.emergency_service_label) > 200:
            raise RuntimeError("emergency service label must contain 1 to 200 characters")
        if self.model_gateway_enabled:
            _validate_model_gateway_configuration(
                environment=self.environment,
                endpoint=self.model_gateway_endpoint,
                model=self.model_gateway_model,
                timeout_seconds=self.model_gateway_timeout_seconds,
                allowed_hosts=self.model_gateway_allowed_hosts,
            )

    @classmethod
    def from_env(cls) -> "Settings":
        environment = os.getenv("AI_DOCTOR_ENV", "preclinical").strip().lower()
        database_path = Path(
            os.getenv("AI_DOCTOR_DATABASE", "./data/ai_doctor_preclinical.db")
        ).expanduser()
        emergency_service_label = os.getenv(
            "AI_DOCTOR_EMERGENCY_SERVICE_LABEL", "local emergency services"
        ).strip()

        raw_tokens = os.getenv("AI_DOCTOR_TOKENS_JSON")
        if raw_tokens:
            tokens = json.loads(raw_tokens)
        elif environment == "preclinical":
            tokens = {
                "preclinical-physician-token": {
                    "user_id": "preclinical-physician",
                    "role": "physician",
                },
                "preclinical-pharmacist-token": {
                    "user_id": "preclinical-pharmacist",
                    "role": "pharmacist",
                },
                "preclinical-patient-token": {
                    "user_id": "preclinical-patient",
                    "role": "patient",
                },
                "preclinical-safety-token": {
                    "user_id": "preclinical-safety-officer",
                    "role": "clinical_safety_officer",
                },
            }
        else:
            raise RuntimeError(
                "AI_DOCTOR_TOKENS_JSON is required outside preclinical mode; "
                "the bundled demonstration credentials are never enabled in production"
            )

        if environment == "production" and any(
            token.startswith("preclinical-") for token in tokens
        ):
            raise RuntimeError("preclinical credentials are prohibited in production")

        protocol_path_text = os.getenv("AI_DOCTOR_PROTOCOL_PATH")
        protocol_path = Path(protocol_path_text).expanduser() if protocol_path_text else None
        protocol_public_keys = json.loads(os.getenv("AI_DOCTOR_PROTOCOL_PUBLIC_KEYS_JSON", "{}"))
        allow_test_protocols = os.getenv("AI_DOCTOR_ALLOW_TEST_PROTOCOLS", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        if environment != "preclinical" and allow_test_protocols:
            raise RuntimeError("test protocols are prohibited outside preclinical mode")

        model_gateway_enabled = os.getenv("AI_DOCTOR_MODEL_GATEWAY_ENABLED", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        model_gateway_endpoint = os.getenv("AI_DOCTOR_MODEL_GATEWAY_ENDPOINT")
        model_gateway_model = os.getenv("AI_DOCTOR_MODEL_GATEWAY_MODEL")
        allowed_hosts = tuple(
            host.strip().lower()
            for host in os.getenv("AI_DOCTOR_MODEL_GATEWAY_ALLOWED_HOSTS", "").split(",")
            if host.strip()
        )

        return cls(
            environment=environment,
            database_path=database_path,
            emergency_service_label=emergency_service_label,
            tokens=tokens,
            protocol_path=protocol_path,
            protocol_public_keys=protocol_public_keys,
            allow_test_protocols=allow_test_protocols,
            model_gateway_enabled=model_gateway_enabled,
            model_gateway_endpoint=model_gateway_endpoint,
            model_gateway_model=model_gateway_model,
            model_gateway_api_key=os.getenv("AI_DOCTOR_MODEL_GATEWAY_API_KEY"),
            model_gateway_timeout_seconds=float(
                os.getenv("AI_DOCTOR_MODEL_GATEWAY_TIMEOUT_SECONDS", "20")
            ),
            model_gateway_release=os.getenv(
                "AI_DOCTOR_MODEL_GATEWAY_RELEASE", "optional-diagnosis-model-0.1.0"
            ),
            model_gateway_allowed_hosts=allowed_hosts,
        )


def _validate_model_gateway_configuration(
    *,
    environment: str,
    endpoint: Optional[str],
    model: Optional[str],
    timeout_seconds: float,
    allowed_hosts: Tuple[str, ...],
) -> None:
    if not endpoint or not model:
        raise RuntimeError(
            "AI_DOCTOR_MODEL_GATEWAY_ENDPOINT and AI_DOCTOR_MODEL_GATEWAY_MODEL "
            "are required when the optional model gateway is enabled"
        )
    if not 1.0 <= timeout_seconds <= 60.0:
        raise RuntimeError("model gateway timeout must be between 1 and 60 seconds")
    parsed = urlparse(endpoint)
    hostname = (parsed.hostname or "").lower()
    if not hostname or parsed.username or parsed.password:
        raise RuntimeError("model gateway endpoint must be an absolute URL without credentials")
    local_preclinical = environment == "preclinical" and hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local_preclinical):
        raise RuntimeError("model gateway endpoint must use HTTPS outside preclinical localhost")
    if allowed_hosts and hostname not in allowed_hosts:
        raise RuntimeError("model gateway endpoint host is not in the configured allowlist")
    if environment != "preclinical" and not allowed_hosts:
        raise RuntimeError(
            "AI_DOCTOR_MODEL_GATEWAY_ALLOWED_HOSTS is required outside preclinical mode"
        )
