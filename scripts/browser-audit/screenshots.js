// Full-page screenshots of the five main pages at desktop and phone width in both themes (JPEG, simulated data only).
//   node screenshots.js http://127.0.0.1:8801/ ../../docs/visual-review
// The theme is chosen the way a visitor chooses it (the saved preference), so this also exercises the persistence path.
const { chromium } = require('playwright');
const fs = require('fs');
const [BASE, OUT] = [process.argv[2] || 'http://127.0.0.1:8801/', process.argv[3] || '.'];
const PAGES = { today: 'index.html', explorer: 'explorer.html#MSFT&p=1Y', fundamentals: 'fundamentals.html#DEMA', compare: 'compare.html#s=AAPL,MSFT,TLT&p=1Y&f=DEMA,DEMB', portfolio: 'portfolio.html' };
const SIZES = { desktop: { width: 1280, height: 900 }, mobile: { width: 390, height: 844 } };
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch({ channel: 'chrome' });
  for (const theme of ['light', 'dark']) for (const [size, vp] of Object.entries(SIZES)) {
    const ctx = await b.newContext({ viewport: vp, serviceWorkers: 'block', deviceScaleFactor: 1 });
    await ctx.addInitScript(t => { try { localStorage.setItem('creditscope.theme', t); } catch (e) { /* ignore */ } }, theme);
    for (const [name, url] of Object.entries(PAGES)) {
      const p = await ctx.newPage(); await p.goto(BASE + url, { waitUntil: 'networkidle' }); await p.waitForTimeout(900);
      const actual = await p.evaluate(() => document.documentElement.dataset.theme); if (actual !== theme) throw new Error(name + ': expected ' + theme + ' got ' + actual);
      await p.screenshot({ path: `${OUT}/${name}-${size}-${theme}.jpg`, fullPage: true, type: 'jpeg', quality: 80 }); await p.close();
    }
    await ctx.close();
  }
  await b.close(); console.log('wrote', fs.readdirSync(OUT).filter(f => f.endsWith('.jpg')).length, 'screenshots to', OUT);
})().catch(e => { console.error('ERROR', e.message); process.exit(1); });
