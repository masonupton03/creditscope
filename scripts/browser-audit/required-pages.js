// Functional check of the three assignment pages (Today, Browse, Trends) in a real browser, plus the installability prerequisites.
//   node required-pages.js http://127.0.0.1:8801/
// Reads data/history.csv and data/status.json from the same server and compares what the pages show with the files.
const { chromium } = require('playwright');
const assert = require('assert');
const BASE = process.argv[2] || 'http://127.0.0.1:8801/';
const out = []; const bad = [];
const ok = (n, c, d) => { out.push((c ? 'PASS ' : 'FAIL ') + n + (c || !d ? '' : ' :: ' + d)); if (!c) bad.push(n); };

(async () => {
  const csv = await (await fetch(BASE + 'data/history.csv')).text();
  const status = await (await fetch(BASE + 'data/status.json')).json();
  const parseCsv = text => { const out = []; let row = [], f = '', q = false;
    for (let i = 0; i < text.length; i++) { const c = text[i];
      if (q) { if (c === '"' && text[i + 1] === '"') { f += '"'; i++; } else if (c === '"') q = false; else f += c; }
      else if (c === '"') q = true; else if (c === ',') { row.push(f); f = ''; } else if (c === '\n') { row.push(f); out.push(row); row = []; f = ''; } else if (c !== '\r') f += c; }
    if (f || row.length) { row.push(f); out.push(row); } return out; };
  const table = parseCsv(csv); const header = table[0]; const rows = table.slice(1);
  const dates = Array.from(new Set(rows.map(r => r[0]))).sort(); const lastDate = dates[dates.length - 1];
  const latest = rows.filter(r => r[0] === lastDate);

  const b = await chromium.launch({ channel: 'chrome' });
  const ctx = await b.newContext({ viewport: { width: 1280, height: 900 } });
  const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => m.type() === 'error' && errs.push(m.text()));

  // ---- Today
  await p.goto(BASE + 'index.html', { waitUntil: 'networkidle' });
  const today = await p.evaluate(() => document.body.innerText);
  ok('Today: shows every source status (' + status.sources.length + ')', status.sources.every(s => today.includes(s.name.replace('nasdaq-', '')) || today.includes(s.name)));
  ok('Today: shows items count and days collected from status.json', today.includes(String(status.items)) && today.includes(String(status.days_with_success)));
  ok('Today: lists the latest values of every item', latest.every(r => today.includes(r[1])), 'missing some of ' + latest.map(r => r[1]).join(','));
  ok('Today: has a biggest-moves section', /moves?/i.test(today));
  ok('Today: no console errors', errs.length === 0, errs.join('|'));

  // ---- Browse: search, filters (2 columns), sorts, star + persistence
  await p.goto(BASE + 'browse.html', { waitUntil: 'networkidle' });
  const rowCount = async () => p.locator('#tbl tbody tr').count();
  ok('Browse: one row per item', (await rowCount()) === latest.length, (await rowCount()) + ' vs ' + latest.length);
  await p.fill('#q', 'treasury'); await p.waitForTimeout(250);
  const n1 = await rowCount(); ok('Browse: search narrows the list', n1 > 0 && n1 < latest.length, String(n1));
  await p.fill('#q', ''); await p.waitForTimeout(150);
  const classes = await p.$$eval('#fClass option', o => o.map(x => x.value).filter(Boolean)); await p.selectOption('#fClass', classes[0]); await p.waitForTimeout(200);
  const n2 = await rowCount(); ok('Browse: asset-class filter works', n2 > 0 && n2 < latest.length, classes[0] + ' ' + n2);
  const cats = await p.$$eval('#fCat option', o => o.map(x => x.value).filter(Boolean)); await p.selectOption('#fCat', cats[0]); await p.waitForTimeout(200);
  ok('Browse: category filter works (second column)', (await rowCount()) <= n2);
  await p.click('#reset'); await p.waitForTimeout(200);
  const keys = await p.$$eval('#sortKey option', o => o.map(x => x.value)); ok('Browse: sort offers the numeric columns', keys.length >= 4, keys.join(','));
  const firstSym = async () => (await p.locator('#tbl tbody tr').first().getAttribute('data-id'));
  const orderFor = async (k, dir) => { await p.selectOption('#sortKey', k); await p.click(dir === 'asc' ? '#ascBtn' : '#descBtn'); await p.waitForTimeout(200); return p.$$eval('#tbl tbody tr', r => r.map(x => x.dataset.id)); };
  let allSorted = true; const detail = [];
  const valueOf = (id, k) => { const r = latest.find(x => x[1] === id); const v = r && r[header.indexOf(k)]; return v === '' || v === undefined ? null : Number(v); };
  const monotone = (ids, k, dir) => { const vs = ids.map(i => valueOf(i, k)).filter(v => v !== null); return vs.every((v, i) => i === 0 || (dir === 'asc' ? vs[i - 1] <= v : vs[i - 1] >= v)); };
  for (const k of keys.filter(k => header.includes(k) && latest.some(r => r[header.indexOf(k)] !== '' && !isNaN(Number(r[header.indexOf(k)]))))) {
    const asc = await orderFor(k, 'asc'), desc = await orderFor(k, 'desc'); const good = monotone(asc, k, 'asc') && monotone(desc, k, 'desc'); allSorted = allSorted && good; detail.push(k + (good ? ' ok' : ' WRONG'));
  }
  allSorted = allSorted && detail.length >= 4;
  ok('Browse: every numeric column sorts up and down (order checked against history.csv): ' + detail.join(', '), allSorted);
  const target = await firstSym();
  await p.locator('#tbl tbody tr').first().locator('button, .star').first().click(); await p.waitForTimeout(200);
  await p.reload({ waitUntil: 'networkidle' });
  const starred = await p.evaluate(() => JSON.stringify(Object.assign({}, window.localStorage)));
  ok('Browse: a starred item is stored in the browser and survives a reload', /creditscope/.test(starred) && starred.includes(target), starred.slice(0, 160));
  await p.check('#fStar'); await p.waitForTimeout(200); ok('Browse: shortlist filter shows the starred item', (await rowCount()) === 1);

  // ---- Trends: more than four findings sections, charts, numbers from the history file
  await p.goto(BASE + 'trends.html', { waitUntil: 'networkidle' }); await p.waitForTimeout(500);
  const sections = await p.locator('#findings h2, #findings h3').count(); ok('Trends: at least four finding sections', sections >= 4, String(sections));
  const charts = await p.locator('canvas').count(); ok('Trends: a chart for the explorer and one per finding', charts >= 5, String(charts));
  const tr = await p.evaluate(() => document.body.innerText);
  ok('Trends: shows the day count and row count that match history.csv', tr.includes(String(dates.length)) && tr.includes(String(rows.length)), 'days ' + dates.length + ' rows ' + rows.length);
  const price = await p.$eval('#exValue', s => s.options.length); ok('Trends: a control picks the value and the items shown', price >= 2 && (await p.locator('#exPick input, #exPick button').count()) >= 10);
  ok('Trends: no console errors', errs.length === 0, errs.join('|'));

  // ---- shared navigation, manifest, service worker
  const navs = []; for (const pg of ['index.html', 'browse.html', 'trends.html']) { await p.goto(BASE + pg, { waitUntil: 'domcontentloaded' }); navs.push(await p.$eval('nav.nav', n => Array.from(n.querySelectorAll('a.link')).map(a => a.getAttribute('href')).join(','))); }
  ok('the three pages share one navigation bar', navs[0] === navs[1] && navs[1] === navs[2], navs.join(' | '));
  const man = await (await fetch(BASE + 'manifest.webmanifest')).json();
  ok('manifest: name, start_url, standalone display, 192 and 512 icons', !!man.name && !!man.start_url && /standalone|minimal-ui/.test(man.display) && man.icons.some(i => /192/.test(i.sizes)) && man.icons.some(i => /512/.test(i.sizes)));
  await p.goto(BASE + 'index.html', { waitUntil: 'networkidle' });
  const sw = await p.evaluate(async () => { const r = await navigator.serviceWorker.ready; return { scope: r.scope, state: r.active && r.active.state }; });
  ok('service worker is active', sw.state === 'activated', JSON.stringify(sw));
  const cached = await p.evaluate(async () => (await Promise.all((await caches.keys()).map(async k => (await (await caches.open(k)).keys()).map(r => new URL(r.url).pathname)))).flat());
  ok('offline cache holds the three pages and both data files after one visit', ['index.html', 'browse.html', 'trends.html', 'data/history.csv', 'data/status.json'].every(f => cached.some(c => c.endsWith(f))), cached.length + ' entries');
  await b.close();
  console.log(out.join('\n')); console.log('\n' + (out.length - bad.length) + '/' + out.length + ' checks passed'); process.exit(bad.length ? 1 : 0);
})().catch(e => { console.error('ERROR', e.message); process.exit(2); });
