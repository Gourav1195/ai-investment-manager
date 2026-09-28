"""Versioned scoring profile storage and activation."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import sqlite3
from pathlib import Path
from typing import Iterator, Mapping

from .filings import IST
from .scoring_profiles import INDUSTRY_PROFILES, Metric, metrics_for

PROFILE_STORE_VERSION = 1


@dataclass(frozen=True)
class ProfileVersionSummary:
    profile_version: int
    metric_count: int
    source: str
    created_at: str
    is_active: bool


class ScoringProfileStore:
    """Persist and activate calibrated industry scoring thresholds."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def save_version(
        self,
        profile_version: int,
        profiles: Mapping[str, tuple[Metric, ...]],
        *,
        source: str,
    ) -> int:
        if profile_version < 1:
            raise ValueError("profile_version must be at least 1")
        if not profiles:
            raise ValueError("At least one entity profile is required")
        if self.version_exists(profile_version):
            raise ValueError(f"Profile version {profile_version} already exists")

        created_at = datetime.now(tz=IST).isoformat()
        inserted = 0
        with self._connect() as connection:
            for entity_type, entity_metrics in profiles.items():
                for metric in entity_metrics:
                    connection.execute(
                        """
                        INSERT INTO scoring_profile_metrics (
                            profile_version,
                            entity_type,
                            metric,
                            category,
                            direction,
                            poor,
                            strong,
                            source,
                            created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            profile_version,
                            entity_type.strip().lower(),
                            metric.column,
                            metric.category,
                            metric.direction,
                            metric.poor,
                            metric.strong,
                            source.strip(),
                            created_at,
                        ),
                    )
                    inserted += 1
        return inserted

    def activate(self, profile_version: int) -> None:
        if not self.version_exists(profile_version):
            raise ValueError(f"Profile version {profile_version} does not exist")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO scoring_profile_active (
                    id,
                    profile_version,
                    activated_at
                ) VALUES (1, ?, ?)
                """,
                (profile_version, datetime.now(tz=IST).isoformat()),
            )

    def active_version(self) -> int | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT profile_version FROM scoring_profile_active WHERE id = 1"
            ).fetchone()
        return int(row["profile_version"]) if row else None

    def version_exists(self, profile_version: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM scoring_profile_metrics
                WHERE profile_version = ?
                LIMIT 1
                """,
                (profile_version,),
            ).fetchone()
        return row is not None

    def list_versions(self) -> list[ProfileVersionSummary]:
        active = self.active_version()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    profile_version,
                    COUNT(*) AS metric_count,
                    MIN(source) AS source,
                    MIN(created_at) AS created_at
                FROM scoring_profile_metrics
                GROUP BY profile_version
                ORDER BY profile_version DESC
                """
            ).fetchall()
        return [
            ProfileVersionSummary(
                profile_version=int(row["profile_version"]),
                metric_count=int(row["metric_count"]),
                source=str(row["source"]),
                created_at=str(row["created_at"]),
                is_active=active == int(row["profile_version"]),
            )
            for row in rows
        ]

    def metrics_for(
        self,
        entity_type: str | None,
        profile_version: int | None = None,
    ) -> tuple[Metric, ...] | None:
        version = profile_version if profile_version is not None else self.active_version()
        if version is None:
            return None
        normalized = (entity_type or "non_bank").strip().lower()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT metric, category, direction, poor, strong
                FROM scoring_profile_metrics
                WHERE profile_version = ? AND entity_type = ?
                ORDER BY metric
                """,
                (version, normalized),
            ).fetchall()
        if not rows:
            return None
        return tuple(
            Metric(
                column=str(row["metric"]),
                category=str(row["category"]),
                direction=str(row["direction"]),
                poor=float(row["poor"]),
                strong=float(row["strong"]),
            )
            for row in rows
        )

    def load_version(self, profile_version: int) -> dict[str, tuple[Metric, ...]]:
        profiles: dict[str, tuple[Metric, ...]] = {}
        for entity_type in INDUSTRY_PROFILES:
            metrics = self.metrics_for(entity_type, profile_version)
            if metrics:
                profiles[entity_type] = metrics
        if not profiles:
            raise ValueError(f"Profile version {profile_version} does not exist")
        return profiles

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS scoring_profile_metrics (
                    profile_version INTEGER NOT NULL,
                    entity_type TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    category TEXT NOT NULL,
                    direction TEXT NOT NULL CHECK (direction IN ('higher', 'lower')),
                    poor REAL NOT NULL,
                    strong REAL NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (profile_version, entity_type, metric)
                );

                CREATE TABLE IF NOT EXISTS scoring_profile_active (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    profile_version INTEGER NOT NULL,
                    activated_at TEXT NOT NULL
                );
                """)


def resolve_metrics(
    entity_type: str | None,
    *,
    profile_store: ScoringProfileStore | None = None,
    profile_version: int | None = None,
) -> tuple[Metric, ...]:
    """Return stored profile metrics when active, otherwise built-in defaults."""

    if profile_store is not None:
        stored = profile_store.metrics_for(entity_type, profile_version)
        if stored:
            return stored
    return metrics_for(entity_type)
