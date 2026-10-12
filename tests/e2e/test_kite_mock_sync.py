from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from src.investing.portfolio_service import sync_kite_holdings
from src.investing.portfolio_store import PortfolioStore


class _KiteHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/portfolio/holdings":
            payload = {
                "status": "success",
                "data": [
                    {
                        "tradingsymbol": "INFY-EQ",
                        "quantity": 5,
                        "average_price": 1500.0,
                        "exchange": "NSE",
                    }
                ],
            }
        elif self.path == "/mf/holdings":
            payload = {
                "status": "success",
                "data": [
                    {
                        "fund": "122639",
                        "quantity": 12.5,
                        "average_price": 70.0,
                        "folio": "x",
                    }
                ],
            }
        else:
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def test_sync_kite_holdings_against_mock_server(tmp_path, monkeypatch) -> None:
    server = HTTPServer(("127.0.0.1", 0), _KiteHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("KITE_API_KEY", "key")
    monkeypatch.setenv("KITE_ACCESS_TOKEN", "token")
    import src.investing.kite_client as kite_client

    monkeypatch.setattr(kite_client, "KITE_API_BASE", f"http://127.0.0.1:{port}")
    store = PortfolioStore(tmp_path / "portfolio.db")
    equity_rows, mf_rows = sync_kite_holdings(store)
    server.shutdown()
    assert equity_rows == 1
    assert mf_rows == 1
    assert store.list_equity_holdings().iloc[0]["symbol"] == "INFY"
