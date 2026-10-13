from __future__ import annotations

from unittest.mock import Mock

import pytest


def test_streamlit_cloud_without_password_blocks_app(monkeypatch):
    from src.investing import cloud_auth

    monkeypatch.setattr(cloud_auth, "is_cloud_persistence_configured", lambda: False)
    monkeypatch.setattr(cloud_auth, "is_streamlit_community_cloud", lambda: True)
    monkeypatch.setattr(cloud_auth, "_configured_password", lambda: None)
    monkeypatch.setattr(cloud_auth.st, "session_state", {})
    monkeypatch.setattr(cloud_auth.st, "error", Mock())
    stop = Mock(side_effect=AssertionError("stop"))
    monkeypatch.setattr(cloud_auth.st, "stop", stop)
    with pytest.raises(AssertionError, match="stop"):
        cloud_auth.require_app_password()
    cloud_auth.st.error.assert_called_once()
