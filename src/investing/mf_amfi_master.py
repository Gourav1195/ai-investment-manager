"""Parse AMFI NAVAll.txt into scheme metadata and SEBI categories."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class SchemeMasterRow:
    scheme_code: str
    scheme_name: str
    category: str
    plan_type: str
    option_type: str
    is_direct: bool
    is_growth: bool


_CATEGORY_RE = re.compile(r"\(([^)]+)\)\s*$")


def parse_amfi_nav_all(text: str) -> pd.DataFrame:
    """Return scheme master rows from AMFI NAVAll.txt content."""

    current_category = "Unknown"
    rows: list[dict[str, object]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if ";" not in stripped:
            match = _CATEGORY_RE.search(stripped)
            if match:
                current_category = _normalize_category(match.group(1))
            continue
        parts = [part.strip() for part in stripped.split(";")]
        if len(parts) < 5:
            continue
        scheme_code = parts[0]
        if not scheme_code.isdigit():
            continue
        scheme_name = parts[3] if len(parts) >= 6 and parts[3] else parts[1]
        plan_type, option_type, is_direct, is_growth = _classify_plan_option(scheme_name)
        rows.append(
            {
                "scheme_code": scheme_code,
                "scheme_name": scheme_name,
                "category": current_category,
                "plan_type": plan_type,
                "option_type": option_type,
                "is_direct": int(is_direct),
                "is_growth": int(is_growth),
            }
        )
    return pd.DataFrame(rows)


def _normalize_category(value: str) -> str:
    text = value.strip()
    text = re.sub(r"^\s*Open Ended Schemes\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*Close Ended Schemes\s*", "", text, flags=re.IGNORECASE)
    return text.strip() or "Unknown"


def _classify_plan_option(scheme_name: str) -> tuple[str, str, bool, bool]:
    upper = scheme_name.upper()
    is_direct = "DIRECT" in upper
    plan_type = "Direct" if is_direct else "Regular"
    if "IDCW" in upper or "DIVIDEND" in upper:
        return plan_type, "IDCW", is_direct, False
    return plan_type, "Growth", is_direct, True


def peer_bucket_key(category: str, plan_type: str, option_type: str) -> str:
    return f"{category}|{plan_type}|{option_type}"
