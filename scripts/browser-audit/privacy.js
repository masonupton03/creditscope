// Privacy audit of the portfolio page against a RUNNING personal server (python -m personal serve).
//   node privacy.js http://localhost:8766/ /path/to/screenshot-folder [/tmp/cs-ocr]
// It saves a distinctive ledger through the local API, reads every sensitive value from the REAL view, then proves none of
// them is exposed in the "hide" view: visible text, element attributes, chart data, and OCR of real screenshots (including one
// with a chart tooltip open). It also checks that risk statistics are still shown.
// WARNING: it overwrites the portfolio file of the server it talks to. Use a throwaway CREDITSCOPE_HOME.
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const assert = require('assert');
const [BASE, OUT, OCR] = [process.argv[2], process.argv[3] || '.', process.argv[4] || '/tmp/cs-ocr'];
const SYMS = ['AAPL', 'TSLA', 'KO'], NAMES = ['Apple', 'Tesla', 'Coca'];
const LEDGER = { version: 1, benchmark: 'SPY', baseCurrency: 'USD', transactions: [
  { id: 'a1', date: '2023-02-03', type: 'deposit', amount: 52317.41 },
  { id: 'a2', date: '2023-02-06', type: 'buy', symbol: 'AAPL', shares: 137, price: 131.37, fee: 1.25 },
  { id: 'a3', date: '2023-02-06', type: 'buy', symbol: 'TSLA', shares: 41.5, price: 189.9 },
  { id: 'a4', date: '2023-05-02', type: 'buy', symbol: 'KO', shares: 2841, price: 61.07 },
  { id: 'a5', date: '2024-03-04', type: 'sell', symbol: 'TSLA', shares: 11.25, price: 201.45 }] };

async function save() {
  const r = await fetch(BASE + 'api/portfolio'); const { revision } = await r.json();
  const w = await fetch(BASE + 'api/portfolio', { method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-CreditScope': '1', Origin: BASE.replace(/\/$/, '') },
    body: JSON.stringify({ baseRevision: revision, portfolio: LEDGER }) });
  assert(w.ok, 'could not save the audit ledger: HTTP ' + w.status);
}
const grab = p => p.evaluate(() => {
  const skip = ['class', 'style', 'href', 'src', 'rel', 'type', 'id', 'for', 'role', 'name', 'content'];
  const attrs = [];
  document.querySelectorAll('*').forEach(e => { for (const a of e.attributes) if (skip.indexOf(a.name) < 0) attrs.push(a.name + '=' + a.value); if (e.value && e.tagName !== 'OPTION') attrs.push('value=' + e.value); });
  const charts = [];
  document.querySelectorAll('canvas').forEach(c => { const ch = window.Chart && window.Chart.getChart(c); if (ch) charts.push(JSON.stringify({ labels: ch.data.labels, sets: ch.data.datasets.map(d => ({ label: d.label, data: d.data })) })); });
  return { text: document.body.innerText, attrs: attrs.join('\n'), charts: charts.join('\n'), title: document.title, url: location.href };
});

(async () => {
  await save();
  const b = await chromium.launch({ channel: 'chrome' });
  const p = await (await b.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => m.type() === 'error' && errs.push(m.text()));
  // changing only the address-bar hash makes the page reload itself (by design), so wait for that instead of forcing a second reload
  const open = async view => { await p.goto(BASE + 'portfolio.html#p=ITD&view=' + view, { waitUntil: 'networkidle' }); await p.waitForTimeout(1500); await p.waitForLoadState('networkidle'); await p.waitForTimeout(600); };

  await open('real');
  const real = await grab(p);
  const money = Array.from(new Set(real.text.match(/[−-]?\$[\d,]+(?:\.\d+)?/g) || [])).filter(t => /\d{3}|\.\d\d/.test(t));
  const shareCells = await p.$$eval('#holdBody tr td:nth-child(2)', els => els.map(e => e.textContent.trim()).filter(Boolean));
  const raw = money.map(m => m.replace(/[−\-$,]/g, ''));                           // chart data holds 446742.74, not "$446,742.74"
  const sensitive = [].concat(SYMS, NAMES, money.map(m => m.replace(/^[−-]/, '')), raw, shareCells, ['137', '2,841', '41.5', '30.25']);
  const esc = t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  // numbers match only as whole numbers (so "137" is not "found" inside 100.1374), words match anywhere
  const found = (hay, t) => (/^[$\-−]?[\d,.]+$/.test(t) ? new RegExp('(?<![\\d.,])' + esc(t) + '(?!\\d|[.,]\\d)').test(hay) : hay.includes(t));
  console.log('real view exposes', sensitive.length, 'sensitive tokens, for example:', sensitive.slice(0, 8).join(' | '));
  assert(sensitive.length > 15 && real.text.includes('AAPL'), 'the real view should expose the data, otherwise this test proves nothing');
  await p.screenshot({ path: OUT + '/privacy-real.png', fullPage: true });
  const ocrReal = execFileSync(OCR, [OUT + '/privacy-real.png'], { maxBuffer: 1 << 26 }).toString();
  assert(/AAPL/.test(ocrReal) && /TSLA/.test(ocrReal), 'OCR must be able to read the real screenshot, or the hidden-screenshot check is meaningless');
  console.log('control: OCR reads the real screenshot (' + ocrReal.split('\n').length + ' lines, finds AAPL and TSLA)');

  await open('hide');
  const h = await grab(p);
  const hay = { 'visible text': h.text, 'attributes': h.attrs, 'chart data': h.charts, 'title': h.title, 'address': h.url };
  const leaks = [];
  for (const where of Object.keys(hay)) for (const t of sensitive) if (found(hay[where], t)) leaks.push(where + ': "' + t + '"');
  assert(!/\$\s?\d/.test(h.text), 'a dollar figure is visible');
  assert(!leaks.length, 'LEAKS in the hidden view:\n' + leaks.join('\n'));
  assert(/Holding A/.test(h.text), 'neutral labels should appear');
  assert(await p.isHidden('#txForm') && (await p.$$('#txBody .rm')).length === 0, 'editing must be off while hidden');
  const stats = (await p.textContent('#perfTiles')).replace(/\s+/g, ' ');
  assert(/Volatility\s*[\d.]+%/.test(stats) && /Beta vs SPY\s*[\d.]+/.test(stats) && /Max drawdown/.test(stats), 'risk statistics must still be shown: ' + stats.slice(0, 160));
  console.log('hidden view: visible text, attributes, chart data, title and address are clean; risk statistics shown:', stats.slice(0, 110));

  const box = await p.locator('#chAlloc').boundingBox();
  await p.mouse.move(box.x + box.width / 2 + box.height * 0.3, box.y + box.height / 2); await p.waitForTimeout(400);
  await p.screenshot({ path: OUT + '/privacy-hide.png', fullPage: true });
  const ocr = execFileSync(OCR, [OUT + '/privacy-hide.png'], { maxBuffer: 1 << 26 }).toString();
  const ocrLeaks = sensitive.filter(t => t.length >= 3 && found(ocr, t));
  const dollars = ocr.match(/\$\s?\d[\d,.]*/g) || [];
  console.log('hidden screenshot: OCR read', ocr.split('\n').length, 'lines | sensitive strings found:', JSON.stringify(ocrLeaks), '| dollar figures found:', JSON.stringify(dollars));
  assert(!ocrLeaks.length && !dollars.length, 'the screenshot exposes: ' + ocrLeaks.concat(dollars).join(', '));
  assert(!errs.length, 'console errors: ' + errs);
  console.log('PRIVACY AUDIT PASSED');
  await b.close();
})().catch(e => { console.error('FAILED:', e.message); process.exit(1); });
