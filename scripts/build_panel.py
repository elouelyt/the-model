"""Combine several HTML documents into one tabbed page (to be encrypted afterwards)."""

from html import escape

TEMPLATE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>the-model</title>
<style>
body{{margin:0;background:#080808;color:#ececec;font:14px system-ui,sans-serif}}
nav{{position:sticky;top:0;z-index:5;display:flex;flex-wrap:wrap;gap:8px;padding:10px 16px;background:#080808;border-bottom:1px solid #242424}}
nav button{{background:#111;color:#8a8a8a;border:1px solid #242424;border-radius:6px;padding:7px 14px;font:inherit;cursor:pointer}}
nav button[aria-selected=true]{{color:#ececec;border-color:#f97316}}
nav button:focus-visible{{outline:2px solid #f97316;outline-offset:2px}}
iframe{{display:block;width:100%;border:0;background:#080808}}
iframe[hidden]{{display:none}}
</style></head><body>
<nav role="tablist">
{buttons}
</nav>
{frames}
<script>
const fr=[...document.querySelectorAll('iframe')];
function fit(f){{try{{f.style.height=f.contentDocument.documentElement.scrollHeight+'px'}}catch(e){{}}}}
fr.forEach(f=>{{f.addEventListener('load',()=>{{fit(f);new ResizeObserver(()=>fit(f)).observe(f.contentDocument.body)}})}});
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{{
  document.querySelectorAll('nav button').forEach(x=>x.setAttribute('aria-selected',x===b));
  fr.forEach((f,i)=>f.hidden=i!=b.dataset.t);fit(fr[b.dataset.t]);scrollTo(0,0)}});
</script></body></html>
"""

PREFIX = "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"


def build(tabs: list[tuple[str, str]]) -> str:
    """tabs: (label, html) pairs; the first tab is shown on load."""
    buttons = "\n".join(
        f'<button role="tab" aria-selected="{"true" if i == 0 else "false"}" data-t="{i}">{escape(label)}</button>'
        for i, (label, _) in enumerate(tabs)
    )
    frames = "\n".join(
        f'<iframe srcdoc="{escape(doc if doc.lstrip().lower().startswith("<!doctype") else PREFIX + doc, quote=True)}"'
        f'{"" if i == 0 else " hidden"}></iframe>'
        for i, (_, doc) in enumerate(tabs)
    )
    return TEMPLATE.format(buttons=buttons, frames=frames)
