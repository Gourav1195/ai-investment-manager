from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from src.investing.portfolio_store import PortfolioStore
from src.investing.zerodha_import import parse_equity_holdings

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "zerodha_portfolio"


def test_malformed_equity_csv_raises_clear_error(tmp_path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Could not map required columns"):
        parse_equity_holdings(path)


def test_xlsx_equity_import_round_trip(tmp_path) -> None:
    csv_path = EXAMPLES / "equity_holdings.example.csv"
    xlsx_path = tmp_path / "holdings.xlsx"
    pd.read_csv(csv_path).to_excel(xlsx_path, index=False)
    frame = parse_equity_holdings(xlsx_path)
    assert len(frame) == 3


def test_portfolio_show_empty_database(tmp_path) -> None:
    db = tmp_path / "empty.db"
    PortfolioStore(db)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.investing.cli",
            "portfolio",
            "show",
            "--database",
            str(db),
            "--no-fetch",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "Portfolio summary" in completed.stdout
