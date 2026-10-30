#!/usr/bin/env python3
"""Checks that the published private web is complete and fresh. Runs in GitHub Actions every 2 hours (web_check.yml), independent of the local PC.

    DASHBOARD_PASSWORD=... GH_TOKEN=... python scripts/web_check.py [--build-log build.log]

Fails (exit 1, GitHub e-mails the failure) when:
  - the live site or panel.html does not answer 200 or is not the encrypted panel
  - a data file (nba/nfl/mix picks, results) does not decrypt or is stale for the time of day (UTC)
  - panel.html was not rebuilt after the latest data push, or the last panel build skipped a tab (build log has "skipped")
  - the last 'Rebuild private panel' / 'Daily Predictions' / Pages deployment runs failed, or the tennis bot has not run today
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from private_crypto import decrypt_file  # noqa: E402

SITE = "https://elouelyt.github.io/the-model"
TABS = ["Recomendaciones", "Rendimiento", "NBA", "NFL", "MMA", "Combinadas", "Resultados"]
now = datetime.now(timezone.utc)
problems: list[str] = []


def sh(*cmd: str) -> str:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()


def check_live() -> None:
    for path, min_bytes in (("/", 100), ("/panel.html", 50_000)):
        try:
            r = requests.get(SITE + path, timeout=30, headers={"Cache-Control": "no-cache"})
        except requests.RequestException as exc:
            problems.append(f"{path}: not reachable ({exc})")
            continue
        if r.status_code != 200 or len(r.content) < min_bytes:
            problems.append(f"{path}: HTTP {r.status_code}, {len(r.content)} bytes")
        elif path == "/panel.html" and "staticrypt" not in r.text.lower():
            problems.append("panel.html is not the encrypted panel (staticrypt marker missing)")


def load(enc: str) -> dict | None:
    out = Path(tempfile.mkdtemp()) / "x.json"
    try:
        decrypt_file(ROOT / "data" / enc, out)
        return json.loads(out.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        problems.append(f"data/{enc}: does not decrypt ({type(exc).__name__})")
        return None


def age_h(ts: str) -> float:
    return (now - datetime.fromisoformat(ts)).total_seconds() / 3600


def check_data() -> None:
    nba = load("nba_picks.enc")
    if nba and "timestamp" in nba:
        a = age_h(nba["timestamp"])
        if (now.hour, now.minute) >= (20, 30) and a > 6:  # evening batches (18:00 / 19:04 / 22:09) must have run
            problems.append(f"NBA picks stale: {a:.1f} h old")
        elif a > 30:
            problems.append(f"NBA picks very stale: {a:.1f} h old")
    elif nba is not None:
        problems.append("NBA picks without timestamp")
    for enc in ("nfl_picks.enc", "mix_picks.enc"):
        d = load(enc)
        if d and d.get("timestamp") and age_h(d["timestamp"]) > 72:
            problems.append(f"{enc}: {age_h(d['timestamp']):.0f} h old")
    res = load("results.enc")
    if res and res.get("timestamp"):
        a = age_h(res["timestamp"])
        if (now.hour, now.minute) >= (11, 0) and a > 24:
            problems.append(f"Resultados tab not refreshed today ({a:.0f} h old)")


def check_rebuild(build_log: str | None) -> None:
    def ct(*paths: str) -> int:
        return max((int(sh("git", "log", "-1", "--format=%ct", "--", p) or 0) for p in paths), default=0)
    panel = ct("panel.html")
    data = ct("data/nba_picks.enc", "data/nfl_picks.enc", "data/mix_picks.enc", "data/results.enc")
    if data and panel < data - 20 * 60:
        problems.append(f"panel.html is older than the latest data push by {(data - panel) / 60:.0f} min (panel rebuild failed?)")
    if build_log and Path(build_log).exists():
        log = Path(build_log).read_text(encoding="utf-8", errors="replace")
        for line in log.splitlines():
            if "skipped" in line.lower():
                problems.append(f"panel build: {line.strip()}")
        missing = [t for t in TABS if t not in log and t in ("NBA", "NFL", "Combinadas", "Resultados") and f"{t} tab skipped" in log]
        problems += [f"tab {t} missing in the rebuilt panel" for t in missing]


def check_runs() -> None:
    if not os.environ.get("GH_TOKEN"):
        return
    for wf in ("daily.yml", "panel.yml"):
        out = sh("gh", "run", "list", "--workflow", wf, "--limit", "3", "--json", "conclusion,createdAt,status")
        try:
            runs = [r for r in json.loads(out) if r["status"] == "completed"]
        except Exception:  # noqa: BLE001
            continue
        if runs and all(r["conclusion"] == "failure" for r in runs):
            problems.append(f"workflow {wf}: the last {len(runs)} runs failed")
        if wf == "daily.yml" and (now.hour, now.minute) >= (17, 30):
            today = [r for r in runs if r["createdAt"][:10] == f"{now:%Y-%m-%d}"]
            if not today:
                problems.append("tennis bot (daily.yml) has not run today")
    out = sh("gh", "api", "repos/elouelyt/the-model/pages/builds/latest", "--jq", ".status")
    if out and out != "built":
        problems.append(f"GitHub Pages build status: {out}")


def main() -> int:
    log = sys.argv[sys.argv.index("--build-log") + 1] if "--build-log" in sys.argv else None
    for fn in (check_live, check_data, lambda: check_rebuild(log), check_runs):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            problems.append(f"check crashed: {exc}")
    if problems:
        print("WEB CHECK FAILED:")
        for p in problems:
            print(" -", p)
        return 1
    print(f"WEB CHECK OK {now:%Y-%m-%d %H:%M} UTC")
    return 0


if __name__ == "__main__":
    sys.exit(main())
