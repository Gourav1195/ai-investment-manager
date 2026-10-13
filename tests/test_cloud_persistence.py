from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from src.investing.cloud_persistence import (
    PersistenceMode,
    pull_cloud_blobs,
    push_cloud_blobs,
    resolve_database_url,
)
from src.investing.portfolio_store import PortfolioStore


def test_resolve_database_url_from_environment(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert resolve_database_url() is None
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    assert resolve_database_url() == "postgresql://u:p@localhost/db"


def test_pull_push_without_url_returns_local(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    state = pull_cloud_blobs(tmp_path)
    assert state.mode == PersistenceMode.LOCAL


def test_bad_database_url_degrades_gracefully(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://bad:bad@127.0.0.1:1/nope")
    state = pull_cloud_blobs(tmp_path)
    assert state.mode == PersistenceMode.CLOUD_DEGRADED
    assert state.message


@pytest.fixture(scope="module")
def postgres_url() -> str:
    """Start a throwaway Postgres container when Docker is available."""

    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True, timeout=30)
    except (subprocess.SubprocessError, FileNotFoundError):
        pytest.skip("Docker not available")

    name = "investing-cloud-persist-test"
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "-e",
            "POSTGRES_PASSWORD=testpass",
            "-e",
            "POSTGRES_DB=investing",
            "-p",
            "55432:5432",
            "postgres:16-alpine",
        ],
        check=True,
        capture_output=True,
    )
    url = "postgresql://postgres:testpass@127.0.0.1:55432/investing"
    for _ in range(30):
        try:
            from sqlalchemy import create_engine, text

            engine = create_engine(url)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            break
        except Exception:
            time.sleep(1)
    else:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        pytest.fail("Postgres container did not become ready")
    yield url
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def test_restart_simulation_with_postgres(
    tmp_path: Path,
    postgres_url: str,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url)

    work_a = tmp_path / "session_a"
    work_a.mkdir()
    portfolio_path = work_a / "portfolio.db"
    PortfolioStore(portfolio_path)
    prefs_path = work_a / "ui_prefs.json"
    prefs_path.write_text(
        json.dumps({"display_name": "Cloud Tester", "onboarding_complete": True}),
        encoding="utf-8",
    )

    push_state = push_cloud_blobs(work_a, url=postgres_url)
    assert push_state.mode == PersistenceMode.CLOUD

    work_b = tmp_path / "session_b"
    work_b.mkdir()
    pull_state = pull_cloud_blobs(work_b, url=postgres_url)
    assert pull_state.mode == PersistenceMode.CLOUD
    assert (work_b / "portfolio.db").is_file()
    assert json.loads((work_b / "ui_prefs.json").read_text())["display_name"] == "Cloud Tester"

    PortfolioStore(work_b / "portfolio.db")


def test_cloud_auth_requires_password_with_database_url(monkeypatch) -> None:
    from src.investing.cloud_auth import _configured_password

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    assert _configured_password() is None
    # Integration with Streamlit is covered by import smoke; policy is enforced in require_app_password.
