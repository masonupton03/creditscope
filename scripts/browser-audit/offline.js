// Offline check in two phases with the web server stopped in between (a service worker's own requests cannot be faked offline).
//   node offline.js prime  http://127.0.0.1:8801/ <profile-dir>     visit the pages online so the service worker caches them
//   (stop the web server)
//   node offline.js verify http://127.0.0.1:8801/ <profile-dir>     reopen them with no network: they must still open and show data
const chromium = require('./launch');
const [phase, BASE, PROFILE] = process.argv.slice(2);
(async () => {
  const ctx = await chromium.launchPersistentContext(PROFILE, { viewport: { width: 1280, height: 900 } });
  const p = ctx.pages()[0] || await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
  const pages = ['index.html', 'browse.html', 'trends.html'];
  if (phase === 'prime') {
    for (const pg of pages) { await p.goto(BASE + pg, { waitUntil: 'networkidle' }); }
    await p.evaluate(async () => { await navigator.serviceWorker.ready; });
    await p.goto(BASE + 'index.html', { waitUntil: 'networkidle' }); await p.waitForTimeout(1500);
    console.log('primed: service worker', await p.evaluate(async () => (await navigator.serviceWorker.ready).active.state));
  } else {
    let fails = 0;
    for (const pg of pages) {
      let status = 'opened';
      try { await p.goto(BASE + pg, { waitUntil: 'load', timeout: 15000 }); await p.waitForTimeout(1200); } catch (e) { status = 'FAILED to open: ' + e.message.split('\n')[0]; fails++; }
      const text = status === 'opened' ? await p.evaluate(() => document.body.innerText) : '';
      const hasData = /SPY/.test(text) && /QQQ/.test(text); const note = /offline|saved copy|last (copy|data)/i.test(text);
      if (status === 'opened' && !hasData) { fails++; status += ' but WITHOUT data'; }
      console.log((status === 'opened' ? 'PASS ' : 'FAIL ') + pg + ': ' + status + (hasData ? ', shows SPY and QQQ rows' : '') + (note ? ', offline notice shown' : ''));
    }
    console.log('errors:', errs.length ? errs : 'none'); process.exit(fails ? 1 : 0);
  }
  await ctx.close();
})().catch(e => { console.error('ERROR', e.message); process.exit(2); });
