"""Identify completed browser uploads across Streamlit reruns."""
from __future__ import annotations

import hashlib
from pathlib import Path
import streamlit as st

def upload_marker(key: str, path: Path) -> str:
    return f"_processed_upload:{key}:{path.resolve()}"

def upload_digest(uploaded) -> str:
    return hashlib.sha256(uploaded.getvalue()).hexdigest()

def needs_processing(uploaded, key: str, path: Path) -> bool:
    marker = upload_marker(key, path)
    if uploaded is None:
        st.session_state.pop(marker, None)
        return False
    return st.session_state.get(marker) != upload_digest(uploaded)

def mark_processed(uploaded, key: str, path: Path) -> None:
    st.session_state[upload_marker(key, path)] = upload_digest(uploaded)
