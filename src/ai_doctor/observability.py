"""R3.2 observability: structured JSON request logs + counters, PHI-free.

Design ceiling (ponytail): stdlib logging with a JSON formatter and an
in-process counter registry — no external metrics stack until a real
deployment needs scraping. Upgrade path: swap Metrics.record for a
Prometheus client; formatter stays.

Contract:
- Every relay request logs one JSON line: ts, event, method, path, status,
  duration_ms. No query strings, no bodies, no profile pseudonyms.
- /v1/operations/metrics returns the counters as JSON.
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Response

from ai_doctor.settings import Settings


def _iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class JsonFormatter(logging.Formatter):
    """One JSON object per record; only whitelisted fields ever leave."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": _iso_now(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for key in ("method", "path", "status", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        record.msg = json.dumps(payload, separators=(",", ":"))
        record.args = ()
        return record.msg


class Metrics:
    """Thread-unsafe-on-purpose simple counters (single-process relay)."""

    def __init__(self) -> None:
        self.counters: Counter[str] = Counter()
        self.started_at = _iso_now()

    def record(self, name: str, amount: int = 1) -> None:
        self.counters[name] += amount

    def snapshot(self) -> dict:
        return {
            "started_at": self.started_at,
            "counters": dict(sorted(self.counters.items())),
        }


_metrics = Metrics()
_request_logger = logging.getLogger("ai_doctor.requests")


def install_observability(app: FastAPI, settings: Settings) -> None:
    """Attach the structured-access-log + counter middleware. Idempotent."""
    for middleware in app.user_middleware:
        dispatch = getattr(middleware, "dispatch", None) or getattr(
            middleware.kwargs.get("dispatch", None), "__name__", ""
        )
        fn = getattr(middleware, "fn", None)
        if (fn is not None and getattr(fn, "__name__", "") == "_observability_middleware") or (
            dispatch == "_observability_middleware"
        ):
            return

    @app.middleware("http")
    async def _observability_middleware(request: Request, call_next):
        start = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            path = request.url.path
            status_code = response.status_code if response is not None else 500
            # Path only — never the query string (may carry profile params).
            _request_logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": path,
                    "status": status_code,
                    "duration_ms": duration_ms,
                },
            )
            _metrics.record(f"http.{request.method.lower()}.{status_code}")

    @app.get("/v1/operations/metrics")
    def operations_metrics() -> dict:
        return _metrics.snapshot()


def metrics_snapshot() -> dict:
    """Read-only view for tests and health dashboards."""
    return _metrics.snapshot()


def reset_metrics_for_tests() -> None:
    global _metrics
    _metrics = Metrics()
