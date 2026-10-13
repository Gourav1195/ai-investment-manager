from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest


def test_cookie_script_uses_supported_api(monkeypatch):
    from src.investing import auth_cookies
    html = Mock()
    monkeypatch.setattr(auth_cookies.st, 'html', html)
    auth_cookies.write_remember_cookie('signed-token')
    html.assert_called_once()
    assert html.call_args.kwargs == {'unsafe_allow_javascript': True}
    assert 'max-age=' in html.call_args.args[0]


def test_login_stages_cookie_without_token_in_url(monkeypatch):
    from src.investing import cloud_auth
    state, query = {}, {}
    monkeypatch.setattr(cloud_auth.st, 'session_state', state)
    monkeypatch.setattr(cloud_auth.st, 'query_params', query)
    monkeypatch.setattr(cloud_auth, 'mint_remember_token', lambda _: 'signed-token')
    cloud_auth._persist_remember_token('secret')
    assert state['_remember_token'] == 'signed-token'
    assert query == {}


def test_authenticated_run_emits_cookie(monkeypatch):
    from src.investing import cloud_auth
    monkeypatch.setattr(cloud_auth.st, 'session_state', {'app_password_ok': True, '_remember_token': 'token'})
    monkeypatch.setattr(cloud_auth, 'is_cloud_persistence_configured', lambda: False)
    monkeypatch.setattr(cloud_auth, '_configured_password', lambda: 'secret')
    writer = Mock()
    monkeypatch.setattr(cloud_auth, 'write_remember_cookie', writer)
    cloud_auth.require_app_password()
    writer.assert_called_once_with('token')


def test_upload_only_processed_once_and_removal_allows_retry(monkeypatch, tmp_path):
    from src.investing import upload_state
    monkeypatch.setattr(upload_state.st, 'session_state', {})
    upload = BytesIO(b'one')
    path = tmp_path / 'portfolio.db'
    assert upload_state.needs_processing(upload, 'holdings', path)
    upload_state.mark_processed(upload, 'holdings', path)
    assert not upload_state.needs_processing(upload, 'holdings', path)
    assert upload_state.needs_processing(BytesIO(b'two'), 'holdings', path)
    assert not upload_state.needs_processing(None, 'holdings', path)
    assert upload_state.needs_processing(upload, 'holdings', path)


def test_upload_renderer_does_not_reimport_on_rerun(monkeypatch, tmp_path):
    from src.investing import portfolio_cloud_ui as ui
    monkeypatch.setattr(ui.st, 'session_state', {})
    upload = BytesIO(b'symbol,quantity\nTCS,2\n')
    upload.name = 'holdings.csv'
    monkeypatch.setattr(ui.st, 'file_uploader', lambda *a, **kw: upload)
    monkeypatch.setattr(ui.st, 'success', Mock())
    monkeypatch.setattr(ui.st, 'rerun', Mock())
    importer = Mock(return_value=1)
    monkeypatch.setattr(ui, 'import_equity_holdings_file', importer)
    path = tmp_path / 'portfolio.db'
    for _ in range(2):
        ui._import_upload(path, label='Holdings', kind='equity-holdings', key='upload')
    importer.assert_called_once()
    assert not importer.call_args.args[1].exists()


def test_restore_renderer_does_not_loop_or_overwrite_later_changes(monkeypatch, tmp_path):
    from src.investing import ui_research as ui
    monkeypatch.setattr(ui.st, 'session_state', {})
    from src.investing.research import ResearchStore
    source = tmp_path / 'source.db'
    ResearchStore(source)
    upload = BytesIO(source.read_bytes())
    monkeypatch.setattr(ui.st, 'file_uploader', lambda *a, **kw: upload if kw['key'] == 'ul_research_db' else None)
    monkeypatch.setattr(ui.st, 'rerun', Mock())
    monkeypatch.setattr(ui.st, 'download_button', Mock())
    research, portfolio = tmp_path / 'research.db', tmp_path / 'portfolio.db'
    ui.render_database_backup_panel(research, portfolio)
    research.write_bytes(b'new local data')
    ui.render_database_backup_panel(research, portfolio)
    assert research.read_bytes() == b'new local data'
    ui.st.rerun.assert_called_once()


def test_cloud_pull_failure_retries_without_pushing(monkeypatch, tmp_path):
    from src.investing import cloud_persistence as cloud
    state = {}
    monkeypatch.setattr(__import__('streamlit'), 'session_state', state)
    monkeypatch.setattr(cloud, 'resolve_database_url', lambda: 'test-url')
    pull = Mock(side_effect=[cloud.PersistenceState(cloud.PersistenceMode.CLOUD_DEGRADED), cloud.PersistenceState(cloud.PersistenceMode.CLOUD)])
    push = Mock(return_value=cloud.PersistenceState(cloud.PersistenceMode.CLOUD))
    monkeypatch.setattr(cloud, 'pull_cloud_blobs', pull)
    monkeypatch.setattr(cloud, 'push_cloud_blobs', push)
    (tmp_path / 'ui_prefs.json').write_text('{}')
    assert cloud.sync_session_cloud_data(tmp_path).mode == cloud.PersistenceMode.CLOUD_DEGRADED
    assert not state.get('_cloud_pulled')
    push.assert_not_called()
    assert cloud.sync_session_cloud_data(tmp_path).mode == cloud.PersistenceMode.CLOUD
    assert pull.call_count == 2
    push.assert_called_once()


def test_cloud_push_failure_retries(monkeypatch, tmp_path):
    from src.investing import cloud_persistence as cloud
    state = {'_cloud_pulled': True, '_cloud_persistence_state': cloud.PersistenceState(cloud.PersistenceMode.CLOUD_DEGRADED)}
    monkeypatch.setattr(__import__('streamlit'), 'session_state', state)
    monkeypatch.setattr(cloud, 'resolve_database_url', lambda: 'test-url')
    push = Mock(return_value=cloud.PersistenceState(cloud.PersistenceMode.CLOUD))
    monkeypatch.setattr(cloud, 'push_cloud_blobs', push)
    (tmp_path / 'ui_prefs.json').write_text('{}')
    assert cloud.sync_session_cloud_data(tmp_path).mode == cloud.PersistenceMode.CLOUD
    push.assert_called_once()


def test_sidebar_changes_page_and_keeps_selection_on_rerun():
    app = AppTest.from_string('''
import streamlit as st
from src.investing.sidebar_nav import render_sidebar_section_menu
with st.sidebar:
    section = render_sidebar_section_menu()
st.write(section)
''').run()
    assert not app.exception
    assert app.session_state['active_section'] == 'Dashboard'
    app.button(key='nav_About').click().run()
    assert app.session_state['active_section'] == 'About'
    app.run()
    assert app.session_state['active_section'] == 'About'
    assert any(item.value == 'About' for item in app.markdown)
    assert not app.exception


def test_welcome_escapes_user_markup(monkeypatch):
    from src.investing import royal_theme
    render = Mock()
    monkeypatch.setattr(royal_theme.st, 'markdown', render)
    royal_theme.render_welcome_header('<img src=x onerror=alert(1)>')
    assert '<img' not in render.call_args.args[0]
    assert '&lt;img' in render.call_args.args[0]


def test_invalid_or_wrong_backup_keeps_original(tmp_path):
    from src.investing.ui_research import restore_sqlite_bytes
    from src.investing.portfolio_store import PortfolioStore
    dest = tmp_path / 'research.db'
    dest.write_bytes(b'original data')
    with pytest.raises(ValueError):
        restore_sqlite_bytes(b'not a database', dest, kind='Research')
    source = tmp_path / 'portfolio.db'
    PortfolioStore(source)
    with pytest.raises(ValueError):
        restore_sqlite_bytes(source.read_bytes(), dest, kind='Research')
    assert dest.read_bytes() == b'original data'


def test_saved_summary_skips_live_history(monkeypatch, tmp_path):
    from src.investing import portfolio_dashboard_data as data
    from src.investing.portfolio_service import load_example_portfolio
    from src.investing.portfolio_store import PortfolioStore
    path = tmp_path / 'portfolio.db'
    load_example_portfolio(PortfolioStore(path))
    history = Mock(side_effect=AssertionError('Unexpected live history'))
    monkeypatch.setattr(data, 'estimate_portfolio_history', history)
    summary, comparison = data.load_portfolio_summary(path, refresh_prices=False)
    assert not summary.equity.empty
    assert comparison is None
    history.assert_not_called()


def test_offline_fund_client_never_contacts_network(tmp_path):
    from src.investing.mf_nav_client import MfNavClient
    from src.investing.portfolio_store import PortfolioStore
    session = Mock()
    client = MfNavClient(PortfolioStore(tmp_path / 'portfolio.db'), session=session, allow_network=False)
    with pytest.raises(RuntimeError):
        client.sync_scheme_master_from_amfi()
    with pytest.raises(RuntimeError):
        client.sync_scheme_nav('123')
    session.get.assert_not_called()


def test_portfolio_peer_comparison_respects_sync_master(monkeypatch, tmp_path):
    from src.investing import mf_peer_comparison as peers
    from src.investing.portfolio_service import load_example_portfolio
    from src.investing.portfolio_store import PortfolioStore
    store = PortfolioStore(tmp_path / 'portfolio.db')
    load_example_portfolio(store)
    compare = Mock(return_value=None)
    client = Mock()
    monkeypatch.setattr(peers, 'compare_held_fund_to_peers', compare)
    peers.compare_portfolio_mutual_funds(store, client=client, sync_master=False)
    assert compare.call_count > 0
    assert all(call.kwargs['sync_master'] is False for call in compare.call_args_list)
    client.sync_scheme_master_from_amfi.assert_not_called()


def test_demo_overview_has_values_without_network(monkeypatch, tmp_path):
    from src.investing.onboarding_ui import _load_demo_portfolio, portfolio_contains_demo_data
    from src.investing.app_preferences import AppPreferences
    from src.investing.wealth_insights import load_wealth_snapshot
    from src.investing.providers import YFinancePriceProvider
    import requests
    network = Mock(side_effect=AssertionError('Unexpected network call'))
    monkeypatch.setattr(requests.Session, 'get', network)
    monkeypatch.setattr(YFinancePriceProvider, 'fetch', network)
    path = tmp_path / 'portfolio.db'
    _load_demo_portfolio(path, AppPreferences(tmp_path / 'prefs.json'))
    assert portfolio_contains_demo_data(path)
    wealth, _, reports = load_wealth_snapshot(path, None, refresh_prices=False)
    assert wealth.has_portfolio
    assert wealth.total_value is not None and wealth.total_value > 0
    assert reports == []
    network.assert_not_called()
