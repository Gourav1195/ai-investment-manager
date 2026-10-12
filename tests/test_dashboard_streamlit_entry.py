from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_dashboard_streamlit_entry_imports() -> None:
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "-c", "from src.investing.dashboard import main; assert callable(main)"],
        cwd=root,
        env={**__import__("os").environ, "PYTHONPATH": str(root)},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
