#!/usr/bin/env python3
"""Make sure the debug Chrome (port 9222) has a stake.com tab on a page the scrapers can read, and wait until it is loaded.

    python scripts/stake_tab.py nba|nfl

The scrapers call Stake's GraphQL from whatever stake.com tab they find; a tab parked on a finished/started game page or a
challenge page makes Stake answer with HTML ("Unexpected token '<'"), so each job first moves the tab to the league page.
Exit code 0 = tab ready, 1 = Chrome not reachable or the page did not load.
"""

import json
import sys
import time

import requests
import websocket

URLS = {"nba": "https://stake.com/es/sports/basketball/usa/nba", "nfl": "https://stake.com/es/sports/american-football/usa/nfl"}


def main(sport: str) -> int:
    try:
        tabs = requests.get("http://localhost:9222/json", timeout=5).json()
    except Exception as exc:  # noqa: BLE001
        print(f"Chrome 9222 not reachable: {exc}")
        return 1
    pages = [t for t in tabs if t.get("type") == "page"]
    tab = next((t for t in pages if "stake.com" in t.get("url", "")), pages[0] if pages else None)
    if tab is None:
        tab = requests.put("http://localhost:9222/json/new?about:blank", timeout=10).json()
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=60)
    n = 0

    def call(method: str, params: dict | None = None) -> dict:
        nonlocal n
        n += 1
        ws.send(json.dumps({"id": n, "method": method, "params": params or {}}))
        while True:
            r = json.loads(ws.recv())
            if r.get("id") == n:
                return r

    call("Page.navigate", {"url": URLS[sport]})
    for _ in range(30):
        time.sleep(2)
        v = call("Runtime.evaluate", {"expression": "document.readyState + '|' + document.title", "returnByValue": True})
        state = v.get("result", {}).get("result", {}).get("value", "")
        if state.startswith("complete") and "Stake" in state and "moment" not in state.lower():
            print(f"Stake tab ready on {URLS[sport]}: {state}")
            return 0
    print(f"Stake tab did not finish loading: {state}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "nba"))
