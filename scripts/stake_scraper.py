#!/usr/bin/env python3
"""Stake.com tennis odds scraper via Chrome DevTools Protocol (CDP).

Connects to the already-running Chrome (no new browser launched, no cookies needed)
and executes fetch requests inside the browser context.

ONE-TIME SETUP:
  1. Right-click Chrome shortcut → Properties
  2. In "Target" add: --remote-debugging-port=9222
     Example: "C:\\...\\chrome.exe" --remote-debugging-port=9222
  3. Restart Chrome

Daily run: python scripts/stake_scraper.py
Requires: pip install websocket-client requests
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import websocket

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "stake_cache.json"

CDP_HOST = "http://localhost:9222"
STAKE_DOMAIN = "stake.com"


SCRAPE_JS = r"""
(async function() {
  const QUERY_CAT = `query Cat($sport: String!, $cat: String!) {
    slugCategory(sport: $sport, category: $cat) {
      name slug tournamentList(limit: 100) { name slug }
    }
  }`;

  const QUERY_T = `query T($sport: String!, $cat: String!, $slug: String!, $type: SportSearchEnum!) {
    slugTournament(sport: $sport, category: $cat, tournament: $slug) {
      name fixtureCount(type: $type)
      fixtureList(type: $type, limit: 50, offset: 0) {
        id name status
        data { __typename ... on SportFixtureDataMatch { startTime isOutright competitors { name defaultName countryCode } } }
        groups(groups: ["winner"], status: [active, suspended, deactivated]) {
          templates(limit: 1, includeEmpty: false) {
            markets(limit: 1) { status outcomes { active odds name } }
          }
        }
      }
    }
  }`;

  async function gql(variables, query) {
    const r = await fetch("/_api/graphql", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({variables, query})
    });
    return (await r.json())?.data;
  }

  function parseFixture(f, tName) {
    const data = f.data || {};
    if (data.isOutright) return null;
    const comps = data.competitors || [];
    if (comps.length < 2) return null;
    const home = comps[0].name || comps[0].defaultName || "";
    const away = comps[1].name || comps[1].defaultName || "";
    if (!home || !away) return null;
    let hOdds = null, aOdds = null;
    for (const g of (f.groups || [])) for (const t of (g.templates || [])) for (const m of (t.markets || [])) {
      for (const o of (m.outcomes || [])) if (o.active) {
        const n = (o.name || "").toLowerCase();
        const hl = home.toLowerCase(), al = away.toLowerCase();
        if (n.includes(hl.split(" ")[0]) || n.includes(hl.split(",")[0])) hOdds = parseFloat(o.odds);
        else if (n.includes(al.split(" ")[0]) || n.includes(al.split(",")[0])) aOdds = parseFloat(o.odds);
      }
    }
    return {
      tournament: tName, fixture_id: f.id, status: f.status,
      start_time: data.startTime || "", home, away,
      home_odds: hOdds, away_odds: aOdds,
      home_country: comps[0].countryCode, away_country: comps[1].countryCode
    };
  }

  const cats = ["wta", "atp", "davis-cup", "challenger"];
  const allSlugs = [];
  for (const cat of cats) {
    const d = await gql({sport: "tennis", cat}, QUERY_CAT);
    for (const t of (d?.slugCategory?.tournamentList || [])) allSlugs.push({cat, slug: t.slug, name: t.name});
    await new Promise(r => setTimeout(r, 100));
  }

  const allMatches = [];
  const seenIds = new Set();
  for (const {cat, slug, name} of allSlugs) {
    const d = await gql({sport: "tennis", cat, slug, type: "popular"}, QUERY_T);
    const st = d?.slugTournament;
    for (const f of (st?.fixtureList || [])) {
      if (seenIds.has(f.id)) continue;
      seenIds.add(f.id);
      const m = parseFixture(f, st?.name || name);
      if (m) allMatches.push(m);
    }
    await new Promise(r => setTimeout(r, 150));
  }

  return JSON.stringify({
    timestamp: new Date().toISOString(),
    source: "Stake.com GraphQL (CDP)",
    match_count: allMatches.length,
    matches: allMatches
  });
})()
"""


class CDPClient:
    def __init__(self, ws_url: str):
        self._ws = websocket.create_connection(ws_url, timeout=10)
        self._msg_id = 0
        logger.info("CDP WebSocket connected")

    def send(self, method: str, params: dict, timeout: float = 120.0) -> dict:
        self._msg_id += 1
        msg_id = self._msg_id
        payload = json.dumps({"id": msg_id, "method": method, "params": params})
        self._ws.send(payload)
        self._ws.settimeout(timeout)
        # Read messages until we get the one matching our id
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                raw = self._ws.recv()
                msg = json.loads(raw)
                if msg.get("id") == msg_id:
                    return msg
                # Ignore CDP events (no id or different id)
            except websocket.WebSocketTimeoutException:
                raise TimeoutError(f"CDP {method} timed out after {timeout}s")
        raise TimeoutError(f"CDP {method} timed out after {timeout}s")

    def close(self):
        self._ws.close()


def _find_stake_tab() -> tuple[str, str] | None:
    """Find the Stake.com tab via CDP /json endpoint."""
    try:
        tabs = requests.get(f"{CDP_HOST}/json", timeout=5).json()
    except Exception as e:
        logger.error("Cannot connect to Chrome DevTools at %s: %s", CDP_HOST, e)
        logger.error("Make sure Chrome is running with --remote-debugging-port=9222")
        return None

    for tab in tabs:
        url = tab.get("url", "")
        ws_url = tab.get("webSocketDebuggerUrl", "")
        if STAKE_DOMAIN in url and ws_url:
            logger.info("Found Stake tab: %s", url)
            return tab["id"], ws_url

    # No Stake tab open — open one
    logger.info("No Stake tab found. Opening stake.com/es/sports/tennis ...")
    try:
        new_tab = requests.get(
            f"{CDP_HOST}/json/new?https://stake.com/es/sports/tennis", timeout=10
        ).json()
        ws_url = new_tab.get("webSocketDebuggerUrl", "")
        if ws_url:
            time.sleep(5)  # Let the page load
            return new_tab["id"], ws_url
    except Exception as e:
        logger.error("Could not open new tab: %s", e)
    return None


def main() -> None:
    logger.info("Stake.com scraper via Chrome DevTools Protocol")

    result = _find_stake_tab()
    if not result:
        raise SystemExit(1)

    tab_id, ws_url = result
    logger.info("Connecting to CDP WebSocket: %s", ws_url[:60])

    client = CDPClient(ws_url)
    try:
        logger.info("Executing scraper JS (may take 30-60s)...")
        response = client.send(
            "Runtime.evaluate",
            {
                "expression": SCRAPE_JS,
                "awaitPromise": True,
                "returnByValue": True,
                "timeout": 120000,
            },
            timeout=150.0,
        )

        result_val = response.get("result", {}).get("result", {})
        if result_val.get("type") == "string":
            payload = json.loads(result_val["value"])
        else:
            exc = response.get("result", {}).get("exceptionDetails", {})
            logger.error("JS execution error: %s", exc)
            raise SystemExit(1)

    finally:
        client.close()

    logger.info("Scrape complete: %d matches", payload.get("match_count", 0))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved to %s", OUT)

    matches = payload.get("matches", [])
    live = [m for m in matches if m["status"] in ("active", "live")]
    with_odds = [m for m in matches if m["home_odds"] and m["away_odds"]]

    print(f"\n{len(matches)} matches ({len(live)} live, {len(with_odds)} with odds)")
    print("\nSample:")
    for m in matches[:8]:
        h = m["home_odds"] or "?"
        a = m["away_odds"] or "?"
        print(f"  [{m['tournament'][:15]}] {m['home'][:22]} vs {m['away'][:22]}  {h}/{a}")


if __name__ == "__main__":
    main()
