"""Alternate Streamlit entry when the app file lives under ``src/investing/``."""

from pathlib import Path
import sys

# Streamlit Cloud may set cwd/sys.path to this file's directory only.
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.investing.repo_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from src.investing.dashboard import main

main()
