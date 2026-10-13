"""Optional Postgres blob store so Streamlit Cloud data survives redeploys."""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BLOB_RESEARCH = "research_db"
BLOB_PORTFOLIO = "portfolio_db"
BLOB_UI_PREFS = "ui_prefs"

_BLOB_FILES: dict[str, str] = {
    BLOB_RESEARCH: "research.db",
    BLOB_PORTFOLIO: "portfolio.db",
    BLOB_UI_PREFS: "ui_prefs.json",
}

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS investing_app_blobs (
    name VARCHAR(64) PRIMARY KEY,
    payload BYTEA NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


class PersistenceMode(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"
    CLOUD_DEGRADED = "cloud_degraded"


@dataclass(frozen=True)
class PersistenceState:
    mode: PersistenceMode
    message: str | None = None


def resolve_database_url() -> str | None:
    """Read ``DATABASE_URL`` from Streamlit secrets or environment (never logged)."""

    value: Any = None
    try:
        import streamlit as st

        value = st.secrets.get("DATABASE_URL")
    except Exception:
        value = None
    if value:
        text = str(value).strip()
        return text or None
    env = os.environ.get("DATABASE_URL", "").strip()
    return env or None


def is_cloud_persistence_configured() -> bool:
    return bool(resolve_database_url())


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _connect_engine(url: str):
    from sqlalchemy import create_engine

    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 15},
    )


def _ensure_schema(engine) -> None:
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text(_SCHEMA_SQL))


def _remote_blobs(engine) -> dict[str, tuple[bytes, str, datetime]]:
    from sqlalchemy import text

    out: dict[str, tuple[bytes, str, datetime]] = {}
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT name, payload, sha256, updated_at FROM investing_app_blobs"
            )
        ).fetchall()
    for name, payload, sha256, updated_at in rows:
        key = str(name)
        ts = updated_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        out[key] = (bytes(payload), str(sha256), ts)
    return out


def pull_cloud_blobs(work_dir: Path, *, url: str | None = None) -> PersistenceState:
    """Download remote blobs into ``work_dir`` when newer or missing locally."""

    database_url = url or resolve_database_url()
    if not database_url:
        return PersistenceState(PersistenceMode.LOCAL)

    try:
        engine = _connect_engine(database_url)
        _ensure_schema(engine)
        remote = _remote_blobs(engine)
    except Exception:
        logger.exception("Cloud database pull failed")
        return PersistenceState(
            PersistenceMode.CLOUD_DEGRADED,
            "Could not reach your cloud database. Using temporary local storage until it is fixed.",
        )

    work_dir.mkdir(parents=True, exist_ok=True)
    for blob_name, filename in _BLOB_FILES.items():
        if blob_name not in remote:
            continue
        payload, _remote_sha, remote_ts = remote[blob_name]
        local_path = work_dir / filename
        use_remote = not local_path.is_file()
        if local_path.is_file():
            local_mtime = datetime.fromtimestamp(
                local_path.stat().st_mtime, tz=timezone.utc
            )
            if remote_ts > local_mtime:
                use_remote = True
        if use_remote:
            local_path.write_bytes(payload)

    return PersistenceState(
        PersistenceMode.CLOUD,
        None,
    )


def push_cloud_blobs(work_dir: Path, *, url: str | None = None) -> PersistenceState:
    """Upload local blob files to Postgres when cloud persistence is enabled."""

    database_url = url or resolve_database_url()
    if not database_url:
        return PersistenceState(PersistenceMode.LOCAL)

    try:
        engine = _connect_engine(database_url)
        _ensure_schema(engine)
    except Exception:
        logger.exception("Cloud database push failed")
        return PersistenceState(
            PersistenceMode.CLOUD_DEGRADED,
            "Could not save to your cloud database. Download a backup from Import & backup.",
        )

    from sqlalchemy import text

    try:
        with engine.begin() as conn:
            for blob_name, filename in _BLOB_FILES.items():
                local_path = work_dir / filename
                if not local_path.is_file():
                    continue
                payload = local_path.read_bytes()
                sha = hashlib.sha256(payload).hexdigest()
                conn.execute(
                    text(
                        """
                        INSERT INTO investing_app_blobs (name, payload, sha256, updated_at)
                        VALUES (:name, :payload, :sha256, NOW())
                        ON CONFLICT (name) DO UPDATE SET
                            payload = EXCLUDED.payload,
                            sha256 = EXCLUDED.sha256,
                            updated_at = EXCLUDED.updated_at
                        WHERE investing_app_blobs.sha256 <> EXCLUDED.sha256
                        """
                    ),
                    {"name": blob_name, "payload": payload, "sha256": sha},
                )
    except Exception:
        logger.exception("Cloud database push failed")
        return PersistenceState(
            PersistenceMode.CLOUD_DEGRADED,
            "Could not save to your cloud database. Download a backup from Import & backup.",
        )

    return PersistenceState(PersistenceMode.CLOUD, None)


def sync_session_cloud_data(work_dir: Path) -> PersistenceState:
    """
    Pull once per Streamlit session, then push when local files change.

    Returns the current persistence state for UI badges.
    """

    url = resolve_database_url()
    if not url:
        return PersistenceState(PersistenceMode.LOCAL)

    flag = "_cloud_pulled"
    import streamlit as st

    if not st.session_state.get(flag):
        state = pull_cloud_blobs(work_dir, url=url)
        st.session_state["_cloud_persistence_state"] = state
        if state.mode == PersistenceMode.CLOUD_DEGRADED:
            return state
        st.session_state[flag] = True
    else:
        state = st.session_state.get(
            "_cloud_persistence_state",
            PersistenceState(PersistenceMode.CLOUD),
        )

    # A failed push is retried on the next interaction with the same local files.
    hashes: dict[str, str] = {}
    for _blob, filename in _BLOB_FILES.items():
        path = work_dir / filename
        digest = _file_sha256(path)
        if digest:
            hashes[filename] = digest

    last_pushed = st.session_state.get("_cloud_last_pushed_hashes", {})
    if hashes != last_pushed:
        push_state = push_cloud_blobs(work_dir, url=url)
        if push_state.mode == PersistenceMode.CLOUD_DEGRADED:
            st.session_state["_cloud_persistence_state"] = push_state
            return push_state
        st.session_state["_cloud_last_pushed_hashes"] = dict(hashes)
        st.session_state["_cloud_persistence_state"] = PersistenceState(
            PersistenceMode.CLOUD,
            None,
        )

    return st.session_state.get(
        "_cloud_persistence_state",
        PersistenceState(PersistenceMode.CLOUD),
    )


def persistence_state_without_streamlit(work_dir: Path) -> PersistenceState:
    """Test/helper entry: pull then push using only environment configuration."""

    url = resolve_database_url()
    if not url:
        return PersistenceState(PersistenceMode.LOCAL)
    pull = pull_cloud_blobs(work_dir, url=url)
    if pull.mode == PersistenceMode.CLOUD_DEGRADED:
        return pull
    return push_cloud_blobs(work_dir, url=url)
