// Browser regression for the public pages (static server, simulated data): navigation between pages, loading / error / empty states,
// mobile overflow at several widths, and an axe-core accessibility scan in both themes.
//   node regression.js http://127.0.0.1:8801/        (needs playwright and axe-core; see README.md)
const chromium = require('./launch');
const fs = require('fs');
const assert = require('assert');
const BASE = process.argv[2] || 'http://127.0.0.1:8801/';
const axeSource = fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');
const results = []; const fail = [];
const ok = (name, cond, detail) => { results.push((cond ? 'PASS ' : 'FAIL ') + name + (cond || !detail ? '' : ' :: ' + detail)); if (!cond) fail.push(name); };
const PAGES = ['index.html', 'browse.html', 'trends.html', 'explorer.html#AAPL', 'fundamentals.html#DEMA', 'compare.html#s=AAPL,MSFT,TLT&p=1Y&f=DEMA,DEMB', 'portfolio.html', 'platform.html'];

(async () => {
  const b = await chromium.launch();
  const newPage = async (w, scheme) => { const ctx = await b.newContext({ viewport: { width: w || 1280, height: 900 }, colorScheme: scheme || 'dark', serviceWorkers: 'block' }); /* a service worker would bypass page.route fakes */ const p = await ctx.newPage(); p.errs = []; p.on('pageerror', e => p.errs.push(e.message)); p.on('console', m => m.type() === 'error' && p.errs.push(m.text())); return p; };

  // ---- cross-page navigation: links appear only when the target has data, and explain why not
  {
    const p = await newPage();
    await p.goto(BASE + 'explorer.html#AAPL', { waitUntil: 'networkidle' });
    ok('explorer: links bar present', await p.isVisible('#xlinks'));
    const off = await p.locator('#xlinks .off').first().getAttribute('title');
    ok('explorer: fundamentals link is disabled with a reason for a ticker with no filings', /No SEC financial statements for AAPL/.test(off || ''), off);
    await p.goto(BASE + 'fundamentals.html#DEMA', { waitUntil: 'networkidle' });
    const off2 = await p.locator('#xlinks .off').first().getAttribute('title');
    ok('fundamentals: price link is disabled with a reason for a fictional company', /No price history for DEMA/.test(off2 || ''), off2);
    ok('fundamentals: simulated banner and company shown', await p.isVisible('#synthBanner') && /DEMA/.test(await p.textContent('#detail')));
    ok('fundamentals: no console errors', p.errs.length === 0, p.errs.join('|'));
    await p.close();
  }
  // a ticker present in both data sets: links enabled and they round-trip (the SEC index is faked here for this test only)
  {
    const p = await newPage();
    const demo = JSON.parse(fs.readFileSync(require.resolve('./../../explorer/sec-sample/company/DEMA.json'), 'utf8'));
    await p.route('**/explorer/sec/index.json', r => r.fulfill({ json: { meta: { synthetic: true }, entries: [{ s: 'AAPL', n: 'Linked Test Co', t: 'S', x: '' }] } }));
    await p.route('**/explorer/sec/company/AAPL.json', r => r.fulfill({ json: Object.assign({}, demo, { ticker: 'AAPL', name: 'Linked Test Co' }) }));
    await p.goto(BASE + 'explorer.html#AAPL', { waitUntil: 'networkidle' });
    await p.click('#xlinks a:has-text("Fundamentals")'); await p.waitForLoadState('networkidle');
    ok('round trip: explorer to fundamentals keeps the ticker', /fundamentals\.html#AAPL/.test(p.url()) && /AAPL/.test(await p.textContent('#detail h2')));
    await p.click('#xlinks a:has-text("Price and risk")'); await p.waitForLoadState('networkidle');
    ok('round trip: fundamentals to explorer keeps the ticker', /explorer\.html#AAPL/.test(p.url()) && /AAPL/.test(await p.textContent('#detail h2')));
    await p.click('#xlinks a:has-text("Compare prices")'); await p.waitForLoadState('networkidle');
    ok('compare opens with the ticker and a reference', /compare\.html#s=AAPL,SPY/.test(p.url()) && (await p.locator('#chosen li').count()) === 2);
    await p.close();
  }
  // ---- theme: light by default (even on a dark-mode computer), dark on request, remembered across pages
  {
    const ctx = await b.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: 'dark', serviceWorkers: 'block' });
    const p = await ctx.newPage(); p.errs = []; p.on('pageerror', e => p.errs.push(e.message));
    await p.goto(BASE + 'index.html', { waitUntil: 'networkidle' });
    const theme = () => p.evaluate(() => document.documentElement.dataset.theme);
    const stored = () => p.evaluate(() => localStorage.getItem('creditscope.theme'));
    ok('theme: a first visit is light even when the OS prefers dark', (await theme()) === 'light' && (await stored()) === null, await theme() + ' / ' + await stored());
    await p.click('#themeBtn'); ok('theme: the toggle switches to dark and remembers it', (await theme()) === 'dark' && (await stored()) === 'dark');
    for (const pg of ['browse.html', 'trends.html', 'explorer.html', 'fundamentals.html', 'compare.html', 'portfolio.html', 'platform.html']) {
      await p.goto(BASE + pg, { waitUntil: 'domcontentloaded' });
      const early = await theme(); ok('theme: dark is already applied when ' + pg + ' starts (no flash)', early === 'dark', early);
    }
    await p.goto(BASE + 'index.html', { waitUntil: 'networkidle' }); await p.click('#themeBtn');
    await p.goto(BASE + 'browse.html', { waitUntil: 'domcontentloaded' }); ok('theme: switching back to light is remembered too', (await theme()) === 'light' && (await stored()) === 'light');
    ok('theme: the toggle label matches the theme', /dark/i.test(await p.getAttribute('#themeBtn', 'aria-label') || ''));
    await ctx.close();
    const blocked = await b.newContext({ viewport: { width: 1280, height: 900 }, serviceWorkers: 'block' }); const q = await blocked.newPage(); const errs = [];
    q.on('pageerror', e => errs.push(e.message)); await q.addInitScript(() => { Object.defineProperty(window, 'localStorage', { get() { throw new Error('storage blocked'); } }); });
    await q.goto(BASE + 'index.html', { waitUntil: 'networkidle' }); await q.click('#themeBtn');
    ok('theme: with storage blocked the page still works and the toggle still switches', errs.length === 0 && (await q.evaluate(() => document.documentElement.dataset.theme)) === 'dark', errs.join('|')); await blocked.close();
  }
  // ---- loading, error and empty states
  {
    const p = await newPage();
    await p.route('**/explorer/sec-sample/company/DEMB.json', async r => { await new Promise(x => setTimeout(x, 1500)); r.continue(); });
    await p.goto(BASE + 'fundamentals.html', { waitUntil: 'networkidle' });
    await p.evaluate(() => { location.hash = 'DEMB'; });
    await p.waitForSelector('.inline-loading', { timeout: 3000 }).then(() => ok('loading indicator is shown while a company loads', true), () => ok('loading indicator is shown while a company loads', false));
    await p.waitForSelector('.fd-table', { timeout: 8000 }); ok('company appears after the delay', true);
    await p.unroute('**/explorer/sec-sample/company/DEMB.json');
    await p.route('**/explorer/sec-sample/company/DEMC.json', r => r.abort());
    await p.evaluate(() => { location.hash = 'DEMC'; });
    await p.waitForSelector('[data-retry]', { timeout: 6000 });
    ok('error state names the problem and offers Try again', /Could not load DEMC/.test(await p.textContent('#detail')));
    await p.unroute('**/explorer/sec-sample/company/DEMC.json'); await p.click('[data-retry]'); await p.waitForSelector('.fd-table', { timeout: 8000 });
    ok('Try again recovers', true);
    await p.evaluate(() => { location.hash = 'ZZZZ'; }); await p.waitForTimeout(500);
    ok('empty state for an unknown ticker explains the data set', /No fundamentals for ZZZZ/.test(await p.textContent('#detail')) && /fictional/.test(await p.textContent('#detail')));
    await p.close();
  }
  {
    const p = await newPage();
    await p.goto(BASE + 'compare.html#s=ZZZZ,QQQ,AAPL&p=1Y', { waitUntil: 'networkidle' });
    ok('compare ignores unknown tickers in the address', (await p.locator('#chosen li').count()) === 2 && p.errs.length === 0, p.errs.join('|'));
    ok('compare shows prices-through freshness', /prices through/.test(await p.textContent('#pxCap')));
    await p.close();
  }
  // ---- Fundamentals table on a phone: latest six years by default, all years on request, newest year always visible; charts paint
  {
    const p = await newPage(390);
    await p.goto(BASE + 'fundamentals.html#DEMA', { waitUntil: 'networkidle' }); await p.waitForSelector('.fd-table');
    const heads = () => p.$$eval('.fd-table thead th.r', t => t.map(x => ({ y: x.textContent.slice(0, 6), shown: !!(x.offsetWidth || x.offsetHeight) })));
    let h = await heads(); const total = h.length, shown = h.filter(x => x.shown).length;
    ok('fundamentals phone: the data holds more than six years and six are shown by default', total > 6 && shown === 6, total + ' in the table, ' + shown + ' shown');
    ok('fundamentals phone: the newest year is the last visible column', h[h.length - 1].shown && /FY/.test(h[h.length - 1].y));
        await p.click('#fdAllYears'); h = await heads();
    ok('fundamentals phone: "Show all" reveals every year and reports its state', h.every(x => x.shown) && (await p.getAttribute('#fdAllYears', 'aria-expanded')) === 'true');
    await p.click('#fdAllYears'); h = await heads(); ok('fundamentals phone: the button collapses back to six', h.filter(x => x.shown).length === 6);
    await p.close();
    const d = await newPage(1280);
    await d.goto(BASE + 'fundamentals.html#DEMA', { waitUntil: 'networkidle' }); await d.waitForSelector('.fd-table');
    ok('fundamentals desktop: every year is shown and the toggle is hidden', (await d.$$eval('.fd-table thead th.r', t => t.every(x => x.offsetWidth > 0))) && !(await d.isVisible('#fdAllYears')));
    await d.waitForTimeout(600);
    const painted = await d.evaluate(() => Array.from(document.querySelectorAll('canvas')).map(c => { const g = c.getContext('2d'); const a = g.getImageData(0, 0, c.width, c.height).data; for (let i = 3; i < a.length; i += 4) if (a[i]) return true; return false; }));
    ok('charts paint: every canvas on fundamentals has drawn pixels', painted.length >= 4 && painted.every(Boolean), painted.join(','));
    await d.goto(BASE + 'explorer.html#SPY', { waitUntil: 'networkidle' }); await d.waitForTimeout(800);
    const painted2 = await d.evaluate(() => Array.from(document.querySelectorAll('canvas')).map(c => { const g = c.getContext('2d'); const a = g.getImageData(0, 0, c.width, c.height).data; for (let i = 3; i < a.length; i += 4) if (a[i]) return true; return false; }));
    ok('charts paint: every canvas on explorer has drawn pixels', painted2.length >= 1 && painted2.every(Boolean), painted2.join(','));
    await d.close();
  }
  // ---- a bank, a series that stopped being reported, and a cash definition change (faked from a simulated company; real files carry the same fields)
  {
    const p = await newPage();
    const demo = JSON.parse(fs.readFileSync(require.resolve('./../../explorer/sec-sample/company/DEMA.json'), 'utf8'));
    const bank = JSON.parse(JSON.stringify(demo)); bank.ticker = 'DEMA'; bank.name = 'Demo Bank Corp';
    ['costOfRevenue', 'grossProfit', 'operatingIncome', 'capex'].forEach(k => delete bank.metrics[k]);
    const dm = bank.metrics.debt; delete bank.metrics.debt;
    bank.profile = 'bank'; bank.profileReason = 'reports Deposits and has no cost of revenue or operating income';
    const pts = bank.metrics.cash.points; const n = pts.length;
    pts.forEach((q, i) => { q.tag = i < n - 3 ? 'CashAndDueFromBanks' : 'CashAndCashEquivalentsAtCarryingValue'; });
    bank.coverage.definitions = { cash: [{ meaning: 'cash and due from banks (a narrower item that banks report)', tag: 'CashAndDueFromBanks', fromFy: pts[0].fy, toFy: pts[n - 4].fy }, { meaning: 'cash and cash equivalents', tag: 'CashAndCashEquivalentsAtCarryingValue', fromFy: pts[n - 3].fy, toFy: pts[n - 1].fy }] };
    bank.coverage.stale = { debt: { label: 'Debt', lastFy: 2013, tag: 'LongTermDebt', val: 267889e6, unit: 'USD', filed: '2014-02-28', accn: '0000000000-14-000001', companyLatestFy: pts[n - 1].fy } };
    await p.route('**/explorer/sec-sample/company/DEMA.json', r => r.fulfill({ json: bank }));
    await p.goto(BASE + 'fundamentals.html#DEMA', { waitUntil: 'networkidle' }); await p.waitForSelector('.fd-table');
    const t = await p.textContent('#detail');
    ok('bank: analysed-as-a-bank notice and net-revenue wording', /Analysed as a bank/.test(t) && /Net revenue/.test(t));
    ok('bank: gross profit, operating margin, free cash flow, debt and net debt are not shown', !/Gross profit/.test(await p.textContent('.fd-table')) && !/Free cash flow|Operating margin|Net debt|Debt to equity/.test(await p.textContent('.fd-table')) && /Not shown for a bank/.test(t));
    ok('stale series: a warning says the debt figure is not shown and it is absent from the figures', /Debt is not shown/.test(t) && !/>Debt</.test(await p.innerHTML('.fd-table')) && /last reported for FY2013/.test(await p.textContent('#audit')));
    ok('cash definition change: dagger in the table, footnote names every definition', (await p.locator('.fd-table sup').count()) > 0 && /Cash is not one continuous series/.test(t) && /cash and due from banks/.test(t));
    ok('bank page: no console errors', p.errs.length === 0, p.errs.join('|'));
    await p.close();
  }
  // ---- mobile overflow at several widths on every page
  for (const w of [320, 360, 390, 768]) {
    const p = await newPage(w);
    for (const u of PAGES) {
      await p.goto(BASE + u, { waitUntil: 'networkidle' }); await p.waitForTimeout(500);
      const o = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      ok('no horizontal overflow ' + w + 'px ' + u.split('#')[0], o <= 0, 'overflow ' + o + 'px');
    }
    ok('no console errors at ' + w + 'px', p.errs.length === 0, p.errs.join('|')); await p.close();
  }
  // ---- accessibility (axe: WCAG 2.1 A/AA and best practices), both themes
  for (const scheme of ['dark', 'light']) for (const u of PAGES) {
    const p = await newPage(1280, scheme);
    await p.goto(BASE + u, { waitUntil: 'networkidle' });
    await p.evaluate(t => { document.documentElement.dataset.theme = t; }, scheme);                 // both themes are always checked explicitly
    await p.waitForTimeout(900); await p.evaluate(axeSource);
    const r = await p.evaluate(() => axe.run({ runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa', 'best-practice'] }));
    ok('axe ' + scheme + ' ' + u.split('#')[0], r.violations.length === 0, r.violations.map(v => v.id + '(' + v.nodes.length + ')').join(', ')); await p.close();
  }
  await b.close();
  console.log(results.join('\n')); console.log('\n' + (results.length - fail.length) + '/' + results.length + ' checks passed');
  process.exit(fail.length ? 1 : 0);
})().catch(e => { console.error('ERROR', e.message); process.exit(2); });
