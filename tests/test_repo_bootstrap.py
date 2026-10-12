from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_import_dashboard_from_foreign_cwd(tmp_path) -> None:
    repo = Path(__file__).resolve().parents[1]
    snippet = (
        "import sys; "
        f"sys.path.insert(0, r'{repo}'); "
        "from src.investing.repo_bootstrap import ensure_repo_root_on_path; "
        "ensure_repo_root_on_path(); "
        "from src.investing.dashboard import main; "
        "assert callable(main)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", snippet],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_ensure_repo_root_on_path() -> None:
    from src.investing.repo_bootstrap import ensure_repo_root_on_path, repo_root

    root = ensure_repo_root_on_path()
    assert (root / "src" / "investing" / "dashboard.py").exists()
    assert repo_root() == root
