// Stake Bet Guide - tennis link finder. When the side panel asks for it (user clicked the tennis pick), it looks the match up with the same
// read-only GraphQL query the Stake page itself uses for its tennis lists and answers with the match page URL. It never clicks, types or
// changes the page, and does nothing until the panel sends the message.
(() => {
  const CATS = ["atp", "challenger", "davis-cup"];
  const QUERY_CAT = `query Cat($sport: String!, $cat: String!) { slugCategory(sport: $sport, category: $cat) { tournamentList(limit: 100) { name slug } } }`;
  const QUERY_T = `query T($sport: String!, $cat: String!, $slug: String!, $type: SportSearchEnum!) {
    slugTournament(sport: $sport, category: $cat, tournament: $slug) {
      fixtureList(type: $type, limit: 50, offset: 0) { slug name }
    }
  }`;
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const plain = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z ]/g, " ").replace(/\s+/g, " ").trim();
  const surname = (s) => plain(s).split(" ").pop();

  async function gql(variables, query) {
    const r = await fetch("/_api/graphql", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ variables, query }) });
    return (await r.json()).data;
  }

  // singles fixture whose name holds both surnames; the tournament list is walked category by category and stops at the first hit
  async function findMatch(player, opponent) {
    const a = surname(player), b = surname(opponent);
    for (const cat of CATS) {
      const c = await gql({ sport: "tennis", cat }, QUERY_CAT);
      for (const t of (c && c.slugCategory && c.slugCategory.tournamentList) || []) {
        if (/doubles/i.test(t.slug)) continue;
        const d = await gql({ sport: "tennis", cat, slug: t.slug, type: "popular" }, QUERY_T);
        for (const f of (d && d.slugTournament && d.slugTournament.fixtureList) || []) {
          const n = plain(f.name);
          if (!/\//.test(f.name || "") && n.includes(a) && n.includes(b)) return `https://stake.com/es/sports/tennis/${cat}/${t.slug}/${f.slug}`;
        }
        await wait(120);
      }
    }
    return null;
  }

  // ---- highlighter on the match page: the "Ganador" outcome of the picked player (CSS Custom Highlight API: no element is added or changed)
  let target = null;
  let lastReport = "";
  const report = (code, detail) => {
    if (code + "|" + detail === lastReport) return;
    lastReport = code + "|" + detail;
    try { chrome.storage.local.set({ guideState: { code, detail, at: Date.now() } }); } catch (e) { /* extension reloaded */ }
  };
  // Stake writes "Surname, Firstname"; the pick says "Firstname Surname"
  const key = (s) => { const t = String(s || ""); const [a, b] = t.includes(",") ? t.split(",") : [t, ""]; return plain(t.includes(",") ? `${b} ${a}` : t); };
  const textNode = (el) => { const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); for (let n = w.nextNode(); n; n = w.nextNode()) if (n.textContent.trim()) return n; return null; };
  const num = (s) => { const v = parseFloat(String(s).replace(",", ".")); return Number.isFinite(v) ? v : null; };
  const sheet = new CSSStyleSheet();
  sheet.replaceSync("::highlight(sbg-ty){background:#ffd400;color:#000}::highlight(sbg-tg){background:#00c853;color:#000}::highlight(sbg-to){background:#ff9100;color:#000}");
  document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
  const paint = (name, nodes) => { nodes = nodes.filter(Boolean); if (nodes.length) CSS.highlights.set(name, new Highlight(...nodes.map((n) => { const r = new Range(); r.selectNodeContents(n); return r; }))); else CSS.highlights.delete(name); };

  // the "Ganador" block: the nearest ancestor of the outcome button whose text starts with the market title
  function winnerButtons() {
    const out = [];
    for (const b of document.querySelectorAll('[data-testid="fixture-outcome"]')) {
      for (let e = b.parentElement, i = 0; e && i < 8; e = e.parentElement, i++) {
        const first = e.innerText.split("\n").map((s) => s.trim()).filter(Boolean)[0];
        if (/^(Ganador|Winner)$/i.test(first)) { out.push(b); break; }
        if (e.querySelectorAll('[data-testid="fixture-outcome"]').length > 2) break;   // already a block of several markets
      }
    }
    return out;
  }

  function step() {
    ["sbg-ty", "sbg-tg", "sbg-to"].forEach((k) => CSS.highlights.delete(k));
    if (!target || !location.pathname.includes("/sports/tennis/")) return;
    const want = key(target.player);
    const surname = want.split(" ").pop();
    const btns = winnerButtons();
    if (!btns.length) { report("tennis", "Estás en un partido de tenis, pero aún no veo el mercado «Ganador» (¿carga la página?)."); return; }
    const mine = btns.find((b) => key(b.getAttribute("aria-label")) === want) || btns.find((b) => key(b.getAttribute("aria-label")).split(" ").pop() === surname);
    if (!mine) { report("tennis", `En este partido no veo a ${target.player} en «Ganador»: ¿es el partido correcto?`); return; }
    const name = mine.querySelector('[data-testid="outcome-button-name"]');
    const oddsEl = mine.querySelector('[data-testid="fixture-odds"] span');
    const odds = oddsEl ? num(oddsEl.textContent) : null;
    const okOdds = odds && target.fair ? odds >= target.fair : true;
    paint("sbg-ty", [name && textNode(name)]);
    paint(okOdds ? "sbg-tg" : "sbg-to", [oddsEl && textNode(oddsEl)]);
    report(okOdds ? "ready" : "tennis_odds",
      okOdds ? `Todo listo: pulsa «${target.player}» en Ganador (cuota ${odds}${target.odds ? `, recomendada ${target.odds}` : ""}).`
             : `La cuota de ${target.player} bajó a ${odds}: por debajo de ${target.fair.toFixed(2)} ya no hay ventaja sobre el modelo.`);
  }
  let timer;
  const later = () => { clearTimeout(timer); timer = setTimeout(step, 150); };
  try {
    new MutationObserver(later).observe(document.body, { subtree: true, childList: true, characterData: true });
    const setTarget = (t) => { target = t && t.player ? t : null; lastReport = ""; step(); };
    chrome.storage.local.get("tennisTarget", (v) => setTarget(v.tennisTarget));
    chrome.storage.onChanged.addListener((c) => { if (c.tennisTarget) setTarget(c.tennisTarget.newValue); });
  } catch (e) { /* extension reloaded */ }

  try {
    chrome.runtime.onMessage.addListener((msg, sender, send) => {
      if (!msg || msg.type !== "tennis-link") return false;
      findMatch(msg.player, msg.opponent).then((url) => send({ url }), (e) => send({ url: null, error: String(e && e.message || e) }));
      return true;                                   // answer asynchronously
    });
  } catch (e) { /* extension reloaded */ }
})();
