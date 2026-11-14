/* Stock Explorer page: search, charts, metrics, SPY comparison and a saved watchlist.
 * All calculations come from finance.js (verified against an independent Python implementation). */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const E = CS.esc;
  const ROOT = 'explorer/sample/';                 // data root: the simulated sample set (real data is not connected)
  const BENCH = 'SPY';
  const PERIODS = Finance.PERIODS;
  const state = { sym: null, period: '1Y', compare: true, mode: 'growth' };
  let index = [], searchIdx = [], meta = {}, watchlist = [];
  const cache = new Map(); const charts = {};
  // localStorage can throw (private mode, blocked storage): fall back to an inert store
  const storage = (() => { try { return window.localStorage; } catch (e) { return { getItem() { return null; }, setItem() { throw new Error('no storage'); } }; } })();

  /* ---------- data ---------- */
  async function getJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(url + ' returned HTTP ' + res.status);
    return res.json();
  }
  function loadSeries(sym) {
    if (!cache.has(sym)) cache.set(sym, getJSON(ROOT + 'series/' + encodeURIComponent(sym) + '.json').catch(e => { cache.delete(sym); throw e; }));
    return cache.get(sym);
  }
  const entry = sym => index.find(e => e.s === sym);

  /* ---------- formatting ---------- */
  const pct = (v, d) => (v == null ? '—' : CS.pct(v * 100, d));
  const plain = (v, d) => (v == null ? '—' : (v < 0 && Math.round(Math.abs(v) * 1000) > 0 ? '−' : '') + CS.num(Math.abs(v) * 100, d == null ? 1 : d) + '%');
  const dir = v => CS.dir(v == null ? null : v);
  const WARN = {
    NO_DIVIDEND_DATA: 'Dividend history is not available for this security, so every return here is a <b>price return</b> and excludes dividends. It will understate what a holder of a dividend payer actually earned.',
    COMPARE_PRICE_BASIS: 'The SPY comparison uses <b>price return for both</b>, because dividend data is missing for one of them. Mixing a total return with a price return would be misleading.',
  };

  /* ---------- search ---------- */
  let active = -1, shown = [];
  function renderResults(list, query) {
    const ul = $('results');
    shown = list; active = list.length ? 0 : -1;
    if (!query.trim()) { ul.hidden = true; $('q').setAttribute('aria-expanded', 'false'); return; }
    ul.innerHTML = list.length ? list.map((e, i) => '<li role="option" id="opt' + i + '" data-sym="' + E(e.s) + '" aria-selected="' + (i === 0) + '"><span class="tk">' + E(e.s) + '</span><span class="nm">' + E(e.n) + '</span><span class="chip">' + (e.t === 'E' ? 'ETF' : 'Stock') + '</span></li>').join('')
      : '<li class="none" role="option" aria-disabled="true">No match among the ' + index.length + ' securities in this sample. Real symbol coverage needs a licensed data source.</li>';
    ul.hidden = false; $('q').setAttribute('aria-expanded', 'true');
  }
  function highlight(i) {
    document.querySelectorAll('#results li[role=option]').forEach((li, k) => li.setAttribute('aria-selected', String(k === i)));
    const li = $('opt' + i); if (li) { li.scrollIntoView({ block: 'nearest' }); $('q').setAttribute('aria-activedescendant', 'opt' + i); }
  }
  function closeResults() { $('results').hidden = true; $('q').setAttribute('aria-expanded', 'false'); }
  function bindSearch() {
    const q = $('q');
    q.addEventListener('input', () => renderResults(ExplorerSearch.search(searchIdx, q.value, 8), q.value));
    q.addEventListener('focus', () => { if (q.value.trim()) renderResults(ExplorerSearch.search(searchIdx, q.value, 8), q.value); });
    q.addEventListener('keydown', e => {
      if (e.key === 'ArrowDown' && shown.length) { e.preventDefault(); active = (active + 1) % shown.length; highlight(active); }
      else if (e.key === 'ArrowUp' && shown.length) { e.preventDefault(); active = (active - 1 + shown.length) % shown.length; highlight(active); }
      else if (e.key === 'Enter') { e.preventDefault(); if (shown[active]) choose(shown[active].s); else if (shown[0]) choose(shown[0].s); }
      else if (e.key === 'Escape') { closeResults(); }
    });
    $('results').addEventListener('mousedown', e => { const li = e.target.closest('li[data-sym]'); if (li) { e.preventDefault(); choose(li.dataset.sym); } });
    document.addEventListener('click', e => { if (!e.target.closest('.ex-search')) closeResults(); });
    $('examples').insertAdjacentHTML('beforeend', ['SPY', 'AAPL', 'NVDA', 'TLT', 'KO', 'RDDT'].filter(s => entry(s)).map(s => '<button type="button" data-sym="' + s + '"' + (s === 'KO' ? ' title="No dividend data: shows the price-return label"' : s === 'RDDT' ? ' title="Short history: shows the clipped-period notice"' : '') + '>' + s + '</button>').join(''));
    $('examples').addEventListener('click', e => { const b = e.target.closest('button[data-sym]'); if (b) choose(b.dataset.sym); });
  }
  function choose(sym) {
    state.sym = sym; $('q').value = ''; closeResults(); syncHash(); render();
    $('detail').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  /* ---------- watchlist ---------- */
  function sparkline(closes) {
    if (!closes || closes.length < 2) return '';
    const w = 70, h = 20, lo = Math.min.apply(null, closes), hi = Math.max.apply(null, closes), sp = hi - lo || 1;
    const d = closes.map((v, i) => (i ? 'L' : 'M') + (i * w / (closes.length - 1)).toFixed(1) + ' ' + (h - 1 - (v - lo) / sp * (h - 2)).toFixed(1)).join('');
    const col = closes[closes.length - 1] >= closes[0] ? 'var(--up)' : 'var(--down)';
    return '<svg viewBox="0 0 ' + w + ' ' + h + '" width="' + w + '" height="' + h + '" aria-hidden="true"><path d="' + d + '" fill="none" stroke="' + col + '" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  }
  async function renderWatch() {
    const ul = $('watch');
    $('wlCap').textContent = watchlist.length ? 'Return over ' + state.period + '. Saved in this browser and still here after a reload.' : 'Saved in this browser and still here after a reload.';
    if (!watchlist.length) { ul.innerHTML = '<li class="empty" style="display:block">Nothing saved yet. Open a security and press <b>☆ Add to watchlist</b>.</li>'; return; }
    ul.innerHTML = watchlist.map(s => '<li data-sym="' + E(s) + '"><button class="open" type="button"><span class="tk">' + E(s) + '</span><span class="sub">' + E((entry(s) || {}).n || 'not in this sample') + '</span></button><span class="ret"><span class="muted">…</span></span><button class="rm" type="button" aria-label="Remove ' + E(s) + ' from watchlist" title="Remove">×</button></li>').join('');
    watchlist.forEach(async s => {
      const li = ul.querySelector('li[data-sym="' + CSS.escape(s) + '"]'); if (!li) return;
      try {
        const ser = await loadSeries(s); const sum = Finance.summarize(ser, state.period, null);
        const cd = Finance.chartData(ser, '3M');
        li.querySelector('.ret').innerHTML = (sum.cumulativeReturn == null ? '—' : '<span class="' + dir(sum.cumulativeReturn) + '">' + pct(sum.cumulativeReturn) + '</span><small>' + (sum.basis === 'total' ? 'total' : 'price') + ' return</small>');
        li.querySelector('.sub').insertAdjacentHTML('afterbegin', CS.money(ser.close[ser.close.length - 1]) + ' · ');
        li.querySelector('.open').insertAdjacentHTML('beforeend', sparkline(cd.close));
      } catch (e) { li.querySelector('.ret').textContent = 'n/a'; }
    });
  }
  function saveWatch(list) { watchlist = ExplorerSearch.watch.clean(list); ExplorerSearch.watch.save(storage, watchlist); renderWatch(); updateStar(); }
  function bindWatch() {
    $('watch').addEventListener('click', e => {
      const li = e.target.closest('li[data-sym]'); if (!li) return;
      if (e.target.closest('.rm')) saveWatch(ExplorerSearch.watch.remove(watchlist, li.dataset.sym));
      else if (e.target.closest('.open')) choose(li.dataset.sym);
    });
  }
  function updateStar() {
    const b = $('star'); if (!b) return;
    const on = ExplorerSearch.watch.has(watchlist, state.sym);
    b.setAttribute('aria-pressed', String(on)); b.innerHTML = on ? '★ In watchlist' : '☆ Add to watchlist';
  }

  /* ---------- detail ---------- */
  const tile = (label, value, sub, cls, basis) => '<div class="metric"><span class="l">' + label + '</span><span class="v ' + (cls || '') + '">' + value + '</span><span class="s">' + sub + '</span>' + (basis ? '<span class="basis ' + basis + '">' + (basis === 'total' ? 'total return' : 'price return') + '</span>' : '') + '</div>';

  function metricTiles(sum, isBench) {
    const b = sum.basis; const dd = sum.maxDrawdown || {};
    const t = [];
    t.push(tile('Return · ' + state.period, pct(sum.cumulativeReturn), sum.basisLabel + (sum.truncated ? '<br>from ' + CS.date(sum.startDate) : ''), dir(sum.cumulativeReturn), b));
    t.push(tile('Annualized return', pct(sum.annualizedReturn), sum.annualizedReturn == null ? 'Shown for windows of one year or more' : 'Compound annual growth rate', dir(sum.annualizedReturn), sum.annualizedReturn == null ? null : b));
    t.push(tile('Volatility', plain(sum.volatility), sum.volatility == null ? 'Needs at least 20 daily returns' : 'Annualized std. deviation of daily returns', '', sum.volatility == null ? null : b));
    t.push(tile('Max drawdown', dd.depth == null ? '—' : plain(dd.depth), dd.peakDate ? 'Peak ' + CS.date(dd.peakDate) + ' → trough ' + CS.date(dd.troughDate) + (dd.recoveryDate ? '<br>recovered ' + CS.date(dd.recoveryDate) : '<br>not yet recovered') : (dd.depth === 0 ? 'No decline in this window' : 'Not enough data'), dd.depth < 0 ? 'down' : '', dd.depth == null ? null : b));
    const v = sum.volume;
    t.push(tile('Avg daily volume', v ? CS.compact(v.avg) : '—', v ? 'Avg dollar volume $' + CS.compact(v.avgDollar) + ' · shares are unadjusted' : 'Volume not available'));
    t.push(tile('Dividend yield (TTM)', sum.dividends ? plain(sum.dividends.yieldTTM, 2) : '—', sum.dividends ? 'Trailing 12 months, on the latest close' : 'Dividend history is unavailable'));
    if (!isBench && sum.compare && sum.compare.series) {
      const c = sum.compare;
      t.push(tile('vs ' + BENCH + ' · excess return', c.excessReturn == null ? '—' : (c.excessReturn >= 0 ? '+' : '−') + CS.num(Math.abs(c.excessReturn) * 100, 2) + ' pts', 'This security ' + pct(c.cumulativeReturnA) + ' vs ' + BENCH + ' ' + pct(c.cumulativeReturnB), dir(c.excessReturn), c.basis));
      t.push(tile('Beta vs ' + BENCH, c.beta == null ? '—' : CS.num(c.beta, 2), c.beta == null ? 'Needs at least 60 overlapping daily returns' : 'Sensitivity to ' + BENCH + ' moves (' + c.nReturns + ' daily returns)'));
      t.push(tile('Correlation vs ' + BENCH, c.correlation == null ? '—' : CS.num(c.correlation, 2), c.correlation == null ? 'Needs at least 60 overlapping daily returns' : 'How closely the daily returns move together'));
    }
    return t.join('');
  }

  const color = n => CS.cssVar(n);
  function mkChart(id, cfg) { if (charts[id]) charts[id].destroy(); const el = $(id); if (el) charts[id] = new Chart(el, cfg); }
  const common = () => ({ responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, animation: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? false : { duration: 250 } });
  const tip = cb => ({ backgroundColor: color('--surface-3'), titleColor: color('--text'), bodyColor: color('--text-2'), borderColor: color('--border'), borderWidth: 1, padding: 10, callbacks: cb });
  const xAxis = () => ({ grid: { display: false }, ticks: { maxTicksLimit: window.innerWidth < 560 ? 4 : 7, autoSkip: true, maxRotation: 0 } });

  function drawCharts(ser, sum, isBench, spy) {
    Chart.defaults.color = color('--text-2'); Chart.defaults.font.family = color('--font'); Chart.defaults.borderColor = color('--grid');
    const cd = Finance.chartData(ser, state.period);
    const labels = cd.dates.map(d => CS.date(d, cd.dates.length > 260 ? false : true));
    const cmp = (!isBench && state.compare && sum.compare && sum.compare.series) ? sum.compare : null;
    let datasets, yTitle, fmt, titleText;
    if (cmp) {
      const L = cmp.series.dates.map(d => CS.date(d, cmp.series.dates.length > 260 ? false : true));
      datasets = [{ label: ser.symbol, data: cmp.series.a, borderColor: color('--accent'), backgroundColor: color('--accent') }, { label: BENCH, data: cmp.series.b, borderColor: color('--stock'), backgroundColor: color('--stock') }];
      yTitle = 'Growth of 100'; fmt = v => CS.num(v, 2); titleText = 'Growth of 100 · ' + cmp.basisLabel;
      mkChart('chMain', { type: 'line', data: { labels: L, datasets: datasets.map(d => Object.assign({ borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.1 }, d)) }, options: Object.assign(common(), { scales: { x: xAxis(), y: { grid: { color: color('--grid') }, title: { display: true, text: yTitle } } }, plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: tip({ label: c => ' ' + c.dataset.label + ': ' + fmt(c.parsed.y) }) } }) });
    } else if (state.mode === 'price') {
      titleText = 'Closing price (USD, split-adjusted, excludes dividends)';
      mkChart('chMain', { type: 'line', data: { labels, datasets: [{ label: ser.symbol + ' close', data: cd.close, borderColor: color('--accent'), borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.1 }] }, options: Object.assign(common(), { scales: { x: xAxis(), y: { grid: { color: color('--grid') }, title: { display: true, text: 'USD' } } }, plugins: { legend: { display: false }, tooltip: tip({ label: c => ' ' + CS.money(c.parsed.y) }) } }) });
    } else {
      titleText = 'Growth of 100 · ' + sum.basisLabel;
      const ds = [{ label: ser.symbol + ' (' + (cd.basis === 'total' ? 'total return' : 'price return') + ')', data: cd.growth, borderColor: color('--accent'), borderWidth: 2 }];
      if (cd.basis === 'total') ds.push({ label: ser.symbol + ' (price only)', data: cd.priceGrowth, borderColor: color('--muted'), borderWidth: 1.5, borderDash: [5, 4] });
      mkChart('chMain', { type: 'line', data: { labels, datasets: ds.map(d => Object.assign({ pointRadius: 0, pointHoverRadius: 4, tension: 0.1 }, d)) }, options: Object.assign(common(), { scales: { x: xAxis(), y: { grid: { color: color('--grid') }, title: { display: true, text: 'Growth of 100' } } }, plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: tip({ label: c => ' ' + c.dataset.label + ': ' + CS.num(c.parsed.y, 2) }) } }) });
    }
    $('mainTitle').textContent = titleText;
    mkChart('chDD', { type: 'line', data: { labels, datasets: [{ label: 'Drawdown', data: cd.drawdown, borderColor: color('--down'), backgroundColor: color('--down-soft'), fill: true, borderWidth: 1.5, pointRadius: 0, tension: 0 }] }, options: Object.assign(common(), { scales: { x: xAxis(), y: { grid: { color: color('--grid') }, max: 0, ticks: { callback: v => Math.round(v * 10) / 10 + '%' } } }, plugins: { legend: { display: false }, tooltip: tip({ label: c => ' ' + CS.num(c.parsed.y, 2) + '% below peak' }) } }) });
    if (cd.volume) mkChart('chVol', { type: 'bar', data: { labels, datasets: [{ label: 'Volume', data: cd.volume, backgroundColor: color('--stock'), borderWidth: 0, barPercentage: 1, categoryPercentage: 1 }] }, options: Object.assign(common(), { scales: { x: xAxis(), y: { grid: { color: color('--grid') }, ticks: { callback: v => CS.compact(v) } } }, plugins: { legend: { display: false }, tooltip: tip({ label: c => ' ' + CS.int(c.parsed.y) + ' shares' }) } }) });
  }

  async function render() {
    const box = $('detail');
    if (!state.sym) {
      box.innerHTML = '<div class="card ex-empty"><h2>Pick a security to begin</h2><p>Search above or try an example. You will see its price history, return, volatility, drawdown and volume, and how it compares with SPY, with every return labelled as <b>price return</b> or <b>total return</b>.</p></div>';
      return;
    }
    const sym = state.sym; const e = entry(sym) || {};
    box.innerHTML = '<div class="card"><p class="muted">Loading ' + E(sym) + '…</p></div>';
    let ser, spy = null;
    try { ser = await loadSeries(sym); if (sym !== BENCH) spy = await loadSeries(BENCH); }
    catch (err) { box.innerHTML = '<div class="card"><div class="banner error"><span><b>Could not load ' + E(sym) + '.</b> ' + E(err.message) + '</span></div></div>'; return; }
    if (state.sym !== sym) return;                                  // a newer choice arrived meanwhile
    const isBench = sym === BENCH;
    const sum = Finance.summarize(ser, state.period, isBench ? null : spy);
    const warnings = sum.warnings.filter(w => WARN[w] || w === 'TRUNCATED').concat(sum.compare ? sum.compare.warnings.filter(w => WARN[w]) : []);
    const notes = []; const seen = new Set();
    warnings.forEach(w => { if (seen.has(w)) return; seen.add(w);
      if (w === 'TRUNCATED') notes.push('<div class="banner warn"><span>This history is shorter than ' + state.period + ': showing from <b>' + CS.date(sum.startDate) + '</b>, the first available close.</span></div>');
      else notes.push('<div class="banner warn"><span>' + WARN[w] + '</span></div>'); });
    if (sum.basis === 'total') notes.push('<div class="banner"><span>Returns include <b>reinvested dividends</b> (total return). The dashed line in the chart shows the price-only result for comparison.</span></div>');
    const hasCompare = !isBench;
    box.innerHTML =
      '<div class="card">' +
      '<div class="ex-head"><h2><span class="tk">' + E(sym) + '</span><span class="nm">' + E(ser.name || e.n || '') + '</span></h2>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center"><span class="chip">' + E(ser.type || (e.t === 'E' ? 'ETF' : 'Stock')) + '</span><span class="chip">' + E(ser.exchange || e.x || '') + '</span>' + (ser.synthetic ? '<span class="chip" title="Generated, not real market prices">simulated</span>' : '') +
      '<button class="btn small ex-star" id="star" type="button" aria-pressed="false"></button></div></div>' +
      '<div class="ex-controls"><div class="seg" role="group" aria-label="Period">' + PERIODS.map(p => '<button type="button" data-p="' + p + '" aria-pressed="' + (p === state.period) + '">' + p + '</button>').join('') + '</div>' +
      (hasCompare ? '<label class="check"><input type="checkbox" id="cmp"' + (state.compare ? ' checked' : '') + '> Compare with ' + BENCH + '</label>' : '') +
      (!(hasCompare && state.compare) ? '<div class="seg" role="group" aria-label="Chart type"><button type="button" data-m="growth" aria-pressed="' + (state.mode === 'growth') + '">Growth of 100</button><button type="button" data-m="price" aria-pressed="' + (state.mode === 'price') + '">Price</button></div>' : '') +
      '</div>' +
      '<div class="notes">' + notes.join('') + '</div></div>' +
      '<div class="metrics" aria-label="Metrics">' + metricTiles(sum, isBench) + '</div>' +
      '<div class="charts"><div class="card"><h3 id="mainTitle"></h3><div class="chart-box"><canvas id="chMain" role="img" aria-label="Price or growth chart"></canvas></div></div>' +
      '<div class="card"><h3>Drawdown from the running peak</h3><p class="cap" style="margin-bottom:6px">Same basis as the return above (' + (sum.basis === 'total' ? 'total' : 'price') + ' return).</p><div class="chart-box mini"><canvas id="chDD" role="img" aria-label="Drawdown chart"></canvas></div></div>' +
      (ser.volume ? '<div class="card"><h3>Daily volume</h3><p class="cap" style="margin-bottom:6px">Shares traded, unadjusted.</p><div class="chart-box mini"><canvas id="chVol" role="img" aria-label="Volume chart"></canvas></div></div>' : '') + '</div>';
    updateStar();
    drawCharts(ser, sum, isBench, spy);
    renderWatch();
    $('star').addEventListener('click', () => saveWatch(ExplorerSearch.watch.has(watchlist, sym) ? ExplorerSearch.watch.remove(watchlist, sym) : ExplorerSearch.watch.add(watchlist, sym)));
    box.querySelectorAll('[data-p]').forEach(b => b.addEventListener('click', () => { state.period = b.dataset.p; syncHash(); render(); }));
    box.querySelectorAll('[data-m]').forEach(b => b.addEventListener('click', () => { state.mode = b.dataset.m; render(); }));
    const c = $('cmp'); if (c) c.addEventListener('change', () => { state.compare = c.checked; syncHash(); render(); });
  }

  /* ---------- URL hash: #AAPL&p=1Y&c=0 ---------- */
  function parseHash() {
    const h = decodeURIComponent(location.hash.replace(/^#/, '')); if (!h) return;
    const parts = h.split('&'); const sym = parts[0].toUpperCase();
    if (/^[A-Z0-9][A-Z0-9.\-]{0,9}$/.test(sym) && entry(sym)) state.sym = sym;
    parts.slice(1).forEach(kv => { const [k, v] = kv.split('=');
      if (k === 'p' && PERIODS.indexOf(v) >= 0) state.period = v; if (k === 'c') state.compare = v !== '0'; });
  }
  function syncHash() {
    if (!state.sym) return;
    const h = '#' + state.sym + '&p=' + state.period + (state.compare ? '' : '&c=0');
    try { history.replaceState(null, '', h); } catch (e) { /* ignore */ }
  }

  /* ---------- start ---------- */
  async function start() {
    try {
      const data = await getJSON(ROOT + 'index.json');
      index = data.entries; meta = data.meta; searchIdx = ExplorerSearch.buildIndex(index);
    } catch (err) {
      CS.banner('dataBanner', 'error', '<span><b>Could not load the security list.</b> ' + E(err.message) + ' If you are offline and have not opened this page before, there is no saved copy yet.</span>');
      CS.doneLoading(); return;
    }
    if (meta.synthetic) $('synthBanner').hidden = false;
    $('heroLead').textContent = 'Search ' + index.length + ' securities by ticker or company name, chart the history, compare against SPY, and see return, volatility, drawdown and volume, always labelled as price return or total return.';
    watchlist = ExplorerSearch.watch.load(storage);
    parseHash(); bindSearch(); bindWatch();
    window.addEventListener('cs-theme', () => { if (state.sym) render(); });
    window.addEventListener('hashchange', () => { parseHash(); render(); });
    await render(); renderWatch(); CS.doneLoading();
  }
  start();
})();
