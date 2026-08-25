"""R3.2 drills: structured logs are JSON, PHI-free; metrics counters work."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi.testclient import TestClient
from test_longitudinal_relay import PATIENT_HEADERS, _settings
from test_privacy_surface import CANARY_NAME as CANARY  # sentinel reuse

from ai_doctor.api import create_app
from ai_doctor.observability import JsonFormatter, install_observability


def _capture(client: TestClient, caplog, actions):
    with caplog.at_level(logging.DEBUG, logger="ai_doctor.requests"):
        actions(client)
    formatter = JsonFormatter()
    return [
        formatter.format(r)
        for r in caplog.records
        if r.name == "ai_doctor.requests"
    ]


def test_request_log_is_json_with_whitelisted_fields_only(tmp_path: Path, caplog):
    client = TestClient(create_app(_settings(tmp_path)))
    lines = _capture(client, caplog, lambda c: c.get("/health"))
    assert lines, "expected at least one request log line"
    for line in lines:
        payload = json.loads(line)  # every rendered line is valid JSON
        assert set(payload.keys()) <= {
            "ts",
            "level",
            "event",
            "method",
            "path",
            "status",
            "duration_ms",
        }


def test_query_strings_never_reach_the_log(tmp_path: Path, caplog):
    client = TestClient(create_app(_settings(tmp_path)))

    def actions(c: TestClient):
        # Profile pseudonym rides the query string on this endpoint.
        c.get(
            "/v1/sync/envelopes",
            headers=PATIENT_HEADERS,
            params={"profile_pseudonym": CANARY, "cursor": 0},
        )

    records = _capture(client, caplog, actions)
    assert records
    combined = "\n".join(records)
    assert CANARY not in combined, "pseudonym leaked into request log"


def test_metrics_endpoint_counts_requests(tmp_path: Path):
    from ai_doctor.observability import reset_metrics_for_tests

    reset_metrics_for_tests()
    settings = _settings(tmp_path)
    app = create_app(settings)
    install_observability(app, settings)
    client = TestClient(app)
    client.get("/health")
    client.get("/health")
    snapshot = client.get("/v1/operations/metrics").json()
    keys = [k for k in snapshot["counters"] if k.startswith("http.get.")]
    total = sum(snapshot["counters"][k] for k in keys)
    # Two /health probes counted; the metrics response itself may or may not
    # pass through the middleware depending on route registration order.
    assert total >= 2


def test_install_is_idempotent(tmp_path: Path):
    settings = _settings(tmp_path)
    app = create_app(settings)
    install_observability(app, settings)
    middleware_after_first = len(app.user_middleware)
    install_observability(app, settings)
    assert len(app.user_middleware) == middleware_after_first  # no duplicate
    client = TestClient(app)
    assert client.get("/health").status_code == 200
