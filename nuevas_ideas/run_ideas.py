"""Run every paper idea once (after each production batch). Read-only on the production data.

    python nuevas_ideas/run_ideas.py          # all ideas
    python nuevas_ideas/run_ideas.py 03 04    # only those whose folder starts with these prefixes

Ideas 03/04 need only data/nba_picks.json. Idea 02 also needs the debug Chrome with a stake.com tab (price queries).
A failure in one idea never stops the others.
"""

import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent


NFL_IDEAS = ("03", "06", "07", "08", "09")   # ideas that make sense with the single reference book NFL has (02 and 04 are NBA-only)


def run_one(run: Path, sport: str) -> None:
    import os
    env = {**os.environ, "IDEAS_SPORT": sport}
    r = subprocess.run([sys.executable, str(run)], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    print((r.stdout or "").strip())
    if r.returncode:
        print(f"[{run.parent.name} {sport}] failed ({r.returncode}): {(r.stderr or '').strip()[-400:]}")


def main() -> None:
    wanted = sys.argv[1:]
    sys.path.insert(0, str(BASE))
    try:
        import archive
        print("== archivo:", archive.archive_batch(), flush=True)   # raw lines of this batch, kept forever (local)
    except Exception as exc:  # never block the ideas
        print("== archivo failed:", exc)
    for run in sorted((BASE / "ideas").glob("*/run.py")):
        name = run.parent.name
        if wanted and not any(name.startswith(w) for w in wanted):
            continue
        print(f"== {name}", flush=True)
        run_one(run, "nba")
    nfl_picks = BASE.parent / "nfl" / "data" / "nfl_picks.json"
    if nfl_picks.exists():
        try:
            print("== archivo NFL:", archive.archive_nfl_batch(), flush=True)
        except Exception as exc:
            print("== archivo NFL failed:", exc)
        for run in sorted((BASE / "ideas").glob("*/run.py")):
            name = run.parent.name
            if name[:2] in NFL_IDEAS and (not wanted or any(name.startswith(w) for w in wanted)):
                print(f"== {name} (NFL)", flush=True)
                run_one(run, "nfl")


if __name__ == "__main__":
    main()
