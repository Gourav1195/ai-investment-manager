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


def _coerce_secret_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("url", "connection_string", "DATABASE_URL", "database_url"):
            nested = value.get(key)
            if nested:
                return _coerce_secret_value(nested)
        return None
    text = str(value).strip()
    if not text:
        return None
    if (text.startswith('"') and text.endswith('"')) or (
        text.startswith("'") and text.endswith("'")
    ):
        text = text[1:-1].strip()
    return text or None


def normalize_database_url(url: str) -> str:
    """Normalize Postgres URLs for SQLAlchemy + psycopg2 on Streamlit Cloud."""

    text = url.strip()
    lowered = text.lower()
    if lowered.startswith("postgres://"):
        text = "postgresql+psycopg2://" + text[len("postgres://") :]
    elif lowered.startswith("postgresql://"):
        text = "postgresql+psycopg2://" + text[len("postgresql://") :]
    elif lowered.startswith("postgresql+psycopg2://"):
        pass
    elif lowered.startswith("postgresql+psycopg://"):
        text = "postgresql+psycopg2://" + text[len("postgresql+psycopg://") :]

    host = ""
    try:
        from sqlalchemy.engine.url import make_url

        parsed = make_url(text)
        host = (parsed.host or "").lower()
    except Exception:
        host = ""

    if host and host not in {"localhost", "127.0.0.1"} and "sslmode=" not in text.lower():
        text = f"{text}&sslmode=require" if "?" in text else f"{text}?sslmode=require"
    return text


def _safe_database_target(url: str) -> str:
    try:
        from sqlalchemy.engine.url import make_url

        parsed = make_url(url)
        host = parsed.host or "unknown-host"
        database = parsed.database or "unknown-db"
        driver = parsed.drivername or "postgresql"
        port = f":{parsed.port}" if parsed.port else ""
        return f"{driver}://{host}{port}/{database}"
    except Exception:
        return "configured Postgres (could not parse DATABASE_URL)"


def format_cloud_error(action: str, exc: Exception, database_url: str) -> str:
    detail = f"{type(exc).__name__}: {exc}"
    target = _safe_database_target(database_url)
    logger.error(
        "Cloud database %s failed (%s): %s",
        action,
        target,
        detail,
        exc_info=True,
    )
    return (
        f"Could not {action} your cloud database. Using temporary local storage until it is fixed. "
        f"Details: {detail} — target {_safe_database_target(database_url)}. "
        "Check Streamlit secrets: DATABASE_URL must be a Postgres URI "
        "(postgresql://… or postgres://… from Neon/Supabase, usually with ?sslmode=require)."
    )


def resolve_database_url() -> str | None:
    """Read ``DATABASE_URL`` from Streamlit secrets or environment (never logged)."""

    value: Any = None
    try:
        import streamlit as st

        if hasattr(st, "secrets"):
            if "DATABASE_URL" in st.secrets:
                value = st.secrets["DATABASE_URL"]
            else:
                value = st.secrets.get("DATABASE_URL")
            if not value and "postgres" in st.secrets:
                value = st.secrets["postgres"]
    except Exception:
        value = None
    text = _coerce_secret_value(value)
    if not text:
        text = os.environ.get("DATABASE_URL", "").strip() or None
    if not text:
        return None
    return normalize_database_url(text)


def is_cloud_persistence_configured() -> bool:
    return bool(resolve_database_url())


def is_streamlit_community_cloud() -> bool:
    """True when running on Streamlit Community Cloud (not local ``streamlit run``)."""

    return os.environ.get("STREAMLIT_RUNTIME_ENVIRONMENT", "").strip().lower() == "cloud"


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
    except Exception as exc:
        return PersistenceState(
            PersistenceMode.CLOUD_DEGRADED,
            format_cloud_error("reach", exc, database_url),
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
    except Exception as exc:
        return PersistenceState(
            PersistenceMode.CLOUD_DEGRADED,
            format_cloud_error("save to", exc, database_url),
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
    except Exception as exc:
        return PersistenceState(
            PersistenceMode.CLOUD_DEGRADED,
            format_cloud_error("save to", exc, database_url),
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
