from __future__ import annotations

from src.investing.app_preferences import AppPreferences


def test_display_name_round_trip(tmp_path) -> None:
    prefs = AppPreferences(tmp_path / "ui_prefs.json")
    assert prefs.get_display_name() == ""
    prefs.set_display_name("Gourav")
    again = AppPreferences(tmp_path / "ui_prefs.json")
    assert again.get_display_name() == "Gourav"


def test_onboarding_flag(tmp_path) -> None:
    prefs = AppPreferences(tmp_path / "ui_prefs.json")
    assert not prefs.get_onboarding_complete()
    prefs.set_onboarding_complete(True)
    assert AppPreferences(tmp_path / "ui_prefs.json").get_onboarding_complete()
