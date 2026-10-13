from pathlib import Path
from unittest.mock import Mock
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest


def test_default_demo_is_separate_and_does_not_create_personal_holdings(monkeypatch, tmp_path):
    from src.investing.portfolio_start import selected_portfolio_path
    from src.investing.portfolio_store import PortfolioStore
    monkeypatch.setattr(st, 'session_state', {})
    real = tmp_path / 'portfolio.db'
    demo = selected_portfolio_path(real, tmp_path)
    assert demo != real
    assert not real.exists()
    assert not PortfolioStore(demo).list_equity_holdings().empty
    assert st.session_state['portfolio_source'] == 'Demo portfolio'


def test_existing_personal_portfolio_is_selected_without_overwriting(monkeypatch, tmp_path):
    from src.investing.portfolio_start import selected_portfolio_path
    from src.investing.portfolio_store import PortfolioStore
    from src.investing.portfolio_service import import_equity_holdings_file, EXAMPLES_DIR
    monkeypatch.setattr(st, 'session_state', {})
    real = tmp_path / 'portfolio.db'
    import_equity_holdings_file(PortfolioStore(real), EXAMPLES_DIR/'equity_holdings.example.csv')
    before = real.read_bytes()
    assert selected_portfolio_path(real, tmp_path) == real
    assert real.read_bytes() == before


def test_start_upload_and_connect_select_real_data(tmp_path):
    app = AppTest.from_string(f'''
from pathlib import Path
from src.investing.portfolio_start import render_start_choices, selected_portfolio_path
import streamlit as st
path = Path({str(tmp_path / 'portfolio.db')!r})
render_start_choices(path)
st.write(str(selected_portfolio_path(path, path.parent)))
''').run()
    assert not app.exception
    assert app.session_state['portfolio_source'] == 'Demo portfolio'
    app.button(key='home_upload').click().run()
    assert not app.exception
    assert app.session_state['portfolio_source'] == 'My portfolio'
    assert app.session_state['home_setup'] == 'upload'
    app.button(key='home_connect').click().run()
    assert app.session_state['home_setup'] == 'connect'


def test_browser_token_restores_when_server_cookie_missing(monkeypatch):
    from src.investing import cloud_auth
    from src.investing.auth_remember import mint_remember_token
    monkeypatch.setenv('APP_AUTH_SIGNING_KEY', 'test-only-key')
    token = mint_remember_token('test-password')
    state = {}
    monkeypatch.setattr(st, 'session_state', state)
    monkeypatch.setattr(st, 'query_params', {})
    monkeypatch.setattr(cloud_auth, '_configured_password', lambda: 'test-password')
    monkeypatch.setattr(cloud_auth, 'is_cloud_persistence_configured', lambda: False)
    monkeypatch.setattr(cloud_auth, 'read_remember_cookie', lambda: None)
    monkeypatch.setattr(cloud_auth, 'render_browser_auth', lambda **kw: {'token': token, 'available': True})
    class Rerun(BaseException): pass
    monkeypatch.setattr(st, 'rerun', Mock(side_effect=Rerun))
    with pytest.raises(Rerun):
        cloud_auth.require_app_password()
    assert state['app_password_ok'] is True
    assert state['_remember_token'] == token


def test_invalid_browser_token_cannot_authenticate(monkeypatch):
    from contextlib import nullcontext
    from src.investing import cloud_auth
    state = {'_wealth_browser_auth': {'storage': {'token': 'tampered'}}}
    monkeypatch.setattr(st, 'session_state', state)
    monkeypatch.setattr(st, 'query_params', {})
    monkeypatch.setattr(cloud_auth, '_configured_password', lambda: 'test-password')
    monkeypatch.setattr(cloud_auth, 'is_cloud_persistence_configured', lambda: False)
    monkeypatch.setattr(cloud_auth, 'read_remember_cookie', lambda: None)
    bridge = Mock(return_value={'token': 'tampered'})
    monkeypatch.setattr(cloud_auth, 'render_browser_auth', bridge)
    class Stop(BaseException): pass
    monkeypatch.setattr(st, 'stop', Mock(side_effect=Stop))
    monkeypatch.setattr(st, 'form', lambda *a, **kw: nullcontext())
    monkeypatch.setattr(st, 'text_input', Mock(return_value=''))
    monkeypatch.setattr(st, 'checkbox', Mock(return_value=True))
    monkeypatch.setattr(st, 'form_submit_button', lambda *a, **kw: False)
    with pytest.raises(Stop):
        cloud_auth.require_app_password()
    bridge.assert_called_once_with(clear=True)
    assert not state.get('app_password_ok')


def test_kite_empty_holdings_and_zero_current_quantity():
    from src.investing.kite_client import KiteReadOnlyClient
    from src.investing.kite_config import KiteCredentials
    session = Mock()
    response = Mock()
    response.json.return_value = {'status': 'success', 'data': []}
    session.get.return_value = response
    client = KiteReadOnlyClient(KiteCredentials('test-key','test-token'), session=session)
    assert client.equity_holdings_frame().empty
    assert client.mf_holdings_frame().empty
    response.json.return_value = {'status': 'success', 'data': [{'quantity': 0, 'opening_quantity': 10, 'tradingsymbol': 'INFY'}]}
    assert client.equity_holdings_frame().empty


def test_connect_accepts_session_credentials_without_config_file(monkeypatch, tmp_path):
    from src.investing import portfolio_service as service
    from src.investing.kite_config import KiteCredentials
    from src.investing.portfolio_store import PortfolioStore
    import pandas as pd
    credentials = KiteCredentials('test-key', 'test-token')
    client = Mock()
    client.equity_holdings_frame.return_value = pd.DataFrame(columns=['symbol','quantity','average_price'])
    client.mf_holdings_frame.return_value = pd.DataFrame(columns=['scheme_code','scheme_name','units'])
    factory = Mock(return_value=client)
    monkeypatch.setattr(service, 'KiteReadOnlyClient', factory)
    loader = Mock(side_effect=AssertionError('Should not read or persist credentials'))
    monkeypatch.setattr(service, 'load_kite_credentials', loader)
    assert service.sync_kite_holdings(PortfolioStore(tmp_path/'portfolio.db'), credentials=credentials) == (0,0)
    factory.assert_called_once_with(credentials)
    assert not (tmp_path/'kite.local.json').exists()


def test_user_upload_clears_legacy_sample_holdings_and_trades(tmp_path):
    from src.investing.portfolio_store import PortfolioStore
    from src.investing.portfolio_service import load_example_portfolio, import_equity_holdings_file, EXAMPLES_DIR
    store = PortfolioStore(tmp_path/'portfolio.db')
    load_example_portfolio(store)
    import_equity_holdings_file(store, EXAMPLES_DIR/'equity_holdings.example.csv')
    assert store.list_equity_holdings()['source'].eq('zerodha_csv').all()
    assert store.list_mf_holdings().empty
    assert store.list_equity_trades().empty


def test_kite_real_mf_payload_uses_isin_and_broker_prices():
    from src.investing.kite_client import KiteReadOnlyClient
    from src.investing.kite_config import KiteCredentials
    session = Mock()
    response = Mock()
    response.json.return_value = {'status': 'success', 'data': [{'fund': 'Example Direct Growth Fund', 'tradingsymbol': 'INF000000001', 'quantity': 12, 'average_price': 80, 'last_price': 90}]}
    session.get.return_value = response
    row = KiteReadOnlyClient(KiteCredentials('key','token'),session=session).mf_holdings_frame().iloc[0]
    assert row['scheme_code'] == 'INF000000001'
    assert row['scheme_name'] == 'Example Direct Growth Fund'
    assert row['last_price'] == 90


def test_official_amfi_column_order():
    from src.investing.mf_amfi_master import parse_amfi_nav_all
    frame = parse_amfi_nav_all('Open Ended Schemes ( Equity Scheme - Flexi Cap Fund )\n123456;INF000000001;-;Example Fund - Direct Plan - Growth;90;13-Oct-2026')
    assert frame.iloc[0]['scheme_name'] == 'Example Fund - Direct Plan - Growth'
    assert frame.iloc[0]['plan_type'] == 'Direct'


def test_broker_isin_is_not_sent_as_public_amfi_code(tmp_path):
    from src.investing.mf_nav_client import MfNavClient
    from src.investing.portfolio_store import PortfolioStore
    session = Mock()
    with pytest.raises(ValueError):
        MfNavClient(PortfolioStore(tmp_path/'portfolio.db'),session=session).sync_scheme_nav('INF000000001')
    session.get.assert_not_called()


def test_view_demo_preserves_personal_holdings(monkeypatch, tmp_path):
    from src.investing.portfolio_start import use_demo_portfolio, selected_portfolio_path
    from src.investing.portfolio_store import PortfolioStore
    from src.investing.portfolio_service import import_equity_holdings_file, EXAMPLES_DIR
    real = tmp_path/'portfolio.db'
    import_equity_holdings_file(PortfolioStore(real), EXAMPLES_DIR/'equity_holdings.example.csv')
    before = real.read_bytes()
    monkeypatch.setattr(st, 'session_state', {'portfolio_source': 'My portfolio'})
    use_demo_portfolio()
    assert selected_portfolio_path(real, tmp_path) != real
    assert real.read_bytes() == before
