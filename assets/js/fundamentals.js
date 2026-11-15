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
  const scales = t => ({ x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: window.innerWidth < 560 ? 4 : 6 } }, y: { grid: { color: color('--grid') }, title: { display: false } } });
  const legend = { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } };

  function drawCharts(c, a, sc) {
    CS.chartDefaults();
    const ys = a.years, labels = ys.map(y => 'FY' + y);
    const V = (k, y) => (a.values[k] && a.values[k][y] ? a.values[k][y].val : null);
    const series = (k, f) => ys.map(y => { const v = f ? f(y) : V(k, y); return v == null ? null : v / sc.div; });
    const bar = (label, data, c1) => ({ label, data, backgroundColor: color(c1), borderWidth: 0 });
    const line = (label, data, c1) => ({ label, data, borderColor: color(c1), backgroundColor: color(c1), borderWidth: 2, pointRadius: 3, pointHoverRadius: 5, tension: 0.1, spanGaps: false });
    const usdTip = tip({ label: x => ' ' + x.dataset.label + ': ' + (x.parsed.y == null ? 'not reported' : sign(x.parsed.y) + '$' + CS.num(Math.abs(x.parsed.y), 2) + ' ' + sc.name) });
    mk('chRev', { type: 'bar', data: { labels, datasets: [bar('Revenue', series('revenue'), '--s1'), bar('Net income', series('netIncome'), '--s3')] }, options: Object.assign(common(), { scales: scales('USD ' + sc.name), plugins: { legend, tooltip: usdTip } }) });
    const pctTip = tip({ label: x => ' ' + x.dataset.label + ': ' + (x.parsed.y == null ? 'not available' : CS.dec(x.parsed.y, 1) + '%') });
    const r = (k) => ys.map(y => (a.ratios[y][k] == null ? null : a.ratios[y][k] * 100));
    const noGPc = !!(c.coverage && c.coverage.suppressed && c.coverage.suppressed.grossProfit);
    const marginSets = c.profile === 'bank' ? [line('Net margin', r('netMargin'), '--s3'), line('Return on equity', r('roe'), '--s1')]
      : (noGPc ? [] : [line('Gross margin', r('grossMargin'), '--s1')]).concat([line('Operating margin', r('operatingMargin'), '--s2'), line('Net margin', r('netMargin'), '--s3'), line('Free-cash-flow margin', r('fcfMargin'), '--s4')]);
    mk('chMargin', { type: 'line', data: { labels, datasets: marginSets }, options: Object.assign(common(), { scales: scales('% of revenue'), plugins: { legend, tooltip: pctTip } }) });
    mk('chBal', { type: 'bar', data: { labels, datasets: [bar('Total assets', series('assets'), '--s1'), bar('Total liabilities', series('liabilities'), '--s2')].concat(c.profile === 'bank' ? [] : [bar('Debt', series('debt'), '--s4')]).concat(c.coverage && c.coverage.definitions && c.coverage.definitions.cash ? [] : [bar('Cash', series('cash'), '--s3')]) }, options: Object.assign(common(), { scales: scales('USD ' + sc.name), plugins: { legend, tooltip: usdTip } }) });
    mk('chCash', { type: 'bar', data: { labels, datasets: c.profile === 'bank' ? [bar('Operating cash flow', series('operatingCashFlow'), '--s3')] : [bar('Operating cash flow', series('operatingCashFlow'), '--s3'), bar('Capital expenditure', series('capex'), '--s2'), bar('Free cash flow', series(null, y => a.ratios[y].fcf), '--s1')] }, options: Object.assign(common(), { scales: scales('USD ' + sc.name), plugins: { legend, tooltip: usdTip } }) });
  }

  /* ---------- table ---------- */
  function table(c, a, sc) {
    const ys = a.years.slice(-10);
    const bank = c.profile === 'bank', noGP = !!(c.coverage && c.coverage.suppressed && c.coverage.suppressed.grossProfit);
    const defs = (c.coverage && c.coverage.definitions) || {};
    const runIdx = (k, y) => defs[k] ? defs[k].findIndex(r => y >= r.fromFy && y <= r.toFy) : -1;
    const dagger = (k, y) => (defs[k] && runIdx(k, y) !== defs[k].length - 1 && runIdx(k, y) >= 0) ? '<sup title="Different definition from the latest year: see the note under the table">†</sup>' : '';
    const oc = i => (i < ys.length - 6 ? ' old' : '');
    const head = '<tr><th class="sticky" scope="col">USD ' + sc.name + ' unless noted</th>' + ys.map((y, i) => {
      const p = ['revenue', 'netIncome', 'assets'].map(k => a.values[k] && a.values[k][y]).find(Boolean);
      const len = p && p.start ? Math.round((Date.UTC(+p.end.slice(0, 4), +p.end.slice(5, 7) - 1, +p.end.slice(8, 10)) - Date.UTC(+p.start.slice(0, 4), +p.start.slice(5, 7) - 1, +p.start.slice(8, 10))) / 864e5) : 0;
      return '<th class="r' + oc(i) + '" scope="col">FY' + y + '<small>ends ' + (p ? fdate(p.end) : '—') + (len > 370 || (len && len < 360) ? '<br>' + Math.round(len / 7) + '-week year' : '') + '</small></th>';
    }).join('') + '</tr>';
    const cell = (k, y, fmt) => {
      const i = ys.indexOf(y);
      const p = a.values[k] && a.values[k][y];
      if (!p) return '<td class="r na' + oc(i) + '" title="Not reported by the company under the tags read">—</td>';
      const txt = fmt(p.val);
      const tipText = p.form + ' filed ' + p.filed + ' · ' + p.tag + (p.start ? ' · period ' + p.start + ' to ' + p.end : ' · at ' + p.end);
      return '<td class="r' + oc(i) + '">' + (synthetic ? '<span title="Simulated filing reference ' + E(p.accn) + '">' + txt + '</span>'
        : '<a href="' + FundCalc.filingUrl(c.cik, p.accn) + '" target="_blank" rel="noopener" title="' + E(tipText) + '">' + txt + '</a>') + dagger(k, y) + '</td>';
    };
    const calc = (k, y, fmt, note) => { const v = a.ratios[y][k]; return '<td class="r' + (v == null ? ' na' : '') + oc(ys.indexOf(y)) + '"' + (note && a.ratios[y][note] ? ' title="Derived: revenue minus cost of revenue"' : '') + '>' + (v == null ? '—' : fmt(v)) + (note && a.ratios[y][note] && v != null ? '*' : '') + '</td>'; };
    const m = v => usd(v, sc), eps = v => sign(v) + '$' + CS.num(Math.abs(v), 2);
    const rows = [];
    const grp = t => rows.push('<tr class="grp"><td class="sticky" colspan="' + (ys.length + 1) + '">' + t + '</td></tr>');
    const rep = (label, k, fmt) => { if (a.values[k]) rows.push('<tr><td class="sticky">' + label + '</td>' + ys.map(y => cell(k, y, fmt || m)).join('') + '</tr>'); };
    const der = (label, k, fmt, note) => rows.push('<tr><td class="sticky">' + label + '</td>' + ys.map(y => calc(k, y, fmt, note)).join('') + '</tr>');
    grp('Income statement'); rep(bank ? 'Net revenue' : 'Revenue', 'revenue');
    if (!bank) {
      rep('Cost of revenue', 'costOfRevenue');
      if (!noGP) rows.push('<tr><td class="sticky">Gross profit</td>' + ys.map(y => (a.values.grossProfit && a.values.grossProfit[y]) ? cell('grossProfit', y, m) : calc('grossProfit', y, m, 'grossProfitDerived')).join('') + '</tr>');
      rep('Operating income', 'operatingIncome');
    }
    rep('Net income', 'netIncome'); rep('Diluted EPS (USD per share)', 'epsDiluted', eps);
    grp('Balance sheet'); rep('Total assets', 'assets'); rep('Total liabilities', 'liabilities'); rep("Shareholders' equity", 'equity'); rep(defs.cash ? 'Cash (definition changes) †' : 'Cash and equivalents', 'cash'); if (!bank) rep('Debt', 'debt');
    grp('Cash flow'); rep(defs.operatingCashFlow ? 'Operating cash flow †' : 'Operating cash flow', 'operatingCashFlow'); if (!bank) { rep('Capital expenditure', 'capex'); der('Free cash flow (derived)', 'fcf', m); }
    grp('Growth and profitability (derived)'); der('Revenue growth', 'revenueGrowth', v => pct(v));
    if (!bank) { if (!noGP) der('Gross margin', 'grossMargin', v => plain(v)); der('Operating margin', 'operatingMargin', v => plain(v)); }
    der('Net margin', 'netMargin', v => plain(v));
    if (!bank) der('FCF margin', 'fcfMargin', v => plain(v));
    der('Return on equity', 'roe', v => plain(v)); der('Return on assets', 'roa', v => plain(v));
    grp('Leverage (derived)'); if (!bank) { der('Debt to equity', 'debtToEquity', v => CS.num(v, 2) + '×'); der('Net debt (debt − cash)', 'netDebt', m); } der('Liabilities to assets', 'liabilitiesToAssets', v => plain(v));
    const more = ys.length > 6 ? '<p class="fd-years"><button type="button" class="btn" id="fdAllYears" aria-expanded="false" aria-controls="fdTable">Show all ' + ys.length + ' years</button><span class="cap"> Showing the latest 6 of ' + ys.length + ' fiscal years.</span></p>' : '';
    return more + '<table id="fdTable" class="t fd-table"><caption class="sr-only">Annual figures reported to the SEC and ratios derived from them</caption><thead>' + head + '</thead><tbody>' + rows.join('') + '</tbody></table>' + notesBelow(c, defs, bank);
  }
  function notesBelow(c, defs, bank) {
    const out = [];
    Object.keys(defs).forEach(k => out.push('<p class="cap"><b>† ' + E((c.metrics[k] && c.metrics[k].label) || k) + ' is not one continuous series.</b> ' + defs[k].map(r => 'FY' + r.fromFy + (r.toFy !== r.fromFy ? '–FY' + r.toFy : '') + ': ' + E(r.meaning)).join('; ') + '. Compare years only within the same definition.</p>'));
    if (bank) out.push('<p class="cap"><b>Not shown for a bank:</b> cost of revenue, gross profit, operating income, capital expenditure, free cash flow, net debt, debt to equity and the margins built from them. Interest is a bank\'s operating cost and deposits are its funding, so these measures do not mean what they mean for other companies. Revenue is the total net revenue the bank reports.</p>');
    return out.join('');
  }

  /* ---------- page ---------- */
  const tile = (l, v, s, cls) => '<div class="metric"><span class="l">' + l + '</span><span class="v ' + (cls || '') + '">' + v + '</span><span class="s">' + s + '</span></div>';

  function render(c) {
    const a = FundCalc.analyze(c), sc = scaleFor(c), fr = FundCalc.freshness(c, today());
    const L = a.latestFiscalYear, r = L != null ? a.ratios[L] : {}, V = (k, y) => (a.values[k] && a.values[k][y] ? a.values[k][y].val : null);
    const notes = [], bank = c.profile === 'bank';
    if (bank) notes.push('<div class="banner"><span><b>Analysed as a bank.</b> ' + E(c.name) + ' reports like a bank (' + E(c.profileReason || '') + '), so industrial measures such as gross profit, operating margin and free cash flow are not shown rather than estimated.</span></div>');
    const stale = (c.coverage && c.coverage.stale) || {};
    Object.keys(stale).forEach(k => notes.push('<div class="banner warn"><span><b>' + E(stale[k].label) + ' is not shown.</b> The company last reported it for FY' + stale[k].lastFy + ' (tag ' + E(stale[k].tag) + ') but its other figures run to FY' + stale[k].companyLatestFy + ', so it is not presented as current.</span></div>'));
    if (fr.stale && !c.synthetic) notes.push('<div class="banner warn"><span><b>This may be out of date.</b> The latest annual report here was filed ' + fdate(fr.latestFiled) + ' (' + CS.int(fr.daysSinceFiled / 30.4) + ' months before today); a newer one may exist.</span></div>');
    const sup = (c.coverage && c.coverage.suppressed) || {}, noGP = !!sup.grossProfit;
    if (noGP) a.years.forEach(y => { a.ratios[y].grossMargin = null; });
    a.warnings.filter(w => !(noGP && w.code === 'DERIVED_GROSS_PROFIT')).forEach(w => notes.push('<div class="banner warn"><span>' + E(w.message) + '</span></div>'));
    const cov = c.coverage || { found: {}, missing: [], stale: {} }, checks = c.checks || [];
    const label = k => (c.metrics[k] ? c.metrics[k].label : k);
    const audit = '<details class="box" id="audit"><summary>Data checks and coverage' + (checks.length ? ' <span class="chip">' + checks.length + ' flagged</span>' : ' <span class="chip ok">no flags</span>') + '</summary>' +
      (checks.length ? '<h3>Flagged for a second look (numbers are shown as filed, never altered)</h3><ul>' + checks.map(x => '<li>' + E(x.message) + '</li>').join('') + '</ul>' : '<p class="cap">Automatic checks (balance sheet identity, gross profit arithmetic, filing dates, large revenue jumps, stale or gapped series, definition changes) found nothing to flag.</p>') +
      '<h3>What was found</h3><ul>' + Object.keys(cov.found).map(k => '<li><b>' + E(label(k)) + '</b>: ' + cov.found[k].years + ' fiscal year' + (cov.found[k].years === 1 ? '' : 's') + ' from <code>' + cov.found[k].tags.map(E).join('</code>, <code>') + '</code></li>').join('') + '</ul>' +
      (c.coverage && c.coverage.balanceSheetBasis ? '<h3>Balance sheet basis</h3><p class="cap">' + E(c.coverage.balanceSheetBasis) + '</p>' : '') +
      (Object.keys(cov.stale || {}).length ? '<h3>Not shown because it stopped being reported</h3><ul>' + Object.keys(cov.stale).map(k => { const d = cov.stale[k]; return '<li><b>' + E(d.label) + '</b>: last reported for FY' + d.lastFy + ' (' + usd(d.val, sc) + (sc.div === 1e9 ? 'B' : 'M') + ', tag ' + E(d.tag) + ', filed ' + E(d.filed || '') + '); the company reports through FY' + d.companyLatestFy + '.</li>'; }).join('') + '</ul>' : '') +
      (cov.missing.length ? '<h3>Not reported under the standard tags (left blank, never estimated)</h3><ul>' + cov.missing.map(k => '<li>' + E(k in c.metrics ? label(k) : ({ revenue: 'Revenue', costOfRevenue: 'Cost of revenue', grossProfit: 'Gross profit', operatingIncome: 'Operating income', netIncome: 'Net income', epsDiluted: 'Diluted EPS', operatingCashFlow: 'Operating cash flow', capex: 'Capital expenditure', assets: 'Total assets', liabilities: 'Total liabilities', equity: "Shareholders' equity", cash: 'Cash and equivalents', debt: 'Debt' }[k] || k)) + '</li>').join('') + '</ul>' : '') + '</details>';
    const v = c.verification, lim = c.limitations || [];
    const provenance = c.synthetic ? '' : '<details class="box" id="provenance" open><summary>Source, verification and limitations</summary><ul>' +
      '<li><b>Source:</b> SEC EDGAR annual reports (Form 10-K), reduced by CreditScope from the SEC\'s structured data. Each figure in the table links to the filing it came from.</li>' +
      '<li><b>Latest fiscal period:</b> FY' + (L == null ? '—' : L) + ' ended ' + fdate(c.latestPeriodEnd) + '; the annual report was filed ' + fdate(c.latestFiled) + '. <b>Data refreshed:</b> ' + fdate((c.generated || '').slice(0, 10)) + '.</li>' +
      (v ? '<li><b>Checked against the printed filing:</b> ' + E(v.scope) + ' Checked on ' + fdate(v.checkedOn) + (v.accn ? ' (<a href="' + FundCalc.filingUrl(c.cik, v.accn) + '" target="_blank" rel="noopener">filing</a>)' : '') + '.</li><li><b>Not manually verified:</b> ' + E(v.unverified) + '</li>'
         : '<li><b>Not manually verified:</b> these figures come from the SEC\'s structured data and passed automatic checks only; they have not been compared with the printed filings.</li>') +
      lim.map(x => '<li><b>Note:</b> ' + E(x) + '</li>').join('') +
      (sup.grossProfit ? '<li><b>Not shown:</b> ' + E(sup.grossProfit) + '</li>' : '') + '</ul></details>';
    const cikLink = c.synthetic ? '' : ' · <a href="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=' + c.cik + '&type=10-K" target="_blank" rel="noopener">All SEC filings</a>';
    $('detail').innerHTML =
      '<div class="ex-head"><h2><span class="tk">' + E(c.ticker) + '</span><span class="nm">' + E(c.name) + '</span></h2></div>' +
      '<div class="xlinks" id="xlinks" hidden></div>' +
      '<p class="cap" id="fresh">FY' + (L == null ? '—' : L) + ' ended <b>' + fdate(c.latestPeriodEnd) + '</b> · filed <b>' + fdate(c.latestFiled) + '</b> · compiled ' + fdate((c.generated || '').slice(0, 10)) + ' · USD ' + sc.name + ' except per share · ' + (c.synthetic ? 'simulated data' : 'SEC EDGAR') + cikLink + '</p>' +
      '<div class="notes">' + notes.join('') + '</div>' + provenance +
      (bank ? '<div class="metrics" aria-label="Key figures">' +
        tile('Net revenue · FY' + L, usd(V('revenue', L), sc) + (sc.div === 1e9 ? 'B' : 'M'), r.revenueGrowth == null ? 'Growth needs the previous year' : pct(r.revenueGrowth) + ' year over year', dir(r.revenueGrowth)) +
        tile('Net margin', plain(r.netMargin), 'Net income ' + usd(V('netIncome', L), sc) + (sc.div === 1e9 ? 'B' : 'M'), dir(r.netMargin)) +
        tile('Return on equity', plain(r.roe), r.roe == null ? 'Blank: needs positive average equity' : 'Net income ÷ average equity') +
        tile('Return on assets', plain(r.roa), 'Net income ÷ average assets') + '</div>' :
      '<div class="metrics" aria-label="Key figures">' +
        tile('Revenue · FY' + L, usd(V('revenue', L), sc) + (sc.div === 1e9 ? 'B' : 'M'), r.revenueGrowth == null ? 'Growth needs the previous year' : pct(r.revenueGrowth) + ' year over year', dir(r.revenueGrowth)) +
        tile('Operating margin', plain(r.operatingMargin), (noGP ? 'Gross margin not shown' : 'Gross margin ' + plain(r.grossMargin))) +
        tile('Net margin', plain(r.netMargin), 'Net income ' + usd(V('netIncome', L), sc) + (sc.div === 1e9 ? 'B' : 'M'), dir(r.netMargin)) +
        tile('Free cash flow', r.fcf == null ? '—' : usd(r.fcf, sc) + (sc.div === 1e9 ? 'B' : 'M'), r.fcf == null ? 'Blank: needs operating cash flow and capex' : 'FCF margin ' + plain(r.fcfMargin), dir(r.fcf)) +
      '</div>') +
      '<details class="more"><summary>More ratios</summary><div class="metrics" aria-label="More ratios">' +
        tile('Revenue CAGR', pct(a.cagr[3]), '3 years' + (a.cagr[5] != null ? ' · 5 years ' + pct(a.cagr[5]) : ' · 5 years not available'), dir(a.cagr[3])) +
        (bank ? tile('Liabilities to assets', plain(r.liabilitiesToAssets), 'Balance sheet leverage') : tile('Return on equity', plain(r.roe), r.roe == null ? 'Blank: needs positive average equity' : 'Net income ÷ average equity') +
        tile('Debt to equity', r.debtToEquity == null ? '—' : CS.num(r.debtToEquity, 2) + '×', r.debtToEquity == null ? 'Blank: debt or positive equity missing' : 'Net debt ' + usd(r.netDebt, sc) + (sc.div === 1e9 ? 'B' : 'M'))) +
      '</div></details>' +
      '<div class="charts two">' +
        '<div class="card"><h3>Revenue and net income</h3><p class="cap">USD ' + sc.name + ' by fiscal year.</p><div class="chart-box short"><canvas id="chRev" role="img" aria-label="Revenue and net income by fiscal year"></canvas></div></div>' +
        '<div class="card"><h3>Margins</h3><p class="cap">Share of revenue; a gap in a line means the figure was not reported or not meaningful.</p><div class="chart-box short"><canvas id="chMargin" role="img" aria-label="Margins by fiscal year"></canvas></div></div>' +
        '<div class="card"><h3>Balance sheet</h3><p class="cap">Year-end balances, USD ' + sc.name + '.' + (c.coverage && c.coverage.definitions && c.coverage.definitions.cash ? ' Cash is left out of this chart because its definition changes over time (see the table).' : '') + (bank ? ' Debt is not shown for a bank.' : '') + '</p><div class="chart-box short"><canvas id="chBal" role="img" aria-label="Balance sheet items by fiscal year"></canvas></div></div>' +
        '<div class="card"><h3>Cash flow</h3><p class="cap">USD ' + sc.name + ': operating cash flow, capital expenditure and free cash flow.</p><div class="chart-box short"><canvas id="chCash" role="img" aria-label="Cash flow by fiscal year"></canvas></div></div>' +
      '</div>' +
      audit +
      '<div class="card"><h2>Annual figures</h2><p class="cap">' + (c.synthetic ? 'Simulated figures (no filing links).' : 'Each reported figure links to the SEC filing it came from (hover for form, filing date, tag and period).') + ' Blank means not reported or not meaningful. * = derived.</p><div class="table-wrap">' + table(c, a, sc) + '</div></div>';
    drawCharts(c, a, sc);
    const yb = $('fdAllYears');
    if (yb) yb.addEventListener('click', () => { const t = $('fdTable'); const on = t.classList.toggle('all'); yb.setAttribute('aria-expanded', on); yb.textContent = on ? 'Show latest 6 years' : 'Show all ' + a.years.slice(-10).length + ' years'; yb.parentNode.querySelector('.cap').textContent = on ? ' Showing all fiscal years.' : ' Showing the latest 6 of ' + a.years.slice(-10).length + ' fiscal years.'; });
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
