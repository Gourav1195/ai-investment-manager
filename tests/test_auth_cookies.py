from __future__ import annotations

from src.investing.auth_remember import COOKIE_NAME


def test_read_remember_cookie_handles_missing_context(monkeypatch) -> None:
    from src.investing import auth_cookies

    class BrokenCookies:
        def get(self, _key: str) -> str | None:
            raise RuntimeError("no context")

    class Ctx:
        cookies = BrokenCookies()

    monkeypatch.setattr(auth_cookies.st, "context", Ctx(), raising=False)
    assert auth_cookies.read_remember_cookie() is None


def test_read_remember_cookie_returns_value(monkeypatch) -> None:
    from src.investing import auth_cookies

    class Cookies(dict):
        pass

    class Ctx:
        cookies = Cookies({COOKIE_NAME: "token-value"})

    monkeypatch.setattr(auth_cookies.st, "context", Ctx(), raising=False)
    assert auth_cookies.read_remember_cookie() == "token-value"
