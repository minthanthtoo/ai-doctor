"""9router custom-endpoint support for the optional model gateway.

The gateway already speaks OpenAI-compatible JSON; this adds a convenience
env contract used by the operator's 9router setup:

    NINE_ROUTER_BASE_URL   e.g. http://localhost:4000/v1   (optional)
    NINE_ROUTER_API_KEY    bearer key                       (optional)

When NINE_ROUTER_* values are present AND the generic gateway vars are
unset, they fill AI_DOCTOR_MODEL_GATEWAY_{ENDPOINT,API_KEY}. The model
name still comes from AI_DOCTOR_MODEL_GATEWAY_MODEL (e.g. "free").
Nothing here relaxes endpoint validation — localhost http stays
preclinical-only.
"""

from __future__ import annotations

import os


def apply_nine_router_defaults(env: dict[str, str] | None = None) -> None:
    """Fill generic gateway env vars from 9router ones when unset. Idempotent."""
    environ = os.environ if env is None else env

    base_url = environ.get("NINE_ROUTER_BASE_URL", "").strip()
    api_key = environ.get("NINE_ROUTER_API_KEY", "").strip()
    if not base_url and not api_key:
        return

    if base_url and not environ.get("AI_DOCTOR_MODEL_GATEWAY_ENDPOINT"):
        endpoint = base_url.rstrip("/")
        # Accept both bare base (…/v1) and chat-completions style; normalize to
        # the full completions URL the transport posts to.
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"
        environ["AI_DOCTOR_MODEL_GATEWAY_ENDPOINT"] = endpoint
    if api_key and not environ.get("AI_DOCTOR_MODEL_GATEWAY_API_KEY"):
        environ["AI_DOCTOR_MODEL_GATEWAY_API_KEY"] = api_key
