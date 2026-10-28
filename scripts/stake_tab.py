#!/usr/bin/env python3
"""Make sure the debug Chrome (port 9222) has a stake.com tab on a page the scrapers can read, and wait until it is loaded.

    python scripts/stake_tab.py nba|nfl

The scrapers call Stake's GraphQL from whatever stake.com tab they find; a tab parked on a finished/started game page or a
challenge page makes Stake answer with HTML ("Unexpected token '<'"), so each job first moves the tab to the league page.
Stake also answers 403 "ip-blocked" (HTML) to some VPN exit IPs: the script probes the GraphQL API from the tab and, if it is blocked,
reconnects Windscribe (a new IP of the same location) up to MAX_ROTATIONS times before giving up.
Exit code 0 = tab ready and API answering, 1 = Chrome not reachable, page not loaded or API still blocked.
"""

import json
import subprocess
import sys
import time

import requests
import websocket

WINDSCRIBE = r"C:\Program Files\Windscribe\windscribe-cli.exe"
LOCATION = "Besa"
MAX_ROTATIONS = 4
PROBE_JS = (
    "(async()=>{const r=await fetch('/_api/v1/graphql',{method:'POST',headers:{'Content-Type':'application/json'},"
    "body:JSON.stringify({variables:{},query:'query{__typename}'})});"
    "return r.status+'|'+(r.headers.get('content-type')||'')})()"
)
URLS = {"nba": "https://stake.com/es/sports/basketball/usa/nba", "nfl": "https://stake.com/es/sports/american-football/usa/nfl"}


def load_tab(sport: str) -> int:
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
            v = call("Runtime.evaluate", {"expression": PROBE_JS, "awaitPromise": True, "returnByValue": True})
            probe = v.get("result", {}).get("result", {}).get("value", "")
            ws.close()
            if probe.startswith("200|") and "json" in probe:
                return 0
            print(f"Stake API blocked from this IP: {probe}")
            return 2
    print(f"Stake tab did not finish loading: {state}")
    return 1


def rotate_vpn() -> None:
    """Reconnect Windscribe so the exit IP changes (Stake blocks some of them)."""
    subprocess.run([WINDSCRIBE, "disconnect"], capture_output=True, timeout=60)
    time.sleep(3)
    out = subprocess.run([WINDSCRIBE, "connect", LOCATION], capture_output=True, text=True, timeout=90)
    print(f"VPN reconnect: {out.stdout.strip().splitlines()[-1] if out.stdout.strip() else out.stderr.strip()}")
    time.sleep(8)


def main(sport: str) -> int:
    code = load_tab(sport)
    for attempt in range(1, MAX_ROTATIONS + 1):
        if code != 2:
            return code
        print(f"Rotating VPN IP (attempt {attempt}/{MAX_ROTATIONS})")
        rotate_vpn()
        code = load_tab(sport)
    return 0 if code == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "nba"))
