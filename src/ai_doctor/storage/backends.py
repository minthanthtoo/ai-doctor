"""R3.3: storage backend abstraction.

A typing.Protocol describes what the app needs from a case store; SQLite is
the shipped implementation and stays the default. The Postgres adapter is a
skeleton: constructor validates DSN shape and refuses to run (fail closed) —
it exists so the seam is proven without shipping an untested driver path.

ponytail: no async, no connection pooling, no ORM. Add when a real Postgres
deployment exists; the Protocol is the only contract that matters.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ai_doctor.storage.sqlite import SqliteRepository


@runtime_checkable
class CaseStoreProtocol(Protocol):
    """The surface api.py actually uses from a case repository."""

    def create_case(self, case: object) -> object: ...

    def get_case(self, case_id: str) -> object: ...


def open_sqlite_store(database_path: Path) -> "SqliteRepository":
    from ai_doctor.storage.sqlite import SqliteRepository

    return SqliteRepository(database_path)


class PostgresCaseStore:
    """Skeleton adapter — refuses construction until the driver lands."""

    def __init__(self, dsn: str) -> None:
        if not dsn.startswith(("postgresql://", "postgres://")):
            raise ValueError("PostgresCaseStore requires a postgres:// DSN")
        try:
            import psycopg  # noqa: F401
        except ImportError as error:  # pragma: no cover - depends on env
            raise RuntimeError(
                "Postgres backend not installed in this build; "
                "SQLite remains the default store."
            ) from error
        raise NotImplementedError(
            "Postgres adapter is a skeleton; implement against CaseStoreProtocol "
            "when a real deployment requires it."
        )
