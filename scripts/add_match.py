"""Add a match manually to data/manual_odds.json for today's pipeline run.

Usage:
    python scripts/add_match.py "Lorenzo Sonego" "Vit Kopriva" 1.63 2.20
    python scripts/add_match.py "Oliver Crawford" "Lukas Neumayer" 1.64 2.16 --tournament "US Open Qualifying"
    python scripts/add_match.py --clear          # remove all today's manual matches
    python scripts/add_match.py --list           # show today's matches

The pipeline (coordinator.py tier 3) reads this file when both The Odds API
and the Stake fallback return no upcoming matches.
"""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_MANUAL_FILE = _ROOT / "data" / "manual_odds.json"


def _load() -> dict:
    if _MANUAL_FILE.exists():
        return json.loads(_MANUAL_FILE.read_text(encoding="utf-8"))
    return {"date": "", "matches": []}


def _save(data: dict) -> None:
    _MANUAL_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def main() -> None:
    parser = argparse.ArgumentParser(description="Add a match to manual_odds.json")
    parser.add_argument("home", nargs="?", help="Home player name")
    parser.add_argument("away", nargs="?", help="Away player name")
    parser.add_argument("home_odds", nargs="?", type=float, help="Home player decimal odds")
    parser.add_argument("away_odds", nargs="?", type=float, help="Away player decimal odds")
    parser.add_argument("--tournament", default="Manual", help="Tournament name")
    parser.add_argument("--date", default=None, help="Match date YYYY-MM-DD (default: today UTC)")
    parser.add_argument("--clear", action="store_true", help="Clear all manual matches for today")
    parser.add_argument("--list", action="store_true", help="List today's manual matches")
    args = parser.parse_args()

    today = args.date or _today()
    data = _load()

    # Reset if date changed
    if data.get("date") != today:
        data = {"date": today, "matches": []}

    if args.clear:
        data["matches"] = []
        _save(data)
        print(f"Cleared all manual matches for {today}")
        return

    if args.list:
        matches = data.get("matches", [])
        if not matches:
            print(f"No manual matches for {today}")
        for m in matches:
            home = m["home_team"]
            away = m["away_team"]
            bk = m["bookmakers"][0]["markets"][0]["outcomes"]
            h_odds = next(o["price"] for o in bk if o["name"] == home)
            a_odds = next(o["price"] for o in bk if o["name"] == away)
            print(f"  {home} ({h_odds}) vs {away} ({a_odds})  [{m['sport_title']}]")
        return

    if not all([args.home, args.away, args.home_odds, args.away_odds]):
        parser.print_help()
        sys.exit(1)

    # Build commence_time: today at 14:00 UTC
    commence = f"{today}T14:00:00Z"

    match = {
        "id": f"manual_{args.home.lower().replace(' ', '_')}_{args.away.lower().replace(' ', '_')}",
        "sport_key": "tennis_atp_manual",
        "sport_title": args.tournament,
        "commence_time": commence,
        "home_team": args.home,
        "away_team": args.away,
        "bookmakers": [{
            "key": "stake",
            "title": "Stake",
            "markets": [{"key": "h2h", "outcomes": [
                {"name": args.home, "price": args.home_odds},
                {"name": args.away, "price": args.away_odds},
            ]}],
        }],
    }

    data["matches"].append(match)
    _save(data)

    print(f"Added: {args.home} ({args.home_odds}) vs {args.away} ({args.away_odds}) [{args.tournament}]")
    print(f"  File: {_MANUAL_FILE}")
    print()
    print("Next steps:")
    print("  git add data/manual_odds.json && git commit -m 'feat: add manual odds'")
    print("  git push")
    print("  gh workflow run daily.yml --repo elouelyt/the-model")


if __name__ == "__main__":
    main()
