#!/usr/bin/env python3
"""Build the private, encrypted panel.html with four tabs: Recomendaciones, Rendimiento, NBA, MMA.

Usage:
  python scripts/build_private.py --from-build   # daily run: use build/site.html and refresh data/site.enc
  python scripts/build_private.py                # rebuild from data/site.enc (e.g. when NBA picks change)
Needs DASHBOARD_PASSWORD. The full site and the NBA picks only exist in the repo as ciphertext.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from bs4 import BeautifulSoup
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import generate_dashboard  # noqa: E402
import generate_nba  # noqa: E402
from build_panel import build  # noqa: E402
from private_crypto import decrypt_file, encrypt_file  # noqa: E402

BUILD = ROOT / "build"
SITE_ENC = ROOT / "data" / "site.enc"
NBA_ENC = ROOT / "data" / "nba_picks.enc"
SALT = "8669795df810e4666e526fa8a931d9da"
STATICRYPT = "staticrypt@3.5.4"


def split_site(site_html: str) -> tuple[str, str]:
    """Return (recommendations, mma) documents from the generated site."""
    rec = BeautifulSoup(site_html, "html.parser")
    mma_section = rec.select_one("section.mma-section")
    if mma_section is None:
        return site_html, ""
    mma = BeautifulSoup(site_html, "html.parser")
    main = mma.find("main")
    keep = mma.select_one("section.mma-section")
    for child in list(main.children):
        if child is not keep and getattr(child, "name", None) != "style":
            child.extract()
    mma_section.extract()
    return str(rec), str(mma)


def main() -> None:
    load_dotenv(ROOT / ".env")
    BUILD.mkdir(exist_ok=True)
    site_path = BUILD / "site.html"
    if "--from-build" in sys.argv:
        encrypt_file(site_path, SITE_ENC)
    else:
        decrypt_file(SITE_ENC, site_path)
    rec, mma = split_site(site_path.read_text(encoding="utf-8"))

    tabs = [("Recomendaciones", rec), ("Rendimiento", generate_dashboard.build(generate_dashboard.load_bets()))]
    if NBA_ENC.exists():
        picks_path = BUILD / "nba_picks.json"
        decrypt_file(NBA_ENC, picks_path)
        tabs.append(("NBA", generate_nba.build(json.loads(picks_path.read_text(encoding="utf-8")))))
    if mma:
        tabs.append(("MMA", mma))

    src = BUILD / "panel_src.html"
    src.write_text(build(tabs), encoding="utf-8")
    shutil.rmtree(BUILD / "enc", ignore_errors=True)
    import os
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    subprocess.run([npx, "--yes", STATICRYPT, str(src), "-p", os.environ["DASHBOARD_PASSWORD"], "--short",
                    "--salt", SALT, "--remember", "30", "--template-title", "Acceso",
                    "--template-instructions", "Panel privado", "-d", str(BUILD / "enc")], check=True, cwd=ROOT)
    shutil.copy(BUILD / "enc" / "panel_src.html", ROOT / "panel.html")
    print(f"panel.html built with tabs: {[t[0] for t in tabs]}")


if __name__ == "__main__":
    main()
