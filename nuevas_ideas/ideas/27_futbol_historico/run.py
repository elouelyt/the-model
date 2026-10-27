"""Idea 27 - historical test of "soft book price vs sharp (Pinnacle) fair" on free football-data.co.uk odds (12 leagues, 2014-15 .. 2024-25).

For every match and outcome (1X2 and over/under 2.5) we look at the SAME-MOMENT pre-match prices of a soft book (Bet365) and Pinnacle:
  value rule  : B365 odds * fair_prob(Pinnacle pre, proportional de-vig) - 1 > THR   (information available when betting)
  CLV         : the same B365 odds judged with Pinnacle's CLOSING fair probability (EV at the close; > 0 = we bought better than the sharp close)
  ROI         : realised flat 1 u return at the B365 odds
Also "best price" (market maximum of the pre-match books) instead of Bet365. Paper only; data files are public CSVs fetched into a temp folder.
Usage: python run.py <folder with the CSVs>  ->  RESULTADO.md here
"""

import glob
import math
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
THRS = (0.0, 0.02, 0.05)


def devig(*odds):
    inv = [1 / o for o in odds]
    s = sum(inv)
    return [i / s for i in inv]


def load(folder: str) -> pd.DataFrame:
    frames = []
    for f in sorted(glob.glob(os.path.join(folder, "*.csv"))):
        try:
            d = pd.read_csv(f, encoding="latin-1", on_bad_lines="skip")
        except Exception:  # noqa: BLE001
            continue
        if "FTR" not in d or d.empty:
            continue
        d["file"] = os.path.basename(f)
        d["league"] = d["Div"] if "Div" in d else os.path.basename(f)[:2]
        frames.append(d)
    return pd.concat(frames, ignore_index=True)


def rows(df: pd.DataFrame) -> pd.DataFrame:
    out = []
    spec = [("1X2", ["H", "D", "A"], "B365{}", "PS{}", "PSC{}", "Max{}", "FTR"),
            ("OU2.5", [">2.5", "<2.5"], "B365{}", "P{}", "PC{}", "Max{}", None)]
    for mkt, outs, soft, pre, close, best, res in spec:
        # build outcome-by-outcome with all columns needed for the whole market
        if mkt == "1X2":
            need = ["B365H", "B365D", "B365A", "PSH", "PSD", "PSA", "PSCH", "PSCD", "PSCA", "MaxH", "MaxD", "MaxA", "FTR"]
            if any(c not in df for c in need):
                continue
            d = df.dropna(subset=need)
            d = d[(d[need[:-1]] > 1.0).all(axis=1)]
            for _, r in d.iterrows():
                pre = devig(r.PSH, r.PSD, r.PSA)
                clo = devig(r.PSCH, r.PSCD, r.PSCA)
                for k, (lab, s, b) in enumerate((("H", r.B365H, r.MaxH), ("D", r.B365D, r.MaxD), ("A", r.B365A, r.MaxA))):
                    out.append((mkt, r.league, r.file, s, b, pre[k], clo[k], 1.0 if r.FTR == lab else 0.0))
        else:
            need = ["B365>2.5", "B365<2.5", "P>2.5", "P<2.5", "PC>2.5", "PC<2.5", "Max>2.5", "Max<2.5", "FTHG", "FTAG"]
            if any(c not in df for c in need):
                continue
            d = df.dropna(subset=need)
            d = d[(d[need[:-2]] > 1.0).all(axis=1)]
            for _, r in d.iterrows():
                tot = r.FTHG + r.FTAG
                if tot == 2.5:
                    continue
                pre = devig(r["P>2.5"], r["P<2.5"])
                clo = devig(r["PC>2.5"], r["PC<2.5"])
                over = 1.0 if tot > 2.5 else 0.0
                out.append((mkt, r.league, r.file, r["B365>2.5"], r["Max>2.5"], pre[0], clo[0], over))
                out.append((mkt, r.league, r.file, r["B365<2.5"], r["Max<2.5"], pre[1], clo[1], 1.0 - over))
    return pd.DataFrame(out, columns=["mkt", "league", "file", "soft", "best", "p_pre", "p_close", "y"])


def table(d: pd.DataFrame, price: str, label: str) -> list[str]:
    lines = [f"### {label}", "", "| Mercado | Umbral EV (precio vs Pinnacle antes del cierre) | Apuestas | EV con prob. de cierre (CLV) | ROI realizado | z del ROI |", "|---|---|---|---|---|---|"]
    for mkt in ("1X2", "OU2.5"):
        m = d[d.mkt == mkt]
        for thr in THRS:
            s = m[(m[price] * m.p_pre - 1) > thr]
            if len(s) < 100:
                continue
            ev_close = (s[price] * s.p_close - 1).mean()
            ret = np.where(s.y == 1, s[price] - 1, -1.0)
            roi = ret.mean()
            z = roi / (ret.std(ddof=1) / math.sqrt(len(ret)))
            lines.append(f"| {mkt} | > {thr:.0%} | {len(s):,} | {ev_close:+.2%} | {roi:+.2%} | {z:+.2f} |")
    return lines + [""]


def main(folder: str) -> None:
    df = load(folder)
    d = rows(df)
    out = ["# Idea 27 - fútbol histórico: precio blando contra Pinnacle", "", f"Generado {datetime.now():%Y-%m-%d %H:%M}. {len(df):,} partidos, {len(d):,} apuestas posibles (ligas de football-data.co.uk, 2014-15 a 2024-25).", ""]
    out += table(d, "soft", "Casa blanda: Bet365 (precio antes del partido)") + table(d, "best", "Mejor precio del mercado antes del partido (máximo entre casas)")
    all_soft = d.assign(ev=d.soft * d.p_close - 1)
    out += ["### Referencia: todas las apuestas posibles en Bet365", "", f"EV medio con prob. de cierre de Pinnacle: {all_soft.ev.mean():+.2%} (margen que paga quien apuesta a ciegas)", ""]
    out += ["### Por liga (Bet365, umbral > 2 %, ambos mercados)", "", "| Liga | Apuestas | EV con prob. de cierre | ROI realizado |", "|---|---|---|---|"]
    s = d[(d.soft * d.p_pre - 1) > 0.02]
    for lg, g in s.groupby("league"):
        if len(g) < 150:
            continue
        ret = np.where(g.y == 1, g.soft - 1, -1.0)
        out.append(f"| {lg} | {len(g):,} | {(g.soft * g.p_close - 1).mean():+.2%} | {ret.mean():+.2%} |")
    (HERE / "RESULTADO.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1])
