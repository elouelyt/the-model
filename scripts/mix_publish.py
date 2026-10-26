#!/usr/bin/env python3
"""Refresh the mixed NBA+NFL combos and encrypt them for the private panel (data/mix_picks.enc, data/mix_history.enc).

Called at the end of nba_publish.py and nfl_publish.py (so the 'Combinadas' tab always has the latest of both sports); can also be run
alone.  update() returns the encrypted files to `git add`.   python scripts/mix_publish.py
"""

import json
import logging
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from private_crypto import encrypt_file  # noqa: E402

logger = logging.getLogger(__name__)
ENC = ROOT / "data" / "mix_picks.enc"
HIST_ENC = ROOT / "data" / "mix_history.enc"


def update() -> list[str]:
    py = sys.executable
    subprocess.run([py, "scripts/mix_settle.py"], cwd=ROOT, check=False)
    subprocess.run([py, "scripts/mix_combos.py"], cwd=ROOT, check=True)
    picks = ROOT / "data" / "mix_picks.json"
    analysis = ROOT / "data" / "mix_analysis.json"
    doc = json.loads(picks.read_text(encoding="utf-8"))
    if analysis.exists():
        doc["analysis"] = json.loads(analysis.read_text(encoding="utf-8"))
        picks.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    encrypt_file(picks, ENC)
    bundle = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "data" / "mix_history").glob("*.json"))}
    (ROOT / "build").mkdir(exist_ok=True)
    (ROOT / "build" / "mix_history_bundle.json").write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    encrypt_file(ROOT / "build" / "mix_history_bundle.json", HIST_ENC)
    files = ["data/mix_picks.enc", "data/mix_history.enc"]
    try:  # 'Resultados' tab data; its failure must not stop the mixed combos
        import results_publish
        files += results_publish.update()
    except Exception as exc:  # noqa: BLE001
        logger.warning("results tab data skipped: %s", exc)
    return files


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    print(update())
