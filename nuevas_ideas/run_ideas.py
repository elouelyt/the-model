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
        r = subprocess.run([sys.executable, str(run)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        print((r.stdout or "").strip())
        if r.returncode:
            print(f"[{name}] failed ({r.returncode}): {(r.stderr or '').strip()[-400:]}")


if __name__ == "__main__":
    main()
