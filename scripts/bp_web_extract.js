((needed) => (async () => {
  // Player page: one `.odds-offer` row per market, loaded 5 at a time while scrolling. Scroll only until every wanted market is present.
  const labels = () => [...document.querySelectorAll('.odds-offer .odds-offer-label')].map(l => l.innerText.split('\n')[0].trim().toLowerCase());
  const have = () => needed.every(n => labels().some(l => l.startsWith(n)));
  const t0 = Date.now();
  let stagnant = 0;
  while (!have() && Date.now() - t0 < 25000 && stagnant < 4) {
    const before = document.querySelectorAll('.odds-offer').length;
    window.scrollTo(0, document.body.scrollHeight);
    let grew = false;
    for (let k = 0; k < 20 && !grew; k++) {
      await new Promise(r => setTimeout(r, 150));
      grew = document.querySelectorAll('.odds-offer').length > before;
    }
    stagnant = grew ? 0 : stagnant + 1;
  }
  const books = [...document.querySelectorAll('img[alt^="Logo for"]')].map(i => i.alt.replace('Logo for ', '').trim());
  const seen = []; for (const b of books) if (!seen.includes(b)) seen.push(b);
  const price = (s) => { s = s.trim().toUpperCase(); if (s === 'EVEN') return 100; const v = parseInt(s.replace('+', ''), 10); return isNaN(v) ? null : v; };
  const re = /O\s*([\d.]+)\s*\(\s*([+-]?\d+|EVEN)\s*\)\s*U\s*([\d.]+)\s*\(\s*([+-]?\d+|EVEN)\s*\)/i;
  const rows = [];
  for (const row of document.querySelectorAll('.odds-offer')) {
    const lab = row.querySelector('.odds-offer-label');
    const items = [...row.querySelectorAll(':scope > .odds-offer__item')].slice(1);   // drop the label column
    const cells = items.map(it => {
      const m = (it.innerText || '').replace(/\s+/g, ' ').trim().match(re);
      return m ? { line: parseFloat(m[1]), over: price(m[2]), under_line: parseFloat(m[3]), under: price(m[4]) } : null;
    });
    rows.push({ label: lab ? lab.innerText.split('\n')[0].trim() : '', cells });
  }
  return JSON.stringify({ books: seen, rows, title: document.title });
})())
