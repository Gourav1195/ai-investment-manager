#!/usr/bin/env python3
"""Sign in with APP_PASSWORD, reload, confirm dashboard still loads."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.environ.get("QA_STREAMLIT_PORT", "8525"))


def _start(work_dir: Path) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["INVESTING_WORK_DIR"] = str(work_dir)
    env["APP_PASSWORD"] = "qa-test-password"
    env["APP_AUTH_SIGNING_KEY"] = "qa-signing-key"
    env["INVESTING_UI_RESEARCH_OFFLINE"] = "1"
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(ROOT / "streamlit_app.py"),
            "--server.headless",
            "true",
            "--server.port",
            str(PORT),
        ],
        cwd="/tmp",
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def main() -> int:
    from playwright.sync_api import sync_playwright

    work_dir = Path(tempfile.mkdtemp(prefix="auth-remember-qa-"))
    process = _start(work_dir)
    base = f"http://127.0.0.1:{PORT}"
    try:
        for _ in range(45):
            try:
                import urllib.request

                urllib.request.urlopen(f"{base}/_stcore/health", timeout=2)
                break
            except Exception:
                if process.poll() is not None:
                    raise RuntimeError((process.stderr.read() if process.stderr else b"").decode())
                time.sleep(1)
        else:
            raise RuntimeError("Streamlit not healthy")

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(base, wait_until="domcontentloaded", timeout=120_000)
            page.get_by_role("textbox", name="Password").fill("qa-test-password")
            page.get_by_role("button", name="Continue").click()
            page.wait_for_selector("text=Dashboard", timeout=60_000)
            page.wait_for_selector("text=Menu", timeout=30_000)
            assert page.get_by_text("Sign in").count() == 0

            page.reload(wait_until="domcontentloaded", timeout=120_000)
            page.wait_for_selector("text=Dashboard", timeout=60_000)
            assert page.get_by_text("Sign in").count() == 0
            assert page.locator('[data-testid="stException"]').count() == 0

            out = Path(os.environ.get("QA_SCREENSHOT_DIR", "/tmp/qa-screenshots"))
            out.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out / "auth-remember-after-reload.png"), full_page=True)
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=10)
    print("Auth remember-me reload check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
