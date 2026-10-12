"""Streamlit Community Cloud entrypoint (repo root)."""

from src.investing.repo_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from src.investing.dashboard import main

main()
