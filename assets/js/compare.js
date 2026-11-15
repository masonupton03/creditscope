/* Compare page: prices and risk for 2-6 securities (CompareCalc), and fundamentals for up to 4 companies (FundCalc).
 * Real and simulated data are kept apart: each section has its own source and its own label. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const E = CS.esc;
  const PERSONAL = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname) && !!document.querySelector('meta[name="creditscope-personal"]');
  const BENCH = 'SPY', MAX_FD = 4;
  const state = { syms: [], period: '1Y', fd: [] };
  let priceMeta = {}, priceIndex = [], fdIndex = [], priceRoot = 'explorer/sample/', personal = false, fdRoot = 'explorer/sec-sample/', fdSynth = true;
  const cache = new Map(), fdCache = new Map(), charts = {};
  const PRESET = ['AAPL', 'MSFT', 'TLT', 'XOM'];
  const COLORS = ['--accent', '--stock', '--bond', '--up', '--down', '--flat'];
  const colorOf = i => CS.cssVar(COLORS[i % COLORS.length]);

  async function getJSON(url) {
    const res = await fetch(url, personal ? { cache: 'no-store' } : undefined);
    if (!res.ok) { await res.text().catch(() => ''); throw new Error(url + ' returned HTTP ' + res.status); }
    return res.json();
  }
  const loadSeries = sym => { if (!cache.has(sym)) cache.set(sym, getJSON(personal ? 'api/series/' + encodeURIComponent(sym) : priceRoot + 'series/' + encodeURIComponent(sym) + '.json').catch(e => { cache.delete(sym); throw e; })); return cache.get(sym); };
  const loadCompany = sym => { if (!fdCache.has(sym)) fdCache.set(sym, getJSON(fdRoot + 'company/' + encodeURIComponent(sym) + '.json').catch(e => { fdCache.delete(sym); throw e; })); return fdCache.get(sym); };

  /* ---------- formatting ---------- */
  const sign = v => (v < 0 && Math.round(Math.abs(v) * 1e4) > 0 ? '−' : '');
  const pct = v => (v == null ? '—' : CS.pct(v * 100, 1));
  const plain = (v, d) => (v == null ? '—' : sign(v) + CS.num(Math.abs(v) * 100, d == null ? 1 : d) + '%');
  const dir = v => CS.dir(v == null ? null : v);

  /* ---------- URL state ---------- */
  function parseHash() {
    const q = new URLSearchParams(location.hash.slice(1));
    const list = (k, re) => (q.get(k) || '').split(',').map(s => s.trim().toUpperCase()).filter(s => re.test(s));
    state.syms = Array.from(new Set(list('s', /^[A-Z0-9][A-Z0-9.\-]{0,9}$/))).slice(0, CompareCalc.MAX_SECURITIES);
    state.fd = Array.from(new Set(list('f', /^[A-Z0-9][A-Z0-9.\-]{0,9}$/))).slice(0, MAX_FD);
    if (Finance.PERIODS.indexOf(q.get('p')) >= 0) state.period = q.get('p');
  }
  function syncHash() {
    const q = new URLSearchParams(); if (state.syms.length) q.set('s', state.syms.join(',')); q.set('p', state.period); if (state.fd.length) q.set('f', state.fd.join(','));
    history.replaceState(null, '', '#' + q.toString());
  }

  /* ---------- chips ---------- */
  function chips(el, list, names, remove, colors) {
    el.innerHTML = list.map((s, i) => '<li>' + (colors ? '<span class="sw" style="background:' + colorOf(i) + '"></span>' : '') + '<span class="tk">' + E(s) + '</span><span class="nm">' + E(names[s] || '') + '</span><button type="button" data-s="' + E(s) + '" aria-label="Remove ' + E(s) + '">×</button></li>').join('');
    el.onclick = ev => { const b = ev.target.closest('button[data-s]'); if (b) remove(b.dataset.s); };
  }
  const nameMap = idx => Object.fromEntries(idx.map(e => [e.s, e.n]));

  /* ---------- prices and risk ---------- */
  const color = n => CS.cssVar(n);
  function mk(id, cfg) { if (charts[id]) charts[id].destroy(); if ($(id)) charts[id] = new Chart($(id), cfg); }
  const common = () => ({ responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, animation: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? false : { duration: 250 } });
  const tip = cb => ({ backgroundColor: color('--surface-3'), titleColor: color('--text'), bodyColor: color('--text-2'), borderColor: color('--border'), borderWidth: 1, padding: 10, callbacks: cb });

  async function renderPrices() {
    chips($('chosen'), state.syms, nameMap(priceIndex), s => { state.syms = state.syms.filter(x => x !== s); syncHash(); renderPrices(); }, true);
    $('periods').innerHTML = Finance.PERIODS.map(k => '<button type="button" data-p="' + k + '" aria-pressed="' + (k === state.period) + '">' + k + '</button>').join('');
    const out = $('cmpOut'), notes = $('notes'); notes.innerHTML = '';
    if (state.syms.length < 2) { out.innerHTML = '<div class="ex-empty"><h2>Choose two or more securities</h2><p>Search above, or use “Try an example”.</p></div>'; Object.keys(charts).forEach(k => { charts[k].destroy(); delete charts[k]; }); return; }
    out.innerHTML = CS.loadingHtml('Loading prices…');
    let list, bench = null;
    try {
      list = await Promise.all(state.syms.map(loadSeries));
      bench = state.syms.indexOf(BENCH) >= 0 ? null : await loadSeries(BENCH).catch(() => null);
    } catch (e) { out.innerHTML = CS.errorHtml('Could not load a security.', e.message, true); out.querySelector('[data-retry]').addEventListener('click', renderPrices); return; }
    const r = CompareCalc.compare(list, state.period, bench || list.find(s => s.symbol === BENCH) || null);
    if (r.errors.length) { out.innerHTML = '<div class="banner warn"><span>' + E(r.errors[0].message) + '</span></div>'; return; }
    notes.innerHTML = r.warnings.map(w => '<div class="banner warn"><span>' + E(w.message) + '</span></div>').join('');
    const rows = r.stats.map((s, i) => {
      const dd = s.maxDrawdown;
      return '<tr><td><span class="sw" style="display:inline-block;width:10px;height:10px;border-radius:3px;background:' + colorOf(i) + ';margin-right:8px"></span><span class="tk">' + E(s.symbol) + '</span><br><span class="nm">' + E(s.name) + '</span></td>' +
        '<td class="r ' + dir(s.cumulative) + '">' + pct(s.cumulative) + '</td><td class="r ' + dir(s.annualized) + '">' + pct(s.annualized) + '</td><td class="r">' + plain(s.volatility) + '</td>' +
        '<td class="r">' + plain(dd.depth) + (dd.troughDate ? '<br><small class="nm">trough ' + CS.date(dd.troughDate) + '</small>' : '') + '</td>' +
        '<td class="r">' + (s.beta == null ? '—' : CS.num(s.beta, 2)) + '</td><td class="r">' + (s.correlationToBenchmark == null ? '—' : CS.num(s.correlationToBenchmark, 2)) + '</td></tr>';
    }).join('');
    const corr = r.correlation ? '<div class="table-wrap"><table class="corr"><caption class="sr-only">Correlation of daily returns between each pair</caption><thead><tr><th><span class="sr-only">Security</span></th>' + r.symbols.map(s => '<th scope="col">' + E(s) + '</th>').join('') + '</tr></thead><tbody>' +
      r.correlation.map((row, i) => '<tr><th scope="row">' + E(r.symbols[i]) + '</th>' + row.map(v => '<td style="background:color-mix(in srgb, var(--accent) ' + Math.round(Math.max(0, Math.abs(v == null ? 0 : v)) * 24) + '%, var(--surface))">' + (v == null ? '—' : CS.num(v, 2)) + '</td>').join('') + '</tr>').join('') + '</tbody></table></div>' : '<p class="cap">Correlation needs at least 60 shared daily returns.</p>';
    out.innerHTML = '<p class="cap">' + E(r.basisLabel) + ' · ' + CS.date(r.startDate) + ' to ' + CS.date(r.endDate) + ' · ' + r.nReturns + ' shared daily returns · beta and correlation are versus ' + BENCH + '</p>' +
      '<div class="table-wrap"><table class="t"><caption class="sr-only">Return and risk by security over the common window</caption><thead><tr><th>Security</th><th class="r">Return</th><th class="r">Annualized</th><th class="r">Volatility</th><th class="r">Max drawdown</th><th class="r">Beta</th><th class="r">Corr. vs ' + BENCH + '</th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
      '<div class="charts"><div class="card"><h3>Growth of 100</h3><div class="chart-box"><canvas id="chGrow" role="img" aria-label="Growth of 100 for each security"></canvas></div></div>' +
      '<div class="card"><h3>Drawdown</h3><div class="chart-box short"><canvas id="chDD" role="img" aria-label="Drawdown for each security"></canvas></div></div>' +
      '<div class="card"><h3>Correlation of daily returns</h3><p class="cap">1 = move together, 0 = unrelated, −1 = move oppositely.</p>' + corr + '</div></div>';
    Chart.defaults.color = color('--text-2'); Chart.defaults.font.family = color('--font'); Chart.defaults.borderColor = color('--grid');
    const labels = r.growth.dates.map(d => CS.date(d, r.growth.dates.length > 260 ? false : true));
    const ds = (src) => r.symbols.map((s, i) => ({ label: s, data: src[s], borderColor: colorOf(i), backgroundColor: colorOf(i), borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.1 }));
    const xAxis = { grid: { display: false }, ticks: { maxTicksLimit: window.innerWidth < 560 ? 4 : 7, autoSkip: true, maxRotation: 0 } };
    mk('chGrow', { type: 'line', data: { labels, datasets: ds(r.growth.series) }, options: Object.assign(common(), { scales: { x: xAxis, y: { grid: { color: color('--grid') }, title: { display: true, text: 'Growth of 100' } } }, plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: tip({ label: x => ' ' + x.dataset.label + ': ' + CS.num(x.parsed.y, 2) }) } }) });
    mk('chDD', { type: 'line', data: { labels, datasets: ds(r.drawdown) }, options: Object.assign(common(), { scales: { x: xAxis, y: { grid: { color: color('--grid') }, title: { display: true, text: '%' } } }, plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: tip({ label: x => ' ' + x.dataset.label + ': ' + CS.num(x.parsed.y, 1) + '%' }) } }) });
  }

  /* ---------- fundamentals ---------- */
  async function renderFund() {
    chips($('fchosen'), state.fd, nameMap(fdIndex), s => { state.fd = state.fd.filter(x => x !== s); syncHash(); renderFund(); }, true);
    const out = $('fdOut');
    if (state.fd.length < 2) { out.innerHTML = '<div class="ex-empty"><h2>Choose two or more companies</h2><p>Search above to compare revenue growth, margins, returns and leverage.</p></div>'; return; }
    let cs;
    try { cs = await Promise.all(state.fd.map(loadCompany)); } catch (e) { out.innerHTML = CS.errorHtml('Could not load a company.', e.message, true); out.querySelector('[data-retry]').addEventListener('click', renderFund); return; }
    const A = cs.map(c => FundCalc.analyze(c));
    const rows = [['Latest fiscal year', (a, c) => (a.latestFiscalYear == null ? '—' : 'FY' + a.latestFiscalYear + ' (ended ' + CS.date(c.latestPeriodEnd, true) + ')')],
      ['Revenue growth', (a, c, r) => pct(r.revenueGrowth)], ['Revenue CAGR, 3 years', a => pct(a.cagr[3])], ['Gross margin', (a, c, r) => plain(r.grossMargin)], ['Operating margin', (a, c, r) => plain(r.operatingMargin)],
      ['Net margin', (a, c, r) => plain(r.netMargin)], ['Free-cash-flow margin', (a, c, r) => plain(r.fcfMargin)], ['Return on equity', (a, c, r) => plain(r.roe)], ['Return on assets', (a, c, r) => plain(r.roa)],
      ['Debt to equity', (a, c, r) => (r.debtToEquity == null ? '—' : CS.num(r.debtToEquity, 2) + '×')], ['Liabilities to assets', (a, c, r) => plain(r.liabilitiesToAssets)]];
    const body = rows.map(([label, f]) => '<tr><th scope="row" class="nm" style="text-align:left;font-weight:500">' + label + '</th>' + cs.map((c, i) => { const a = A[i]; const r = a.latestFiscalYear == null ? {} : a.ratios[a.latestFiscalYear]; return '<td class="r">' + f(a, c, r) + '</td>'; }).join('') + '</tr>').join('');
    const warn = cs.map((c, i) => A[i].warnings.filter(w => w.code === 'NEGATIVE_EQUITY' || w.code === 'MISSING_METRICS').map(w => '<div class="banner warn"><span><b>' + E(c.ticker) + ':</b> ' + E(w.message) + '</span></div>').join('')).join('');
    const stale = cs.map(c => { const f = FundCalc.freshness(c, new Date().toISOString().slice(0, 10)); return f.stale && !c.synthetic ? '<div class="banner warn"><span><b>' + E(c.ticker) + '</b>: latest annual report filed ' + CS.date(f.latestFiled) + '; a newer one may exist.</span></div>' : ''; }).join('');
    out.innerHTML = '<div class="notes">' + warn + stale + '</div><div class="table-wrap"><table class="t"><caption class="sr-only">Latest fiscal year ratios by company</caption><thead><tr><th>Latest fiscal year</th>' + cs.map(c => '<th class="r"><span class="tk">' + E(c.ticker) + '</span><br><small class="nm">' + E(c.name) + '</small></th>').join('') + '</tr></thead><tbody>' + body + '</tbody></table></div>' +
      '<div class="charts"><div class="card"><h3>Operating margin by fiscal year</h3><div class="chart-box short"><canvas id="chFdMargin" role="img" aria-label="Operating margin by fiscal year for each company"></canvas></div></div>' +
      '<div class="card"><h3>Revenue growth by fiscal year</h3><div class="chart-box short"><canvas id="chFdGrowth" role="img" aria-label="Revenue growth by fiscal year for each company"></canvas></div></div></div>';
    const years = Array.from(new Set([].concat(...A.map(a => a.years)))).sort((x, y) => x - y);
    const mkds = key => cs.map((c, i) => ({ label: c.ticker, data: years.map(y => (A[i].ratios[y] && A[i].ratios[y][key] != null ? A[i].ratios[y][key] * 100 : null)), borderColor: colorOf(i), backgroundColor: colorOf(i), borderWidth: 2, pointRadius: 3, tension: 0.1 }));
    const opts = Object.assign(common(), { scales: { x: { grid: { display: false } }, y: { grid: { color: color('--grid') }, title: { display: true, text: '%' } } }, plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: tip({ label: x => ' ' + x.dataset.label + ': ' + (x.parsed.y == null ? 'not available' : CS.num(x.parsed.y, 1) + '%') }) } });
    mk('chFdMargin', { type: 'line', data: { labels: years.map(y => 'FY' + y), datasets: mkds('operatingMargin') }, options: opts });
    mk('chFdGrowth', { type: 'line', data: { labels: years.map(y => 'FY' + y), datasets: mkds('revenueGrowth') }, options: opts });
  }

  /* ---------- start ---------- */
  async function start() {
    parseHash();
    try {
      if (PERSONAL) {
        try { const d = await getJSON('private-data/index.json'); priceIndex = d.entries; priceMeta = d.meta || {}; personal = true; } catch (e) { personal = false; }
      }
      if (!personal) { const d = await getJSON(priceRoot + 'index.json'); priceIndex = d.entries; priceMeta = d.meta || {}; }
      try { const d = await getJSON('explorer/sec/index.json'); if (d.entries.length) { fdIndex = d.entries; fdRoot = 'explorer/sec/'; fdSynth = !!d.meta.synthetic; } } catch (e) { /* fall through to the sample */ }
      if (!fdIndex.length) { const d = await getJSON('explorer/sec-sample/index.json'); fdIndex = d.entries; fdRoot = 'explorer/sec-sample/'; fdSynth = true; }
    } catch (e) { CS.banner('dataBanner', 'error', '<span><b>Could not load the data lists.</b> ' + E(e.message) + '</span>'); CS.doneLoading(); return; }
    if (personal) { $('privateBanner').hidden = false; $('privateBanner').firstElementChild.innerHTML = '<b>Private: real prices, local only.</b> Do not screenshot or screen-share this page. Prices are from your own data account; <b>volume is not used</b> here.'; }
    else $('synthBanner').hidden = false;
    $('fdSynth').hidden = !fdSynth;
    $('pxCap').textContent = (personal ? 'Real prices from your private data. ' : 'Simulated prices. ') + 'Search ' + CS.int(priceIndex.length) + ' securities' + (priceMeta.asOf ? ' · prices through ' + CS.date(priceMeta.asOf) : '') + '.';
    $('fdCap').textContent = fdSynth ? 'Fictional companies for demonstration.' : 'Reported annual figures from SEC filings.';
    Picker.attach({ input: $('q'), list: $('results'), entries: priceIndex, noneText: 'No match in this data set.', onChoose: e => { if (state.syms.indexOf(e.s) < 0 && state.syms.length < CompareCalc.MAX_SECURITIES) { state.syms.push(e.s); syncHash(); renderPrices(); } } });
    Picker.attach({ input: $('fq'), list: $('fresults'), entries: fdIndex, noneText: 'No company with that name in this data set.', scope: '#fq', onChoose: e => { if (state.fd.indexOf(e.s) < 0 && state.fd.length < MAX_FD) { state.fd.push(e.s); syncHash(); renderFund(); } } });
    $('periods').addEventListener('click', ev => { const b = ev.target.closest('button[data-p]'); if (b) { state.period = b.dataset.p; syncHash(); renderPrices(); } });
    $('presetBtn').addEventListener('click', () => { state.syms = PRESET.filter(s => priceIndex.some(e => e.s === s)); state.fd = fdIndex.slice(0, 3).map(e => e.s); syncHash(); renderPrices(); renderFund(); });
    $('themeBtn').addEventListener('click', () => setTimeout(() => { renderPrices(); renderFund(); }, 30));
    state.syms = state.syms.filter(s => priceIndex.some(e => e.s === s)); state.fd = state.fd.filter(s => fdIndex.some(e => e.s === s));
    await Promise.all([renderPrices(), renderFund()]);
    CS.doneLoading();
  }
  start();
})();
