#!/usr/bin/env python3
"""Watchdog for the whole publishing chain: checks every link and repairs what it can, so nothing depends on someone looking at it.

    python scripts/health_check.py            # check + repair + notify when something is left broken
    python scripts/health_check.py --no-fix   # check only

Checks (times are local = UTC on this PC):
  1. git: half-finished rebase, local commits not pushed (-> git_sync.sync_push)
  2. VPN connected and Chrome 9222 with a stake.com tab whose GraphQL API answers 200 (-> stake_tab.py rotates the VPN IP)
  3. NBA picks fresh while games are still to start (-> stake_tab + nba_publish)
  4. Resultados tab refreshed today after 10:30 (-> settle + results_publish)
  5. Tennis: today's pick (after 17:30) exists in data/predictions and every pick of the last 7 days has its track_record entry
     (-> adds the missing entry as pending; check_results resolves it)
  6. Windows scheduled tasks of the_model: last run result
Result goes to C:/Users/ojiyo/Scripts/logs/HEALTH.log; unresolved problems raise a Windows notification and data/health_status.json.
"""

import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from git_sync import git, sync_push, _in_rebase  # noqa: E402

PY = sys.executable
LOG = Path(r"C:\Users\ojiyo\Scripts\logs\HEALTH.log")
STATUS = ROOT / "data" / "health_status.json"
WINDSCRIBE = r"C:\Program Files\Windscribe\windscribe-cli.exe"
FIX = "--no-fix" not in sys.argv
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("health")
now = datetime.now(timezone.utc)
problems: list[str] = []
repaired: list[str] = []


def run(*cmd: str, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def job_running() -> bool:
    """True while one of the scheduled jobs (the_model_job.ps1) is running: do not repair under its feet."""
    r = run("powershell", "-NoProfile", "-Command",
            "(Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | Where-Object { $_.CommandLine -match 'the_model_job' -and $_.CommandLine -notmatch '-Job health' }).Count", timeout=60)
    return r.stdout.strip() not in ("", "0")


def age_h(path: Path, key: str | None = None) -> float | None:
    try:
        if key:
            ts = json.loads(path.read_text(encoding="utf-8")).get(key)
            return (now - datetime.fromisoformat(ts)).total_seconds() / 3600
        return (now.timestamp() - path.stat().st_mtime) / 3600
    except Exception:  # noqa: BLE001
        return None


def check_git() -> None:
    if _in_rebase():
        git("rebase", "--abort")
        repaired.append("half-finished rebase aborted")
    git("fetch", "origin", "main")
    ahead = int(git("rev-list", "--count", "origin/main..HEAD").stdout.strip() or 0)
    if ahead:
        if not FIX:
            problems.append(f"git: {ahead} local commits not pushed")
            return
        try:
            sync_push()
            repaired.append(f"git: {ahead} unpushed commits pushed")
        except RuntimeError as exc:
            problems.append(f"git: cannot push ({exc})")


def check_stake() -> bool:
    st = run(WINDSCRIBE, "status", timeout=60).stdout
    if "Conectado:" not in st:
        if FIX:
            run(WINDSCRIBE, "connect", "Besa", timeout=90)
            repaired.append("VPN reconnected")
        else:
            problems.append("VPN disconnected")
    r = run(PY, "scripts/stake_tab.py", "nba", timeout=600)  # opens/moves the tab, probes the API and rotates the VPN IP if blocked
    if r.returncode != 0:
        problems.append(f"Stake not reachable: {(r.stdout + r.stderr).strip()[-200:]}")
        return False
    if "Rotating VPN" in r.stdout:
        repaired.append("Stake blocked the IP: VPN rotated")
    return True


def games_to_come() -> bool:
    try:
        games = json.loads((ROOT / "data" / "nba_stake_cache.json").read_text(encoding="utf-8")).get("games", [])
    except Exception:  # noqa: BLE001
        return False
    for g in games:
        try:
            if datetime.fromisoformat(g["start"].replace("Z", "+00:00")) > now:
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def check_nba(stake_ok: bool) -> None:
    if not (now.hour >= 20 or (now.hour == 19 and now.minute >= 30)):
        return
    age = age_h(ROOT / "data" / "nba_picks.json", "timestamp")
    if age is not None and age < 5:
        return
    if not games_to_come():  # nothing left to bet today (or the cache is old): re-read once before deciding
        if not (FIX and stake_ok):
            return
    if FIX and stake_ok:
        r = run(PY, "scripts/nba_publish.py", timeout=1500)
        age = age_h(ROOT / "data" / "nba_picks.json", "timestamp")
        if r.returncode == 0 and age is not None and age < 1:
            repaired.append("NBA picks were stale: republished")
            return
    problems.append(f"NBA picks stale ({'unknown' if age is None else f'{age:.1f} h'})")


def check_results() -> None:
    if (now.hour, now.minute) < (10, 30):
        return
    age = age_h(ROOT / "data" / "results.json", "timestamp")
    if age is not None and age < (now.hour + now.minute / 60):  # refreshed since midnight
        return
    if FIX:
        for script in ("scripts/nba_settle.py", "nfl/nfl_settle.py", "scripts/mix_settle.py", "scripts/real_bets.py"):
            run(PY, script, timeout=600)
        run(PY, "scripts/results_publish.py", "--push", timeout=600)
        age = age_h(ROOT / "data" / "results.json", "timestamp")
        if age is not None and age < 1:
            repaired.append("Resultados tab was stale: settled and republished")
            return
    problems.append("Resultados tab not refreshed today")


def check_tennis() -> None:
    """Every prediction of the last 7 days must have its track_record entry; today's prediction must exist after 17:30."""
    track = ROOT / "data" / "track_record.json"
    tr = json.loads(track.read_text(encoding="utf-8"))
    changed = False
    for back in range(0, 8):
        d = (now - timedelta(days=back)).date()
        pf = ROOT / "data" / "predictions" / f"{d}.json"
        if not pf.exists():
            continue  # a day without value pick is legitimate; the bot run itself is checked below
        parlays = json.loads(pf.read_text(encoding="utf-8")).get("parlays", [])
        singles = [p["picks"][0] for p in parlays if len(p.get("picks", [])) == 1]
        if not singles:
            continue
        pick = singles[0]
        days = tr["months"].setdefault(d.strftime("%Y-%m"), {"days": {}})["days"]
        if str(d.day) in days:
            continue
        entry = {"legs": [pick["player"]], "stake_odds": pick.get("stake_price"), "best_odds": pick.get("best_price") or pick.get("stake_price"),
                 "won": None, "opponent": pick.get("opponent")}
        if FIX:
            days[str(d.day)] = {"parlays": [entry], "resolved": False}
            changed = True
            repaired.append(f"tennis: missing track record entry for {d} restored ({pick['player']}, pending)")
        else:
            problems.append(f"tennis: {d} pick {pick['player']} missing from track_record")
    if (now.hour, now.minute) >= (17, 30):
        bot = git("log", "origin/main", f"--since={now:%Y-%m-%d} 00:00", "--grep=update predictions", "--format=%h").stdout.split()
        if not bot:
            problems.append("tennis: the GitHub bot has not run today (Daily Predictions workflow)")
    if changed:
        track.write_text(json.dumps(tr, indent=2, ensure_ascii=False), encoding="utf-8")
        run("git", "add", "data/track_record.json")
        run("git", "commit", "-m", "fix: restore missing track record entries (health check)")
        try:
            sync_push()
        except RuntimeError as exc:
            problems.append(f"tennis: restored entry not pushed ({exc})")


def check_tasks() -> None:
    r = run("powershell", "-NoProfile", "-Command",
            "Get-ScheduledTask | Where-Object { $_.TaskName -like 'the-model*' -or $_.TaskName -like 'TheModel*' } | "
            "ForEach-Object { $i = $_ | Get-ScheduledTaskInfo; \"$($_.TaskName)|$($_.State)|$($i.LastTaskResult)|$($i.LastRunTime.ToString('yyyy-MM-dd HH:mm'))\" }", timeout=120)
    for line in r.stdout.splitlines():
        parts = line.strip().split("|")
        if len(parts) == 4 and parts[2] not in ("0", "267009", "267011"):  # 0 ok, 267009 running, 267011 never run
            problems.append(f"scheduled task {parts[0]} last result {parts[2]} ({parts[3]})")


def notify(text: str) -> None:
    ps = ("[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime];"
          "$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent('ToastText02');"
          f"$t.GetElementsByTagName('text').Item(0).AppendChild($t.CreateTextNode('the-model: revisar')) | Out-Null;"
          f"$t.GetElementsByTagName('text').Item(1).AppendChild($t.CreateTextNode('{text[:180].replace(chr(39), '')}')) | Out-Null;"
          "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('the-model').Show([Windows.UI.Notifications.ToastNotification]::new($t))")
    run("powershell", "-NoProfile", "-Command", ps, timeout=60)


def main() -> int:
    if FIX and job_running() and "--force" not in sys.argv:
        logger.info("a scheduled job is running: checking only, no repairs this time")
        globals()["FIX"] = False
    for name, fn in (("git", check_git),):
        fn()
    stake_ok = check_stake()
    for fn in (lambda: check_nba(stake_ok), check_results, check_tennis, check_tasks):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            problems.append(f"check crashed: {fn} {exc}")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{now:%Y-%m-%d %H:%M} OK" if not (problems or repaired) else f"{now:%Y-%m-%d %H:%M} repaired={repaired} problems={problems}"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    STATUS.write_text(json.dumps({"timestamp": now.isoformat(), "problems": problems, "repaired": repaired}, ensure_ascii=False, indent=1), encoding="utf-8")
    logger.info(line)
    if problems:
        notify("; ".join(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
