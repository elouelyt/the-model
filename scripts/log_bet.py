"""Manual bet logger — adds a bet to data/track_record.json.

Usage examples:
    # Log a won single bet:
    python scripts/log_bet.py --legs "Ben Shelton" --odds 1.81 --won

    # Log a lost 2-leg parlay for a specific date:
    python scripts/log_bet.py --legs "Carlos Alcaraz" "Jannik Sinner" --odds 1.73 --lost

    # Log a bet with stake odds different from best odds:
    python scripts/log_bet.py --legs "Ben Shelton" --odds 1.78 --stake-odds 1.81 --won

    # Log a pending bet (result not yet known):
    python scripts/log_bet.py --legs "Novak Djokovic" "Carlos Alcaraz" --odds 1.70

    # Log for a specific date (default is today UTC):
    python scripts/log_bet.py --date 2026-08-09 --legs "Ben Shelton" --odds 1.81 --won
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_TRACK_FILE = _ROOT / "data" / "track_record.json"


def _load() -> dict:
    if _TRACK_FILE.exists():
        return json.loads(_TRACK_FILE.read_text(encoding="utf-8"))
    return {"months": {}}


def _save(tr: dict) -> None:
    _TRACK_FILE.write_text(
        json.dumps(tr, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Log a manual bet to track_record.json")
    parser.add_argument(
        "--date", default=None,
        help="Date in YYYY-MM-DD format (default: today UTC)",
    )
    parser.add_argument(
        "--legs", nargs="+", required=True,
        help="Player name(s) in the bet, e.g. 'Ben Shelton' or 'Ben Shelton' 'Carlos Alcaraz'",
    )
    parser.add_argument(
        "--odds", type=float, required=True,
        help="Decimal odds paid (Stake price or best available)",
    )
    parser.add_argument(
        "--stake-odds", type=float, default=None,
        help="Stake-specific decimal odds if different from --odds",
    )
    result_group = parser.add_mutually_exclusive_group()
    result_group.add_argument("--won", action="store_true", help="Bet won")
    result_group.add_argument("--lost", action="store_true", help="Bet lost")
    args = parser.parse_args()

    # Resolve date
    if args.date:
        try:
            dt = datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(f"ERROR: invalid date '{args.date}', expected YYYY-MM-DD")
            sys.exit(1)
    else:
        dt = datetime.now(timezone.utc)

    month_key = dt.strftime("%Y-%m")
    day_key = str(dt.day)

    # Result
    if args.won:
        won = True
    elif args.lost:
        won = False
    else:
        won = None  # pending

    parlay = {
        "legs": args.legs,
        "stake_odds": args.stake_odds if args.stake_odds else args.odds,
        "best_odds": args.odds,
        "won": won,
    }

    tr = _load()
    tr.setdefault("months", {}).setdefault(month_key, {}).setdefault("days", {})
    day = tr["months"][month_key]["days"].setdefault(day_key, {"parlays": [], "resolved": False})
    day["parlays"].append(parlay)

    # Mark resolved if result is known
    all_resolved = all(p.get("won") is not None for p in day["parlays"])
    day["resolved"] = all_resolved

    _save(tr)

    status = "WON" if won is True else ("LOST" if won is False else "PENDING")
    pnl = (15 * (args.odds - 1)) if won is True else (-15 if won is False else 0)
    legs_str = " + ".join(args.legs)
    print(f"✓ Logged: [{month_key} day {day_key}] {legs_str} @ {args.odds:.2f} → {status} ({pnl:+.2f}€)")
    print(f"  File: {_TRACK_FILE}")
    print()
    print("Next steps:")
    print("  git add data/track_record.json && git commit -m 'fix: log manual bet'")
    print("  git push")
    print("  gh workflow run daily.yml --repo elouelyt/the-model")


if __name__ == "__main__":
    main()
