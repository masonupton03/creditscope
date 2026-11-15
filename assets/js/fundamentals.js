/* Fundamentals page: search companies, show SEC-reported annual figures, ratios, trends and filing links.
 * All ratios come from fundamentals-calc.js (verified against an independent Python implementation). */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const E = CS.esc;
  const REAL = 'explorer/sec/', SAMPLE = 'explorer/sec-sample/';
  let root = REAL, synthetic = false, index = [], picker = null, current = null, avail = null;
  const charts = {};

  async function getJSON(url) {
    const res = await fetch(url);
    if (!res.ok) { await res.text().catch(() => ''); throw new Error(url + ' returned HTTP ' + res.status); }
    return res.json();
  }
  const today = () => new Date().toISOString().slice(0, 10);

  /* ---------- formatting ---------- */
  const sign = v => (v < 0 ? '−' : '');
  const plain = (v, d) => (v == null ? '—' : sign(v) + CS.num(Math.abs(v) * 100, d == null ? 1 : d) + '%');
  const pct = (v, d) => (v == null ? '—' : CS.pct(v * 100, d == null ? 1 : d));
  const dir = v => CS.dir(v == null ? null : v);
  function scaleFor(company) {
    const vals = [].concat(...Object.values(company.metrics).filter(m => m.unit === 'USD').map(m => m.points.map(p => Math.abs(p.val))));
    const mx = vals.length ? Math.max(...vals) : 0;
    return mx >= 1e9 ? { div: 1e9, name: 'billions' } : { div: 1e6, name: 'millions' };
  }
  const usd = (v, sc, d) => (v == null ? '—' : sign(v) + '$' + CS.num(Math.abs(v) / sc.div, d == null ? 2 : d));
  const fdate = iso => (iso ? CS.date(iso) : '—');

  /* ---------- search ---------- */
  function choose(sym) { location.hash = sym; }
  function bindSearch() {
    picker = Picker.attach({ input: $('q'), list: $('results'), entries: index, noneText: 'No company with that name or ticker in this data set.', onChoose: e => choose(e.s) });
    $('examples').insertAdjacentHTML('beforeend', index.slice(0, 6).map(e => '<button type="button" data-sym="' + E(e.s) + '">' + E(e.s) + '</button>').join(''));
    $('examples').addEventListener('click', ev => { const b = ev.target.closest('button[data-sym]'); if (b) choose(b.dataset.sym); });
  }

  /* ---------- charts ---------- */
  const color = n => CS.cssVar(n);
  function mk(id, cfg) { if (charts[id]) charts[id].destroy(); if ($(id)) charts[id] = new Chart($(id), cfg); }
  const common = () => ({ responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, animation: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? false : { duration: 250 } });
  const tip = cb => ({ backgroundColor: color('--surface-3'), titleColor: color('--text'), bodyColor: color('--text-2'), borderColor: color('--border'), borderWidth: 1, padding: 10, callbacks: cb });
  const scales = t => ({ x: { grid: { display: false } }, y: { grid: { color: color('--grid') }, title: { display: !!t, text: t || '' } } });
  const legend = { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } };

  function drawCharts(c, a, sc) {
    Chart.defaults.color = color('--text-2'); Chart.defaults.font.family = color('--font'); Chart.defaults.borderColor = color('--grid');
    const ys = a.years, labels = ys.map(y => 'FY' + y);
    const V = (k, y) => (a.values[k] && a.values[k][y] ? a.values[k][y].val : null);
    const series = (k, f) => ys.map(y => { const v = f ? f(y) : V(k, y); return v == null ? null : v / sc.div; });
    const bar = (label, data, c1) => ({ label, data, backgroundColor: color(c1), borderWidth: 0 });
    const line = (label, data, c1) => ({ label, data, borderColor: color(c1), backgroundColor: color(c1), borderWidth: 2, pointRadius: 3, pointHoverRadius: 5, tension: 0.1, spanGaps: false });
    const usdTip = tip({ label: x => ' ' + x.dataset.label + ': ' + (x.parsed.y == null ? 'not reported' : sign(x.parsed.y) + '$' + CS.num(Math.abs(x.parsed.y), 2) + ' ' + sc.name) });
    mk('chRev', { type: 'bar', data: { labels, datasets: [bar('Revenue', series('revenue'), '--stock'), bar('Net income', series('netIncome'), '--up')] }, options: Object.assign(common(), { scales: scales('USD ' + sc.name), plugins: { legend, tooltip: usdTip } }) });
    const pctTip = tip({ label: x => ' ' + x.dataset.label + ': ' + (x.parsed.y == null ? 'not available' : CS.num(x.parsed.y, 1) + '%') });
    const r = (k) => ys.map(y => (a.ratios[y][k] == null ? null : a.ratios[y][k] * 100));
    mk('chMargin', { type: 'line', data: { labels, datasets: [line('Gross margin', r('grossMargin'), '--stock'), line('Operating margin', r('operatingMargin'), '--accent'), line('Net margin', r('netMargin'), '--up'), line('Free-cash-flow margin', r('fcfMargin'), '--bond')] }, options: Object.assign(common(), { scales: scales('% of revenue'), plugins: { legend, tooltip: pctTip } }) });
    mk('chBal', { type: 'bar', data: { labels, datasets: [bar('Total assets', series('assets'), '--stock'), bar('Total liabilities', series('liabilities'), '--down'), bar('Debt', series('debt'), '--accent'), bar('Cash', series('cash'), '--up')] }, options: Object.assign(common(), { scales: scales('USD ' + sc.name), plugins: { legend, tooltip: usdTip } }) });
    mk('chCash', { type: 'bar', data: { labels, datasets: [bar('Operating cash flow', series('operatingCashFlow'), '--up'), bar('Capital expenditure', series('capex'), '--down'), bar('Free cash flow', series(null, y => a.ratios[y].fcf), '--accent')] }, options: Object.assign(common(), { scales: scales('USD ' + sc.name), plugins: { legend, tooltip: usdTip } }) });
  }

  /* ---------- table ---------- */
  function table(c, a, sc) {
    const ys = a.years.slice(-10);
    const head = '<tr><th class="sticky" scope="col">USD ' + sc.name + ' unless noted</th>' + ys.map(y => {
      const p = ['revenue', 'netIncome', 'assets'].map(k => a.values[k] && a.values[k][y]).find(Boolean);
      const len = p && p.start ? Math.round((Date.UTC(+p.end.slice(0, 4), +p.end.slice(5, 7) - 1, +p.end.slice(8, 10)) - Date.UTC(+p.start.slice(0, 4), +p.start.slice(5, 7) - 1, +p.start.slice(8, 10))) / 864e5) : 0;
      return '<th class="r" scope="col">FY' + y + '<small>ends ' + (p ? fdate(p.end) : '—') + (len > 370 || (len && len < 360) ? '<br>' + Math.round(len / 7) + '-week year' : '') + '</small></th>';
    }).join('') + '</tr>';
    const cell = (k, y, fmt) => {
      const p = a.values[k] && a.values[k][y];
      if (!p) return '<td class="r na">—</td>';
      const txt = fmt(p.val);
      const tipText = p.form + ' filed ' + p.filed + ' · ' + p.tag + (p.start ? ' · period ' + p.start + ' to ' + p.end : ' · at ' + p.end);
      return '<td class="r">' + (synthetic ? '<span title="Simulated filing reference ' + E(p.accn) + '">' + txt + '</span>'
        : '<a href="' + FundCalc.filingUrl(c.cik, p.accn) + '" target="_blank" rel="noopener" title="' + E(tipText) + '">' + txt + '</a>') + '</td>';
    };
    const calc = (k, y, fmt, note) => { const v = a.ratios[y][k]; return '<td class="r' + (v == null ? ' na' : '') + '"' + (note && a.ratios[y][note] ? ' title="Derived: revenue minus cost of revenue"' : '') + '>' + (v == null ? '—' : fmt(v)) + (note && a.ratios[y][note] && v != null ? '*' : '') + '</td>'; };
    const m = v => usd(v, sc), eps = v => sign(v) + '$' + CS.num(Math.abs(v), 2);
    const rows = [];
    const grp = t => rows.push('<tr class="grp"><td class="sticky" colspan="' + (ys.length + 1) + '">' + t + '</td></tr>');
    const rep = (label, k, fmt) => { if (a.values[k]) rows.push('<tr><td class="sticky">' + label + '</td>' + ys.map(y => cell(k, y, fmt || m)).join('') + '</tr>'); };
    const der = (label, k, fmt, note) => rows.push('<tr><td class="sticky">' + label + '</td>' + ys.map(y => calc(k, y, fmt, note)).join('') + '</tr>');
    grp('Income statement'); rep('Revenue', 'revenue'); rep('Cost of revenue', 'costOfRevenue');
    rows.push('<tr><td class="sticky">Gross profit</td>' + ys.map(y => (a.values.grossProfit && a.values.grossProfit[y]) ? cell('grossProfit', y, m) : calc('grossProfit', y, m, 'grossProfitDerived')).join('') + '</tr>');
    rep('Operating income', 'operatingIncome'); rep('Net income', 'netIncome'); rep('Diluted EPS (USD per share)', 'epsDiluted', eps);
    grp('Balance sheet'); rep('Total assets', 'assets'); rep('Total liabilities', 'liabilities'); rep("Shareholders' equity", 'equity'); rep('Cash and equivalents', 'cash'); rep('Debt', 'debt');
    grp('Cash flow'); rep('Operating cash flow', 'operatingCashFlow'); rep('Capital expenditure', 'capex'); der('Free cash flow (derived)', 'fcf', m);
    grp('Growth and profitability (derived)'); der('Revenue growth', 'revenueGrowth', v => pct(v)); der('Gross margin', 'grossMargin', v => plain(v)); der('Operating margin', 'operatingMargin', v => plain(v)); der('Net margin', 'netMargin', v => plain(v));
    der('FCF margin', 'fcfMargin', v => plain(v)); der('Return on equity', 'roe', v => plain(v)); der('Return on assets', 'roa', v => plain(v));
    grp('Leverage (derived)'); der('Debt to equity', 'debtToEquity', v => CS.num(v, 2) + '×'); der('Net debt (debt − cash)', 'netDebt', m); der('Liabilities to assets', 'liabilitiesToAssets', v => plain(v));
    return '<table class="t fd-table"><caption class="sr-only">Annual figures reported to the SEC and ratios derived from them</caption><thead>' + head + '</thead><tbody>' + rows.join('') + '</tbody></table>';
  }

  /* ---------- page ---------- */
  const tile = (l, v, s, cls) => '<div class="metric"><span class="l">' + l + '</span><span class="v ' + (cls || '') + '">' + v + '</span><span class="s">' + s + '</span></div>';

  function render(c) {
    const a = FundCalc.analyze(c), sc = scaleFor(c), fr = FundCalc.freshness(c, today());
    const L = a.latestFiscalYear, r = L != null ? a.ratios[L] : {}, V = (k, y) => (a.values[k] && a.values[k][y] ? a.values[k][y].val : null);
    const notes = [];
    if (c.synthetic) notes.push('<div class="banner synth"><span><b>Simulated company.</b> Fictional, generated numbers (not SEC data).</span></div>');
    if (fr.stale && !c.synthetic) notes.push('<div class="banner warn"><span><b>This may be out of date.</b> The latest annual report here was filed ' + fdate(fr.latestFiled) + ' (' + CS.int(fr.daysSinceFiled / 30.4) + ' months before today); a newer one may exist.</span></div>');
    a.warnings.forEach(w => notes.push('<div class="banner warn"><span>' + E(w.message) + '</span></div>'));
    const cov = c.coverage || { found: {}, missing: [] }, checks = c.checks || [];
    const label = k => (c.metrics[k] ? c.metrics[k].label : k);
    const audit = '<details class="box" id="audit"><summary>Data checks and coverage' + (checks.length ? ' <span class="chip">' + checks.length + ' flagged</span>' : ' <span class="chip ok">no flags</span>') + '</summary>' +
      (checks.length ? '<h3>Flagged for a second look (numbers are shown as filed, never altered)</h3><ul>' + checks.map(x => '<li>' + E(x.message) + '</li>').join('') + '</ul>' : '<p class="cap">Automatic checks (balance sheet identity, gross profit arithmetic, filing dates, large revenue jumps) found nothing to flag.</p>') +
      '<h3>What was found</h3><ul>' + Object.keys(cov.found).map(k => '<li><b>' + E(label(k)) + '</b>: ' + cov.found[k].years + ' fiscal year' + (cov.found[k].years === 1 ? '' : 's') + ' from <code>' + cov.found[k].tags.map(E).join('</code>, <code>') + '</code></li>').join('') + '</ul>' +
      (cov.missing.length ? '<h3>Not reported under the standard tags (left blank, never estimated)</h3><ul>' + cov.missing.map(k => '<li>' + E(k in c.metrics ? label(k) : ({ revenue: 'Revenue', costOfRevenue: 'Cost of revenue', grossProfit: 'Gross profit', operatingIncome: 'Operating income', netIncome: 'Net income', epsDiluted: 'Diluted EPS', operatingCashFlow: 'Operating cash flow', capex: 'Capital expenditure', assets: 'Total assets', liabilities: 'Total liabilities', equity: "Shareholders' equity", cash: 'Cash and equivalents', debt: 'Debt' }[k] || k)) + '</li>').join('') + '</ul>' : '') + '</details>';
    const cikLink = c.synthetic ? '' : ' · <a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=' + c.cik + '&type=10-K" target="_blank" rel="noopener">All SEC filings</a>';
    $('detail').innerHTML =
      '<div class="ex-head"><h2><span class="tk">' + E(c.ticker) + '</span><span class="nm">' + E(c.name) + '</span></h2></div>' +
      '<div class="xlinks" id="xlinks" hidden></div>' +
      '<p class="cap" id="fresh">Latest annual report: fiscal year ' + (L == null ? '—' : L) + ', period ended <b>' + fdate(c.latestPeriodEnd) + '</b>, filed <b>' + fdate(c.latestFiled) + '</b> · data compiled ' + fdate((c.generated || '').slice(0, 10)) + ' · amounts in <b>USD ' + sc.name + '</b> except per-share · source: ' + E(c.source) + cikLink + '</p>' +
      '<div class="notes">' + notes.join('') + '</div>' +
      '<div class="metrics">' +
        tile('Revenue · FY' + L, usd(V('revenue', L), sc) + (sc.div === 1e9 ? 'B' : 'M'), r.revenueGrowth == null ? 'Growth needs the previous year' : pct(r.revenueGrowth) + ' vs previous year', dir(r.revenueGrowth)) +
        tile('Revenue CAGR', pct(a.cagr[3]), '3 years' + (a.cagr[5] != null ? ' · 5 years ' + pct(a.cagr[5]) : ' · 5 years not available'), dir(a.cagr[3])) +
        tile('Net margin', plain(r.netMargin), 'Net income ' + usd(V('netIncome', L), sc) + (sc.div === 1e9 ? 'B' : 'M'), dir(r.netMargin)) +
        tile('Operating margin', plain(r.operatingMargin), 'Gross margin ' + plain(r.grossMargin)) +
        tile('Return on equity', plain(r.roe), r.roe == null ? 'Blank: needs positive average equity' : 'Net income ÷ average equity') +
        tile('Debt to equity', r.debtToEquity == null ? '—' : CS.num(r.debtToEquity, 2) + '×', r.debtToEquity == null ? 'Blank: debt or positive equity missing' : 'Net debt ' + usd(r.netDebt, sc) + (sc.div === 1e9 ? 'B' : 'M')) +
        tile('Free cash flow', r.fcf == null ? '—' : usd(r.fcf, sc) + (sc.div === 1e9 ? 'B' : 'M'), r.fcf == null ? 'Blank: needs operating cash flow and capex' : 'FCF margin ' + plain(r.fcfMargin), dir(r.fcf)) +
      '</div>' +
      '<div class="charts">' +
        '<div class="card"><h3>Revenue and net income</h3><p class="cap">USD ' + sc.name + ' by fiscal year.</p><div class="chart-box short"><canvas id="chRev" role="img" aria-label="Revenue and net income by fiscal year"></canvas></div></div>' +
        '<div class="card"><h3>Margins</h3><p class="cap">Share of revenue; a gap in a line means the figure was not reported or not meaningful.</p><div class="chart-box short"><canvas id="chMargin" role="img" aria-label="Margins by fiscal year"></canvas></div></div>' +
        '<div class="card"><h3>Balance sheet</h3><p class="cap">Year-end assets, liabilities, debt and cash.</p><div class="chart-box short"><canvas id="chBal" role="img" aria-label="Balance sheet items by fiscal year"></canvas></div></div>' +
        '<div class="card"><h3>Cash flow</h3><p class="cap">Operating cash flow, capital expenditure and free cash flow.</p><div class="chart-box short"><canvas id="chCash" role="img" aria-label="Cash flow by fiscal year"></canvas></div></div>' +
      '</div>' +
      audit +
      '<div class="card"><h2>Annual figures</h2><p class="cap">' + (c.synthetic ? 'Simulated figures (no filing links).' : 'Each reported figure links to the SEC filing it came from (hover for form, filing date, tag and period).') + ' Blank means not reported or not meaningful. * = derived.</p><div class="table-wrap">' + table(c, a, sc) + '</div></div>';
    drawCharts(c, a, sc);
    if (avail) XLinks.render($('xlinks'), c.ticker, { price: avail.priceSet.has(c.ticker), fund: true, fundSynthetic: avail.fundSynthetic }, 'fundamentals');
    document.title = 'CreditScope · ' + c.ticker + ' fundamentals';
  }

  async function show() {
    const sym = decodeURIComponent(location.hash.slice(1)).toUpperCase();
    if (!/^[A-Z0-9][A-Z0-9.\-]{0,9}$/.test(sym)) {
      $('detail').innerHTML = '<div class="card ex-empty"><h2>Pick a company to begin</h2><p>Search above. You will see revenue, profit, margins, balance sheet and cash flow by fiscal year, with links to the SEC filings.</p></div>';
      return;
    }
    if (!index.some(e => e.s === sym)) { $('detail').innerHTML = '<div class="card ex-empty"><h2>No fundamentals for ' + E(sym) + '</h2><p>This ticker is not in the ' + (synthetic ? 'demonstration' : 'current') + ' data set' + (synthetic ? ', which contains only four fictional companies' : '') + '. Search above for one that is.</p>' + (avail && avail.priceSet.has(sym) ? '<p><a href="explorer.html#' + E(sym) + '">See its price history in the Explorer</a></p>' : '') + '</div>'; return; }
    $('detail').innerHTML = '<div class="card">' + CS.loadingHtml('Loading ' + sym + ' from the data set…') + '</div>';
    try { current = await getJSON(root + 'company/' + encodeURIComponent(sym) + '.json'); render(current); }
    catch (e) { $('detail').innerHTML = CS.errorHtml('Could not load ' + sym + '.', e.message, true); $('detail').querySelector('[data-retry]').addEventListener('click', show); }
  }

  async function start() {
    try {
      try { const d = await getJSON(REAL + 'index.json'); if (!d.entries.length) throw new Error('no real data built yet'); index = d.entries; synthetic = !!d.meta.synthetic; root = REAL; }
      catch (e) { const d = await getJSON(SAMPLE + 'index.json'); index = d.entries; synthetic = true; root = SAMPLE; }
    } catch (e) {
      CS.banner('dataBanner', 'error', '<span><b>Could not load the company list.</b> ' + E(e.message) + '</span>'); CS.doneLoading(); return;
    }
    if (synthetic) $('synthBanner').hidden = false;
    $('heroLead').textContent = 'Search ' + CS.int(index.length) + ' ' + (synthetic ? 'simulated' : 'public') + ' companies and see revenue, profit, margins, assets, debt and cash flow from annual reports' + (synthetic ? '.' : ', with every reported figure linked to the SEC filing it came from.');
    bindSearch();
    XLinks.availability(false).then(a => { avail = a; if (current) XLinks.render($('xlinks'), current.ticker, { price: a.priceSet.has(current.ticker), fund: true, fundSynthetic: a.fundSynthetic }, 'fundamentals'); });
    window.addEventListener('hashchange', show);
    $('themeBtn').addEventListener('click', () => setTimeout(() => current && render(current), 30));
    await show();
    CS.doneLoading();
  }
  start();
})();
