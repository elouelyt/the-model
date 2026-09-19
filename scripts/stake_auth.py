#!/usr/bin/env python3
"""One-time Stake.com authentication for Playwright.

Opens a real browser window — log in manually, then press Enter here.
Saves session to data/stake_auth.json for use by stake_scraper.py.

Run once: python scripts/stake_auth.py
"""

from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
AUTH_FILE = ROOT / "data" / "stake_auth.json"


def main() -> None:
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto("https://stake.com/es/sports/tennis")
        print("\n=== Abre stake.com en el navegador que se ha lanzado ===")
        print("=== Haz login manualmente y cuando estés dentro, vuelve aquí y presiona Enter ===")
        input()
        ctx.storage_state(path=str(AUTH_FILE))
        browser.close()
    print(f"Sesión guardada en {AUTH_FILE}")


if __name__ == "__main__":
    main()
