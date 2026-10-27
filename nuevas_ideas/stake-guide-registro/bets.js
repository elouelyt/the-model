// Stake Bet Guide - bet recorder. READ-ONLY: it reads the visible betslip (selections, odds, amount) and, when Stake confirms a bet
// was placed, hands one record to the extension's background script. It never clicks, types or changes the page and adds no
// elements to it; the only thing it listens to is the user's own click on Stake's "Apostar" button.
(() => {
  const clean = (s) => String(s || "").replace(/\s+/g, " ").trim();
  const num = (s) => { const v = parseFloat(String(s).replace(/\s/g, "").replace(",", ".")); return Number.isFinite(v) ? v : null; };
  const all = (id, root = document) => [...root.querySelectorAll(`[data-testid="${id}"]`)];
  const MARKET = /^(Sobre|Debajo|Over|Under)\s+([\d.,]+)\s+(.+)$/i;
  const PLACE = /^(apostar|realizar apuesta|colocar apuesta|place bet|confirmar apuesta)/i;
  const SUCCESS = /(apuesta|bet)\s+(realizada|colocada|aceptada|exitosa|placed|accepted|successful)|apuesta\s+hecha|bet\s+confirmed/i;
  const FAILURE = /saldo insuficiente|insufficient|cuotas? (han )?cambiado|odds (have )?changed|no se pudo|error|rechazad|rejected/i;

  // one selection of the slip: lines are [game, "Sobre 7.5 Puntos", player, odds]
  function readLeg(el) {
    const lines = el.innerText.split("\n").map(clean).filter(Boolean);
    const m = lines.map((l) => MARKET.exec(l)).find(Boolean);
    if (!m) return null;
    const i = lines.findIndex((l) => MARKET.test(l));
    const odds = [...lines].reverse().map(num).find((v) => v !== null && v > 1);
    return { game: lines[i - 1] || "", side: /^(sobre|over)$/i.test(m[1]) ? "Over" : "Under", line: num(m[2]), stat: clean(m[3]), player: lines[i + 1] || "", odds };
  }

  function amountOf(input) { const v = num(input && input.value); return v && v > 0 ? v : 0; }

  function snapshot() {
    const multi = all("betslip-multi-bet")[0];
    const out = { at: Date.now(), multi: null, singles: [] };
    if (multi) {
      const legs = all("betslip-bet", multi).map(readLeg).filter(Boolean);
      const odds = num((all("multi-bet-total-odds", multi)[0] || {}).innerText);
      const input = all("input-bet-amount", multi)[0];
      const cur = clean((multi.querySelector(".before-icon") || {}).textContent);
      if (legs.length) out.multi = { legs, odds, amount: amountOf(input), currency: cur };
    }
    for (const b of all("betslip-bet")) {
      if (multi && multi.contains(b)) continue;
      const leg = readLeg(b);
      const input = b.querySelector('[data-testid="input-bet-amount"]') || (b.nextElementSibling && b.nextElementSibling.querySelector('[data-testid="input-bet-amount"]'));
      if (leg) out.singles.push({ leg, amount: amountOf(input) });
    }
    return out;
  }

  const sig = (legs) => legs.map((l) => `${l.player}|${l.stat}|${l.side}|${l.line}`).sort().join(";");
  const sent = new Set();
  let watching = false;

  function report(code, detail) { try { chrome.storage.local.set({ betState: { code, detail, at: Date.now() } }); } catch (e) { /* extension reloaded */ } }

  function emit(kind, legs, odds, amount, currency) {
    const key = kind + "|" + sig(legs) + "|" + amount;
    const slot = Math.floor(Date.now() / 60000);
    if (sent.has(key + "|" + slot) || sent.has(key + "|" + (slot - 1))) return;
    sent.add(key + "|" + slot);
    const bet = { id: `${new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14)}-${Math.random().toString(36).slice(2, 7)}`, placed_at: new Date().toISOString(),
                  kind, odds, amount, currency, legs, page: location.pathname };
    try { chrome.runtime.sendMessage({ type: "bet", bet }); } catch (e) { /* extension reloaded */ }
    report("saved", `Apuesta registrada: ${kind === "multi" ? "combinada de " + legs.length : "simple"} @ ${odds}.`);
  }

  // after the click: wait for Stake's confirmation (text) or for the slip to empty, but never when an error is shown
  function watch(snap) {
    if (watching) return;
    watching = true;
    const t0 = Date.now();
    const finish = (ok) => {
      watching = false;
      if (!ok) { report("unconfirmed", "Pulsaste Apostar pero no vi la confirmación de Stake; no la he registrado."); return; }
      if (snap.multi && snap.multi.amount) emit("multi", snap.multi.legs, snap.multi.odds, snap.multi.amount, snap.multi.currency);
      for (const s of snap.singles) if (s.amount) emit("single", [s.leg], s.leg.odds, s.amount, snap.multi ? snap.multi.currency : "");
    };
    const tick = () => {
      const text = document.body.innerText;
      const now = snapshot();
      const slipLeft = (now.multi ? now.multi.legs.length : 0) + now.singles.length;
      const slipBefore = (snap.multi ? snap.multi.legs.length : 0) + snap.singles.length;
      if (SUCCESS.test(text) && !(FAILURE.test(text) && slipLeft >= slipBefore)) return finish(true);
      if (slipBefore && slipLeft === 0) return finish(true);                       // Stake emptied the slip after accepting the bet
      if (Date.now() - t0 > 25000) return finish(false);
      setTimeout(tick, 500);
    };
    setTimeout(tick, 800);
  }

  document.addEventListener("click", (ev) => {
    const btn = ev.target && ev.target.closest && ev.target.closest("button");
    if (!btn) return;
    const label = clean(btn.innerText);
    if (!PLACE.test(label)) return;
    const snap = snapshot();
    const hasAmount = (snap.multi && snap.multi.amount) || snap.singles.some((s) => s.amount);
    if (!hasAmount) return;
    watch(snap);
  }, true);
})();
