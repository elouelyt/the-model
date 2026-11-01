#!/usr/bin/env python3
"""Refresh Jev's combos, settle them and encrypt data/jev_picks.enc / data/jev_history.enc for the private panel's 'Jev' tab.

Called from scripts/mix_publish.update() (so every NBA/NFL batch refreshes it, in a try/except: Jev must never stop the normal flow);
can also be run alone.  update() returns the encrypted files to `git add`.   python jev/jev_publish.py
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from private_crypto import encrypt_file  # noqa: E402


def update() -> list[str]:
    py = sys.executable
    subprocess.run([py, "jev/jev_settle.py"], cwd=ROOT, check=False)
    subprocess.run([py, "jev/jev_combos.py"], cwd=ROOT, check=True)
    picks = ROOT / "data" / "jev_picks.json"
    analysis = ROOT / "data" / "jev_analysis.json"
    doc = json.loads(picks.read_text(encoding="utf-8"))
    if analysis.exists():
        a = json.loads(analysis.read_text(encoding="utf-8"))
        doc["analysis"] = {k: a.get(k) for k in ("legs_settled", "combos_settled", "brier", "comparison", "combo_families", "calibration")}
        picks.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    encrypt_file(picks, ROOT / "data" / "jev_picks.enc")
    bundle = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "data" / "jev_history").glob("*.json"))}
    (ROOT / "build").mkdir(exist_ok=True)
    (ROOT / "build" / "jev_history_bundle.json").write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    encrypt_file(ROOT / "build" / "jev_history_bundle.json", ROOT / "data" / "jev_history.enc")
    return ["data/jev_picks.enc", "data/jev_history.enc"]


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    print(update())
