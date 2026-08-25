"""R3.3 drills: storage seam — Protocol satisfied by SQLite, Postgres refuses."""

from __future__ import annotations

import pytest

from ai_doctor.storage.backends import (
    CaseStoreProtocol,
    PostgresCaseStore,
    open_sqlite_store,
)


def test_sqlite_store_satisfies_the_protocol(tmp_path):
    store = open_sqlite_store(tmp_path / "cds.db")
    assert isinstance(store, CaseStoreProtocol)


def test_postgres_skeleton_refuses_without_driver():
    with pytest.raises((RuntimeError, NotImplementedError, ValueError)):
        PostgresCaseStore("postgresql://user:pass@localhost/ai_doctor")


def test_postgres_skeleton_rejects_non_postgres_dsn():
    with pytest.raises(ValueError):
        PostgresCaseStore("sqlite:///tmp/x.db")


def test_default_creation_path_still_sqlite(tmp_path):
    # The app's default path constructs SQLite directly.
    from ai_doctor.storage.sqlite import SqliteRepository

    assert isinstance(open_sqlite_store(tmp_path / "x.db"), SqliteRepository)
