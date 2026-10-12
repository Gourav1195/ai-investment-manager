from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "src.investing.cli", *args],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
    )


def test_cli_help_lists_major_commands() -> None:
    completed = _run_cli("--help")
    assert completed.returncode == 0
    for command in (
        "universe",
        "prices",
        "filings",
        "fundamentals",
        "walkforward",
        "dashboard",
        "portfolio",
        "constituents",
        "profiles",
        "calibrate",
        "orchestrate",
        "schedule",
    ):
        assert command in completed.stdout


def test_portfolio_subcommands_help() -> None:
    completed = _run_cli("portfolio", "import", "--help")
    assert completed.returncode == 0
    assert "--kind" in completed.stdout
