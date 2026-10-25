#!/usr/bin/env python3
"""Scrape NFL player props from Stake (Swish markets) through the running debug Chrome (CDP).

Same method as scripts/nba_stake_scraper.py (GraphQL /_api/v1/graphql from a stake.com tab); only the sport changes.
Needs Chrome open on stake.com (scripts/start_chrome_debug.bat). Output: nfl/data/nfl_stake_cache.json
(one row per player / stat / line, with the outcome id of the line and the fixture id for betslip links).
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from stake_scraper import CDPClient, _find_stake_tab  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE = Path(__file__).resolve().parent
OUT = BASE / "data" / "nfl_stake_cache.json"

STATS = ["passing yards", "passing attempts", "passing completions", "passing touchdowns", "interceptions",
         "rushing yards", "rushing attempts", "receiving yards", "receptions"]

SCRAPE_JS = r"""
(async function(STATS) {
  async function gql(variables, query) {
    const r = await fetch("/_api/v1/graphql", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({variables, query})
    });
    return (await r.json())?.data;
  }
  const QF = `query { slugTournament(sport: "american-football", category: "usa", tournament: "nfl") {
    fixtureList(type: popular, limit: 30, offset: 0) { id name slug status data { ... on SportFixtureDataMatch { startTime competitors { name } } } } } }`;
  const QP = `query($fixture: String!) { slugFixture(fixture: $fixture) {
    swishGameCompetitorTeams { name players { name markets(inPlay: false, statTypes: [player]) {
      stat { name } lines { id line over under suspended balanced } } } } } }`;
  const fx = (await gql({}, QF))?.slugTournament?.fixtureList || [];
  const rows = [], games = [];
  for (const f of fx) {
    if (f.status !== "active") continue;
    const comps = (f.data?.competitors || []).map(c => c.name);
    games.push({fixture: f.slug, start: f.data?.startTime, teams: comps});
    const d = await gql({fixture: f.slug}, QP);
    for (const t of (d?.slugFixture?.swishGameCompetitorTeams || []))
      for (const p of (t.players || [])) for (const m of (p.markets || [])) {
        if (!STATS.includes(m.stat?.name)) continue;
        for (const l of (m.lines || [])) {
          if (l.suspended || !l.over || !l.under) continue;
          rows.push({fixture: f.slug, team: t.name, player: p.name, stat: m.stat.name,
                     line: l.line, over: l.over, under: l.under, balanced: !!l.balanced,
                     outcome_id: l.id, event_id: f.id});
        }
      }
    await new Promise(r => setTimeout(r, 200));
  }
  return JSON.stringify({games, rows});
})
"""


def main() -> None:
    found = _find_stake_tab()
    if not found:
        raise SystemExit(1)
    client = CDPClient(found[1])
    try:
        resp = client.send("Runtime.evaluate",
                           {"expression": f"({SCRAPE_JS})({json.dumps(STATS)})", "awaitPromise": True,
                            "returnByValue": True, "timeout": 150000}, timeout=180.0)
    finally:
        client.close()
    value = resp.get("result", {}).get("result", {}).get("value")
    if not value:
        logger.error("Stake NFL scrape failed: %s", resp.get("result", {}).get("exceptionDetails"))
        raise SystemExit(1)
    data = json.loads(value)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "source": "Stake.com Swish NFL (CDP)",
                               "games": data["games"], "rows": data["rows"]}, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved %d games, %d prop lines to %s", len(data["games"]), len(data["rows"]), OUT)


if __name__ == "__main__":
    main()
