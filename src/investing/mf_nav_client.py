"""Fetch mutual fund NAV history from mfapi.in with local caching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any

import pandas as pd
import requests

from .mf_amfi_master import parse_amfi_nav_all
from .portfolio_store import PortfolioStore

MFAPI_SCHEME_URL = "https://api.mfapi.in/mf/{scheme_code}"
AMFI_NAV_ALL_URL = "https://www.amfiindia.com/spages/NAVAll.txt"


@dataclass(frozen=True)
class SchemeNavSeries:
    scheme_code: str
    scheme_name: str
    category: str | None
    plan_type: str | None
    option_type: str | None
    nav: pd.DataFrame


class MfNavClient:
    """Download scheme metadata and NAV history, persisting to SQLite."""

    def __init__(
        self,
        store: PortfolioStore,
        session: requests.Session | None = None,
    ) -> None:
        self.store = store
        self._session = session or requests.Session()

    def sync_scheme_master_from_amfi(self, *, text: str | None = None) -> int:
        payload = text if text is not None else self._session.get(AMFI_NAV_ALL_URL, timeout=90).text
        frame = parse_amfi_nav_all(payload)
        return self.store.replace_scheme_master(frame)

    def sync_scheme_nav(self, scheme_code: str, *, force: bool = False) -> SchemeNavSeries:
        code = str(scheme_code).strip()
        if not force and self.store.has_nav_history(code):
            return self._series_from_store(code)
        response = self._session.get(MFAPI_SCHEME_URL.format(scheme_code=code), timeout=60)
        response.raise_for_status()
        payload = response.json()
        return self._persist_payload(code, payload)

    def _persist_payload(self, scheme_code: str, payload: dict[str, Any]) -> SchemeNavSeries:
        meta = payload.get("meta") or {}
        scheme_name = str(meta.get("scheme_name") or scheme_code)
        category = meta.get("scheme_category")
        plan_type, option_type = _plan_option_from_meta(meta, scheme_name)
        rows = payload.get("data") or []
        nav_rows: list[tuple[str, float]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            nav_date = _parse_mfapi_date(str(item.get("date", "")))
            try:
                nav = float(str(item.get("nav")).replace(",", ""))
            except (TypeError, ValueError):
                continue
            nav_rows.append((nav_date, nav))
        self.store.upsert_nav_history(scheme_code, nav_rows)
        master = self.store.get_scheme_master_row(scheme_code)
        if master:
            category = category or master.get("category")
            plan_type = plan_type or master.get("plan_type")
            option_type = option_type or master.get("option_type")
            scheme_name = master.get("scheme_name") or scheme_name
        self.store.upsert_scheme_meta(
            scheme_code,
            scheme_name=scheme_name,
            category=str(category) if category else None,
            plan_type=plan_type,
            option_type=option_type,
        )
        return self._series_from_store(scheme_code)

    def _series_from_store(self, scheme_code: str) -> SchemeNavSeries:
        meta = self.store.get_scheme_meta(scheme_code)
        nav = self.store.get_nav_history(scheme_code)
        return SchemeNavSeries(
            scheme_code=scheme_code,
            scheme_name=str(meta.get("scheme_name") or scheme_code),
            category=meta.get("category"),
            plan_type=meta.get("plan_type"),
            option_type=meta.get("option_type"),
            nav=nav,
        )


def _parse_mfapi_date(value: str) -> str:
    parsed = datetime.strptime(value.strip(), "%d-%m-%Y")
    return parsed.date().isoformat()


def _plan_option_from_meta(meta: dict[str, Any], scheme_name: str) -> tuple[str | None, str | None]:
    scheme_type = str(meta.get("scheme_type") or "").upper()
    upper = scheme_name.upper()
    is_direct = "DIRECT" in upper or "DIRECT" in scheme_type
    plan_type = "Direct" if is_direct else "Regular"
    if "IDCW" in upper or "DIVIDEND" in upper:
        return plan_type, "IDCW"
    return plan_type, "Growth"


def load_scheme_master_fixture(store: PortfolioStore, text: str) -> int:
    """Test helper: load AMFI master text without HTTP."""

    client = MfNavClient(store, session=_OfflineSession())
    return client.sync_scheme_master_from_amfi(text=text)


class _OfflineSession:
    def get(self, url: str, timeout: int = 60) -> Any:
        raise RuntimeError(f"Unexpected HTTP in offline session: {url}")
