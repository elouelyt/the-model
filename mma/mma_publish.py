#!/usr/bin/env python3
"""Refresh the MMA tracking (our model vs Jev), settle it and encrypt data/mma_picks.enc / data/mma_history.enc for the private panel's 'MMA Jev' tab.

Called from scripts/mix_publish.update() (in a try/except: MMA must never stop the NBA/NFL flow); can also be run alone.
update() returns the encrypted files to `git add`.   python mma/mma_publish.py
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from private_crypto import encrypt_file  # noqa: E402


def update() -> list[str]:
    subprocess.run([sys.executable, "mma/mma_track.py"], cwd=ROOT, check=True)
    analysis = json.loads((ROOT / "data" / "mma_analysis.json").read_text(encoding="utf-8"))
    picks = ROOT / "data" / "mma_picks.json"
    picks.write_text(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "analysis": analysis}, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    encrypt_file(picks, ROOT / "data" / "mma_picks.enc")
    bundle = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "data" / "mma_history").glob("*.json"))}
    (ROOT / "build").mkdir(exist_ok=True)
    (ROOT / "build" / "mma_history_bundle.json").write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    encrypt_file(ROOT / "build" / "mma_history_bundle.json", ROOT / "data" / "mma_history.enc")
    return ["data/mma_picks.enc", "data/mma_history.enc"]


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    print(update())
