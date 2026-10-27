// Clicking the toolbar icon opens the side panel next to the current tab.
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });

// Bet recorder: bets.js (on the Stake tab) sends one record per bet Stake confirmed. They are queued here and written, one file each,
// to the PRIVATE repo below through GitHub's API with a fine-grained token that can only write that repo (set in the side panel).
const REPO = "elouelyt/the-model-bets";
const get = (k) => new Promise((r) => chrome.storage.local.get(k, (v) => r(v[k])));
const set = (o) => new Promise((r) => chrome.storage.local.set(o, r));
const b64 = (s) => btoa(String.fromCharCode(...new TextEncoder().encode(s)));
let flushing = false;

async function flush() {
  if (flushing) return;
  flushing = true;
  try {
    const token = await get("ghToken");
    let queue = (await get("betQueue")) || [];
    let st = (await get("betStats")) || { sent: 0 };
    if (!token) { await set({ betStats: { ...st, pending: queue.length, error: queue.length ? "Falta el token de GitHub (ajustes del panel)" : "" } }); return; }
    for (const bet of [...queue]) {
      const month = bet.placed_at.slice(0, 7);
      const res = await fetch(`https://api.github.com/repos/${REPO}/contents/bets/${month}/${bet.id}.json`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "Content-Type": "application/json" },
        body: JSON.stringify({ message: `bet ${bet.id}`, content: b64(JSON.stringify(bet, null, 1)) }),
      });
      if (res.ok || res.status === 422) {          // 422 = that file already exists (sent before)
        queue = queue.filter((b) => b.id !== bet.id);
        st = { sent: (st.sent || 0) + 1, last: bet.id, error: "" };
        await set({ betQueue: queue, betStats: { ...st, pending: queue.length } });
      } else {
        await set({ betStats: { ...st, pending: queue.length, error: `GitHub respondió ${res.status}${res.status === 401 || res.status === 403 ? " (revisa el token)" : ""}` } });
        break;
      }
    }
  } catch (e) {
    const st = (await get("betStats")) || {};
    await set({ betStats: { ...st, error: "Sin conexión con GitHub; se reintentará" } });
  } finally {
    flushing = false;
  }
}

chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "bet" && msg.bet) {
    get("betQueue").then((q) => set({ betQueue: [...(q || []), msg.bet] })).then(flush);
  }
  if (msg && msg.type === "flush") flush();
});
chrome.alarms.create("flush", { periodInMinutes: 5 });
chrome.alarms.onAlarm.addListener((a) => { if (a.name === "flush") flush(); });
chrome.runtime.onStartup.addListener(flush);
