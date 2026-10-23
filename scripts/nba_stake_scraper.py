#!/usr/bin/env python3
"""Scrape NBA player props from Stake (Swish markets) through the running Chrome (CDP).

Run with Chrome open on stake.com (see stake_scraper.py for setup).
Output: data/nba_stake_cache.json  (one row per player / stat / line).
"""

import json
import logging
from datetime import datetime, timezone

from stake_scraper import ROOT, CDPClient, _find_stake_tab

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUT = ROOT / "data" / "nba_stake_cache.json"

SCRAPE_JS = r"""
(async function() {
  async function gql(variables, query) {
    const r = await fetch("/_api/v1/graphql", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({variables, query})
    });
    return (await r.json())?.data;
  }
  const QF = `query { slugTournament(sport: "basketball", category: "usa", tournament: "nba") {
    fixtureList(type: popular, limit: 30, offset: 0) { id name slug status data { ... on SportFixtureDataMatch { startTime competitors { name } } } } } }`;
  const QP = `query($fixture: String!) { slugFixture(fixture: $fixture) {
    swishGameCompetitorTeams { name players { name markets(inPlay: false, statTypes: [player]) {
      stat { name } lines { line over under suspended balanced } } } } } }`;
  const fx = (await gql({}, QF))?.slugTournament?.fixtureList || [];
  const rows = [], games = [];
  for (const f of fx) {
    if (f.status !== "active") continue;
    const comps = (f.data?.competitors || []).map(c => c.name);
    games.push({fixture: f.slug, start: f.data?.startTime, teams: comps});
    const d = await gql({fixture: f.slug}, QP);
    for (const t of (d?.slugFixture?.swishGameCompetitorTeams || []))
      for (const p of (t.players || [])) for (const m of (p.markets || []))
        for (const l of (m.lines || [])) {
          if (l.suspended || !l.over || !l.under) continue;
          rows.push({fixture: f.slug, team: t.name, player: p.name, stat: m.stat?.name,
                     line: l.line, over: l.over, under: l.under, balanced: !!l.balanced});
        }
    await new Promise(r => setTimeout(r, 200));
  }
  return JSON.stringify({games, rows});
})()
"""


def main() -> None:
    found = _find_stake_tab()
    if not found:
        raise SystemExit(1)
    client = CDPClient(found[1])
    try:
        resp = client.send(
            "Runtime.evaluate",
            {"expression": SCRAPE_JS, "awaitPromise": True, "returnByValue": True, "timeout": 120000},
            timeout=150.0,
        )
    finally:
        client.close()

    value = resp.get("result", {}).get("result", {}).get("value")
    if not value:
        logger.error("Stake scrape failed: %s", resp.get("result", {}).get("exceptionDetails"))
        raise SystemExit(1)

    data = json.loads(value)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "Stake.com Swish player props (CDP)",
        "games": data["games"],
        "rows": data["rows"],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved %d games, %d prop lines to %s", len(data["games"]), len(data["rows"]), OUT)


if __name__ == "__main__":
    main()
