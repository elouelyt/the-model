#!/usr/bin/env python3
"""Finds the Stake match page of the daily tennis pick and publishes it, so the side panel opens the match directly (like NBA/NFL).

    python scripts/tennis_link.py            # latest pick in data/predictions -> data/tennis_links.json (+ commit and push)
    python scripts/tennis_link.py --no-push

The pick comes from the GitHub bot (no Stake link in it), so the match is looked up here with the Stake GraphQL API through the debug Chrome
(port 9222, same as stake_tab.py): category atp / challenger / davis-cup -> tournaments -> fixtures; the page URL is
https://stake.com/es/sports/tennis/<category>/<tournament>/<fixture slug>.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
import websocket

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from git_sync import git, sync_push  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tennis_link")

OUT = ROOT / "data" / "tennis_links.json"
KEEP_DAYS = 6

FIND_JS = r"""(async()=>{
const WANT=__WANT__;
const plain=s=>String(s||'').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/[^a-z ]/g,' ').replace(/\s+/g,' ').trim();
const sur=s=>plain(s).split(' ').pop();
const gql=async(variables,query)=>{const r=await fetch('/_api/graphql',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({variables,query})});return (await r.json())?.data};
const QC=`query Cat($sport:String!,$cat:String!){slugCategory(sport:$sport,category:$cat){tournamentList(limit:100){name slug}}}`;
const QT=`query T($sport:String!,$cat:String!,$slug:String!,$type:SportSearchEnum!){slugTournament(sport:$sport,category:$cat,tournament:$slug){name fixtureList(type:$type,limit:50,offset:0){slug name data{__typename ... on SportFixtureDataMatch{startTime}}}}}`;
const a=sur(WANT.player), b=sur(WANT.opponent);
for(const cat of ['atp','challenger','davis-cup']){
 const c=await gql({sport:'tennis',cat},QC);
 for(const t of (c?.slugCategory?.tournamentList||[])){
  if(/doubles/i.test(t.slug)) continue;
  const d=await gql({sport:'tennis',cat,slug:t.slug,type:'popular'},QT);
  for(const f of (d?.slugTournament?.fixtureList||[])){
   const n=plain(f.name);
   if(!/\//.test(f.name||'') && n.includes(a) && n.includes(b))
     return JSON.stringify({url:`https://stake.com/es/sports/tennis/${cat}/${t.slug}/${f.slug}`,name:f.name,start:f.data?.startTime||null,tournament:d.slugTournament.name});
  }
  await new Promise(r=>setTimeout(r,100));
 }
}
return JSON.stringify(null);})()"""


def latest_pick() -> tuple[str, dict] | None:
    for f in sorted((ROOT / "data" / "predictions").glob("*.json"), reverse=True)[:3]:
        d = json.loads(f.read_text(encoding="utf-8"))
        for p in d.get("parlays", []):
            if len(p.get("picks", [])) == 1:
                return d["date"], p["picks"][0]
    return None


def lookup(player: str, opponent: str) -> dict | None:
    tabs = requests.get("http://localhost:9222/json", timeout=5).json()
    tab = next((t for t in tabs if "stake.com" in t.get("url", "") and t.get("webSocketDebuggerUrl")), None)
    if not tab:
        raise RuntimeError("no stake.com tab in the debug Chrome")
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=30)
    try:
        expr = FIND_JS.replace("__WANT__", json.dumps({"player": player, "opponent": opponent}))
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}}))
        ws.settimeout(180)
        while True:
            m = json.loads(ws.recv())
            if m.get("id") == 1:
                return json.loads(m["result"]["result"].get("value") or "null")
    finally:
        ws.close()


def main(push: bool = True) -> int:
    pick = latest_pick()
    if not pick:
        logger.info("no tennis pick found")
        return 0
    day, p = pick
    doc = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"links": {}}
    if doc["links"].get(day, {}).get("player") == p["player"] and doc["links"][day].get("url"):
        logger.info("link for %s already published", day)
        return 0
    found = lookup(p["player"], p["opponent"])
    if not found:
        logger.warning("%s - %s not listed on Stake (yet)", p["player"], p["opponent"])
        return 1
    doc["links"][day] = {"player": p["player"], "opponent": p["opponent"], **found}
    keep = sorted(doc["links"])[-KEEP_DAYS:]
    doc = {"timestamp": datetime.now(timezone.utc).isoformat(), "links": {k: doc["links"][k] for k in keep}}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    logger.info("%s: %s", day, found["url"])
    if push:
        git("add", "data/tennis_links.json")
        git("commit", "-m", f"data: tennis link {day}")
        sync_push()
    return 0


if __name__ == "__main__":
    sys.exit(main(push="--no-push" not in sys.argv))
