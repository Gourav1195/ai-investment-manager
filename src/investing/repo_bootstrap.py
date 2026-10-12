"""Ensure the repository root is importable as ``src.*`` (Streamlit Cloud, local runs)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT: Path | None = None


def repo_root() -> Path:
    """Return the repository root (parent of the ``src`` package)."""

    global _REPO_ROOT
    if _REPO_ROOT is not None:
        return _REPO_ROOT
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    return _REPO_ROOT


def ensure_repo_root_on_path() -> Path:
    """Insert the repo root at the front of ``sys.path`` if needed."""

    root = repo_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root


def default_work_dir() -> Path:
    """Writable data directory (``work/`` under repo root unless overridden)."""

    import os

    override = os.environ.get("INVESTING_WORK_DIR")
    if override:
        path = Path(override)
    else:
        path = repo_root() / "work"
    path.mkdir(parents=True, exist_ok=True)
    return path
