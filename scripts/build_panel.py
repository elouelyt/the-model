"""Combine the full site and the stats dashboard into one tabbed page (to be encrypted).

Usage: python scripts/build_panel.py <site.html> <dashboard.html> <out.html>
"""

import sys
from html import escape
from pathlib import Path

TEMPLATE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>the-model</title>
<style>
body{{margin:0;background:#080808;color:#ececec;font:14px system-ui,sans-serif}}
nav{{position:sticky;top:0;z-index:5;display:flex;gap:8px;padding:10px 16px;background:#080808;border-bottom:1px solid #242424}}
nav a{{background:#111;color:#8a8a8a;border:1px solid #242424;border-radius:6px;padding:7px 14px;text-decoration:none;margin-left:auto}}
nav button{{background:#111;color:#8a8a8a;border:1px solid #242424;border-radius:6px;padding:7px 14px;font:inherit;cursor:pointer}}
nav button[aria-selected=true]{{color:#ececec;border-color:#f97316}}
nav button:focus-visible{{outline:2px solid #f97316;outline-offset:2px}}
iframe{{display:block;width:100%;border:0;background:#080808}}
iframe[hidden]{{display:none}}
</style></head><body>
<nav role="tablist">
<button role="tab" aria-selected="true" data-t="0">Recomendaciones</button>
<button role="tab" aria-selected="false" data-t="1">Rendimiento</button>
<a href="nba.html">NBA →</a>
</nav>
<iframe id="f0" srcdoc="{site}"></iframe>
<iframe id="f1" srcdoc="{dash}" hidden></iframe>
<script>
const fr=[f0,f1];
function fit(f){{try{{f.style.height=f.contentDocument.documentElement.scrollHeight+'px'}}catch(e){{}}}}
fr.forEach(f=>{{f.addEventListener('load',()=>{{fit(f);new ResizeObserver(()=>fit(f)).observe(f.contentDocument.body)}})}});
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{{
  document.querySelectorAll('nav button').forEach(x=>x.setAttribute('aria-selected',x===b));
  fr.forEach((f,i)=>f.hidden=i!=b.dataset.t);fit(fr[b.dataset.t]);scrollTo(0,0)}});
</script></body></html>
"""


def main() -> None:
    site, dash, out = (Path(a) for a in sys.argv[1:4])
    page = TEMPLATE.format(
        site=escape(site.read_text(encoding="utf-8"), quote=True),
        dash=escape("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                    + dash.read_text(encoding="utf-8"), quote=True),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"Written {out}")


if __name__ == "__main__":
    main()
