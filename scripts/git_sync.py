#!/usr/bin/env python3
"""Self-healing `pull --rebase` + `push` for the publish scripts.

The tennis bot (GitHub Actions) and these local jobs both commit to main. A plain `git pull --rebase` stops on the first conflict
(e.g. data/track_record.json) and leaves the local commits unpushed, so the panel silently stops updating. `sync_push()` instead:
aborts any half-finished rebase, fetches, replays the local commits resolving conflicts by file (the bot's files keep the upstream
version, everything else keeps the local one) and pushes, retrying if the remote moved meanwhile.

    from git_sync import sync_push
    sync_push()            # raises RuntimeError if it cannot publish after all retries
"""

import logging
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)

# written by the GitHub Actions bot / tennis pipeline: on conflict the upstream copy wins (the local copy is re-derived from it)
UPSTREAM_WINS = ("data/track_record.json", "data/predictions/")
RETRIES = 4


def git(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=check)


def _in_rebase() -> bool:
    return (ROOT / ".git" / "rebase-merge").exists() or (ROOT / ".git" / "rebase-apply").exists()


def _conflicted() -> list[str]:
    return [p for p in git("diff", "--name-only", "--diff-filter=U").stdout.split() if p]


def _resolve_conflicts() -> bool:
    """Resolve every conflicted file by policy and continue the rebase. During a rebase `--ours` is the upstream, `--theirs` our commit."""
    for _ in range(50):
        files = _conflicted()
        if not files:
            r = git("-c", "core.editor=true", "rebase", "--continue")
            if r.returncode == 0 or not _in_rebase():
                return True
            if not _conflicted():  # nothing left to resolve but git still refuses (e.g. empty commit)
                git("rebase", "--skip")
                if not _in_rebase():
                    return True
            continue
        for f in files:
            side = "--ours" if f.startswith(UPSTREAM_WINS) else "--theirs"
            if git("checkout", side, "--", f).returncode != 0:  # deleted on one side
                git("rm", "-q", "--", f)
            git("add", "--", f)
            logger.info("conflict in %s resolved with %s", f, "upstream" if side == "--ours" else "local")
        r = git("-c", "core.editor=true", "rebase", "--continue")
        if r.returncode == 0 and not _in_rebase():
            return True
    return False


def sync_push() -> None:
    """Fetch, rebase the local commits onto origin/main (auto-resolving conflicts) and push."""
    if _in_rebase():
        logger.warning("half-finished rebase found: aborting it before syncing")
        git("rebase", "--abort")
    last = ""
    for attempt in range(1, RETRIES + 1):
        f = git("fetch", "origin", "main")
        if f.returncode != 0:
            last = f"fetch failed: {f.stderr.strip()}"
            continue
        r = git("rebase", "--autostash", "origin/main")
        if r.returncode != 0:
            if not _in_rebase() or not _resolve_conflicts():
                git("rebase", "--abort")
                last = f"rebase could not be resolved: {r.stderr.strip()[-300:]}"
                continue
        p = git("push", "origin", "main")
        if p.returncode == 0:
            logger.info("pushed (attempt %d)", attempt)
            return
        last = f"push rejected: {p.stderr.strip()[-300:]}"
        logger.warning("%s - retrying", last)
    raise RuntimeError(f"git sync failed after {RETRIES} attempts: {last}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sync_push()
