// Browser regression for the public pages (static server, simulated data): navigation between pages, loading / error / empty states,
// mobile overflow at several widths, and an axe-core accessibility scan in both themes.
//   node regression.js http://127.0.0.1:8801/        (needs playwright and axe-core; see README.md)
const { chromium } = require('playwright');
const fs = require('fs');
const assert = require('assert');
const BASE = process.argv[2] || 'http://127.0.0.1:8801/';
const axeSource = fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');
const results = []; const fail = [];
const ok = (name, cond, detail) => { results.push((cond ? 'PASS ' : 'FAIL ') + name + (cond || !detail ? '' : ' :: ' + detail)); if (!cond) fail.push(name); };
const PAGES = ['index.html', 'browse.html', 'trends.html', 'explorer.html#AAPL', 'fundamentals.html#DEMA', 'compare.html#s=AAPL,MSFT,TLT&p=1Y&f=DEMA,DEMB', 'portfolio.html', 'platform.html'];

(async () => {
  const b = await chromium.launch({ channel: 'chrome' });
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
    if (scheme === 'light') await p.evaluate(() => { document.documentElement.dataset.theme = 'light'; });
    await p.waitForTimeout(900); await p.evaluate(axeSource);
    const r = await p.evaluate(() => axe.run({ runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa', 'best-practice'] }));
    ok('axe ' + scheme + ' ' + u.split('#')[0], r.violations.length === 0, r.violations.map(v => v.id + '(' + v.nodes.length + ')').join(', ')); await p.close();
  }
  await b.close();
  console.log(results.join('\n')); console.log('\n' + (results.length - fail.length) + '/' + results.length + ' checks passed');
  process.exit(fail.length ? 1 : 0);
})().catch(e => { console.error('ERROR', e.message); process.exit(2); });
