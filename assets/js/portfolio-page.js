/* Portfolio page. All numbers come from portfolio.js / finance.js (verified against independent Python references).
 *
 * Privacy: holdings are never written to any browser storage (local, session, cookies) or the service-worker cache. In the personal
 * edition (the localhost server adds a marker) the ledger is read and written only through /api/portfolio; on the public
 * site the page reads a simulated sample and is read-only.
 */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const E = CS.esc;
  const PERSONAL = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname) && !!document.querySelector('meta[name="creditscope-personal"]');
  const state = { period: 'ITD', mode: 'auto', view: 'real', pf: null, rev: 'new', series: {}, failed: {}, result: null, meta: {} };
  const priv = () => PERSONAL && state.view !== 'sample';      // true while real (private) holdings are on screen
  const hidden = () => state.view === 'hide';                  // hide tickers, names, shares and dollars
  const masked = () => state.view === 'mask' || hidden();      // hide shares and dollars
  const editable = () => priv() && !hidden();
  let alias = {}, names = [];
  const lab = sym => (hidden() && alias[sym] ? alias[sym] : sym);                       // ticker shown on screen
  const clean = text => (hidden() ? Redact.clean(text, alias, names) : String(text == null ? '' : text));
  function buildAlias(r) {
    const syms = (r && r.holdings ? r.holdings.map(h => h.symbol) : []);
    (state.pf.transactions || []).forEach(t => { if (t.symbol) syms.push(t.symbol); });
    syms.push.apply(syms, Object.keys(state.series));
    alias = Redact.aliasMap(syms.filter((x, i) => syms.indexOf(x) === i && x !== (state.pf.benchmark || 'SPY')));
    names = Object.keys(state.series).map(k => state.series[k] && state.series[k].name).filter(Boolean).filter(n => hidden());
  }
  const charts = {};

  /* ---------- data ---------- */
  async function getJSON(url) {
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) { let msg = ''; try { msg = (await res.json()).error || ''; } catch (e) { /* body drained */ } throw new Error(msg || url + ' returned HTTP ' + res.status); }
    return res.json();
  }
  const seriesUrl = s => (priv() ? 'api/series/' + encodeURIComponent(s) : 'explorer/sample/series/' + encodeURIComponent(s) + '.json');
  async function ensureSeries(symbols) {
    await Promise.all(symbols.filter(s => !state.series[s]).map(async s => {
      try { state.series[s] = await getJSON(seriesUrl(s)); delete state.failed[s]; } catch (e) { state.failed[s] = e.message; }
    }));
  }
  const symbolsOf = pf => Array.from(new Set((pf.transactions || []).filter(t => t.type === 'buy').map(t => t.symbol).concat([pf.benchmark || 'SPY'])));

  /* ---------- formatting ---------- */
  const money = (v, d) => (v == null ? '—' : masked() ? '$•••' : (v < 0 && Math.round(Math.abs(v) * 100) > 0 ? '−' : '') + '$' + CS.num(Math.abs(v), d == null ? 2 : d));
  const smoney = v => (v == null ? '—' : masked() ? '$•••' : (v > 0 ? '+' : '') + money(v));
  const pct = (v, d) => (v == null ? '—' : CS.pct(v * 100, d));
  const plain = (v, d) => (v == null ? '—' : (v < 0 && Math.round(Math.abs(v) * 1000) > 0 ? '−' : '') + CS.num(Math.abs(v) * 100, d == null ? 1 : d) + '%');
  const shares = v => masked() ? '•••' : CS.num(v, Math.abs(v - Math.round(v)) < 1e-9 ? 0 : 4);
  const dir = v => CS.dir(v == null ? null : v);
  const tile = (l, v, s, cls, basis) => '<div class="metric"><span class="l">' + l + '</span><span class="v ' + (cls || '') + '">' + v + '</span><span class="s">' + s + '</span></div>';

  /* ---------- render ---------- */
  const color = n => CS.cssVar(n);
  const PALETTE = ['--s1', '--s2', '--s3', '--s4', '--s5', '--s6'];
  const EXTRA = ['--s7', '--s8', '--s-bench'];
  const slice = i => color(i < PALETTE.length ? PALETTE[i] : EXTRA[(i - PALETTE.length) % EXTRA.length]);
  function mkChart(id, cfg) { if (charts[id]) charts[id].destroy(); if ($(id)) charts[id] = new Chart($(id), cfg); }
  const common = () => ({ responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, animation: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? false : { duration: 250 } });
  const tip = cb => ({ backgroundColor: color('--surface-3'), titleColor: color('--text'), bodyColor: color('--text-2'), borderColor: color('--border'), borderWidth: 1, padding: 10, callbacks: cb });
  const xAxis = () => ({ grid: { display: false }, ticks: { maxTicksLimit: window.innerWidth < 560 ? 3 : 6, autoSkip: true, maxRotation: 0 } });
  const yAxis = t => ({ grid: { color: color('--grid') }, title: { display: !!t, text: t || '' } });
  const lineDs = (label, data, c, extra) => Object.assign({ label, data, borderColor: color(c), backgroundColor: color(c), borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.1 }, extra || {});

  const WARN_TEXT = {
    PRICE_BASIS: w => '<b>Price return for both.</b> ' + E(w.message),
    PRICE_GAP_EARLY: w => '<b>Performance starts later than your first transaction.</b> ' + E(w.message),
    NEGATIVE_CASH: w => '<b>Negative cash.</b> ' + E(w.message),
    SPLITS_UNKNOWN: w => '<b>Splits unknown.</b> ' + E(w.message),
    PRICE_STALE: w => '<b>Old price.</b> ' + E(w.message),
    TX_AFTER_END: w => E(w.message), TX_BEFORE_START: w => E(w.message), ZERO_VALUE_DAYS: w => E(w.message)
  };

  function renderSummary(r) {
    const t = r.totals;
    $('asOf').textContent = 'As of the close of ' + CS.date(r.asOf) + ' · prices ' + (state.meta.feed ? 'from the ' + String(state.meta.feed).toUpperCase() + ' feed' : 'simulated') + ' · USD';
    $('summary').innerHTML = [
      tile('Total value', money(t.totalValue), 'Holdings ' + money(t.marketValue, 0) + ' + cash ' + money(t.cash, 0)),
      tile('Unrealized gain', smoney(t.unrealized), (t.unrealizedPct == null ? '' : pct(t.unrealizedPct) + ' on a cost of ') + money(t.costBasis, 0), dir(t.unrealized)),
      tile('Realized gain', smoney(t.realized), 'After fees, first-in first-out', dir(t.realized)),
      tile('Dividends received', money(t.dividends), 'Credited to cash on ex-dates')
    ].join('');
  }

  function renderPerf(r) {
    const p = r.perf[state.period];
    $('periods').innerHTML = Portfolio.PERIODS.map(k => '<button type="button" data-p="' + k + '" aria-pressed="' + (k === state.period) + '">' + (k === 'ITD' ? 'Since start' : k) + '</button>').join('');
    const notes = r.warnings.filter(w => w.code !== 'TX_BEFORE_START').map(w => '<div class="banner warn"><span>' + (WARN_TEXT[w.code] || (x => E(x.message)))(Object.assign({}, w, { message: clean(w.message) })) + '</span></div>');
    if (p && p.truncated) notes.push('<div class="banner warn"><span>Your history is shorter than ' + state.period + ': showing from <b>' + CS.date(p.startDate) + '</b>.</span></div>');
    $('notes').innerHTML = notes.join('');
    if (!p || p.twr === undefined) { $('recon').innerHTML = ''; $('perfTiles').innerHTML = '<p class="cap" style="padding:12px">Not enough history for this period.</p>'; $('perfMore').innerHTML = ''; return; }
    const b = r.basis;
    $('recon').innerHTML =
      '<tr><td>Account value change<small>What the balance did. Includes the money you put in or took out, so it is <b>not</b> a return.</small></td><td class="r ' + dir(p.valueChange) + '">' + smoney(p.valueChange) + '</td></tr>' +
      '<tr><td>− Net contributions<small>Deposits minus withdrawals in the period (outside-funded trades count as deposits).</small></td><td class="r">' + money(p.netFlows) + '</td></tr>' +
      '<tr class="emph"><td>= Investment gain<small>In dollars, after fees' + (b === 'total' ? ', including dividends' : '; dividends are excluded on the price basis') + '.</small></td><td class="r ' + dir(p.investmentGain) + '">' + smoney(p.investmentGain) + '</td></tr>' +
      '<tr><td>Time-weighted return<small>The performance of the investments, independent of when money moved. Compare this with ' + E(r.benchmark) + '.</small></td><td class="r ' + dir(p.twr) + '">' + pct(p.twr) + '</td></tr>' +
      '<tr><td>Modified Dietz return<small>Dollar-weighted estimate: reflects the timing of your own deposits.</small></td><td class="r ' + dir(p.modifiedDietz) + '">' + pct(p.modifiedDietz) + '</td></tr>';
    const dd = p.maxDrawdown || {};
    const more = [];
    $('perfTiles').innerHTML = [
      tile('Return vs ' + E(r.benchmark), p.excess == null ? '—' : (p.excess >= 0 ? '+' : '−') + CS.num(Math.abs(p.excess) * 100, 2) + ' pts', 'Portfolio ' + pct(p.twr) + ' · ' + E(r.benchmark) + ' ' + pct(p.benchmarkReturn), dir(p.excess)),
      tile('Annualized return', pct(p.annualizedTwr), p.annualizedTwr == null ? 'For windows of a year or more' : 'Compound annual rate', dir(p.annualizedTwr)),
      tile('Volatility', plain(p.volatility), p.volatility == null ? 'Needs 20 daily returns' : E(r.benchmark) + ' ' + plain(p.benchmarkVolatility) + ' · annualized', '', p.volatility == null ? null : b),
      tile('Max drawdown', dd.depth == null ? '—' : plain(dd.depth), dd.peakDate ? CS.date(dd.peakDate, true) + ' → ' + CS.date(dd.troughDate, true) + (dd.recoveryDate ? ' · recovered' : ' · not recovered') : 'No decline in this window', '', dd.depth == null ? null : b)
    ].join('');
    $('perfMore').innerHTML = [
      tile('Beta vs ' + E(r.benchmark), CS.dec(p.beta, 2), p.beta == null ? 'Needs 60 daily returns' : 'Sensitivity to ' + E(r.benchmark) + ' (' + p.nReturns + ' returns)'),
      tile('Correlation', CS.dec(p.correlation, 2), 'With ' + E(r.benchmark) + ' daily returns'),
      tile('Fees paid', money(r.totals.fees), 'Trade and account fees')
    ].join('');
  }

  function renderCharts(r) {
    CS.chartDefaults();
    const c = Portfolio.chart(r, state.period); if (!c) return;
    const fmtD = d => CS.date(d, c.dates.length > 260 ? false : true);
    const labels = c.dates.map(fmtD);
    $('chGrowthT').textContent = 'Growth of 100 · portfolio vs ' + r.benchmark;
    $('chGrowthC').textContent = 'Deposits and withdrawals are removed, so this shows investment performance only.';
    mkChart('chGrowth', { type: 'line', data: { labels, datasets: [lineDs('Portfolio', c.twr, '--s1'), lineDs(r.benchmark, c.bench, '--s-bench')] },
      options: Object.assign(common(), { scales: { x: xAxis(), y: yAxis('Growth of 100') }, plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: tip({ label: x => ' ' + x.dataset.label + ': ' + CS.num(x.parsed.y, 2) }) } }) });
    if (masked()) { if (charts.chValue) { charts.chValue.destroy(); delete charts.chValue; } }          // dollar series are never even built while amounts are hidden
    else mkChart('chValue', { type: 'line', data: { labels, datasets: [lineDs('Account value', c.value, '--s1'), lineDs('Net contributions', c.netContributions, '--s-bench', { borderDash: [6, 4], stepped: true })] },
      options: Object.assign(common(), { scales: { x: xAxis(), y: yAxis('USD') }, plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: tip({ label: x => ' ' + x.dataset.label + ': ' + money(x.parsed.y) }) } }) });
    mkChart('chDD', { type: 'line', data: { labels, datasets: [lineDs('Drawdown', c.drawdown, '--down', { fill: true, backgroundColor: color('--down-soft'), borderWidth: 1.5 })] },
      options: Object.assign(common(), { scales: { x: xAxis(), y: yAxis('%') }, plugins: { legend: { display: false }, tooltip: tip({ label: x => ' ' + CS.num(x.parsed.y, 2) + '%' }) } }) });
    const a = r.allocation.bySecurity.filter(x => x.value > 0);
    const share = v => v / r.totals.totalValue * 100;                                 // percentages only: dollar values never reach the chart when amounts are hidden
    mkChart('chAlloc', { type: 'doughnut', data: { labels: a.map(x => lab(x.label)), datasets: [{ data: a.map(x => (masked() ? share(x.value) : x.value)), backgroundColor: a.map((_, i) => slice(i)), borderColor: color('--surface'), borderWidth: 2 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: '58%', animation: false, plugins: { legend: { display: false }, tooltip: tip({ label: x => ' ' + x.label + ': ' + (masked() ? '' : money(x.parsed) + ' (') + CS.num(masked() ? x.parsed : share(x.parsed), 1) + '%' + (masked() ? '' : ')') }) } } });
    $('allocLegend').innerHTML = a.map((x, i) => '<li><i style="background:' + slice(i) + '"></i>' + E(lab(x.label)) + ' ' + CS.num(x.value / r.totals.totalValue * 100, 1) + '%</li>').join('');
  }

  function renderConcentration(r) {
    const c = r.concentration;
    $('conc').innerHTML = [
      tile('Largest holding', plain(c.top1), E(lab(c.largest || '—')) + ' as a share of invested assets'),
      tile('Top 3 / top 5', plain(c.top3, 0) + ' / ' + plain(c.top5, 0), 'Share of invested assets'),
      tile('Herfindahl index', c.hhi ? CS.num(c.hhi, 3) : '—', '0 to 1; the sum of squared weights. Higher is more concentrated'),
      tile('Effective holdings', c.effectiveN ? CS.num(c.effectiveN, 1) : '—', 'Equal-sized positions with the same concentration (of ' + c.positions + ' held)')
    ].join('');
  }

  function renderHoldings(r) {
    $('holdCap').textContent = r.holdings.length + ' position' + (r.holdings.length === 1 ? '' : 's') + ' · first-in first-out lots including buy fees · shares adjusted for splits';
    $('holdBody').innerHTML = r.holdings.map(h => '<tr><td><span class="tk">' + E(lab(h.symbol)) + '</span><br><span class="nm">' + (hidden() ? '' : E(h.name)) + '</span></td>' +
      '<td class="r">' + shares(h.shares) + '</td><td class="r">' + money(h.avgCost) + '</td><td class="r">' + money(h.price) + '<br><small class="nm">' + (h.priceDate ? CS.date(h.priceDate) : '') + '</small></td>' +
      '<td class="r">' + money(h.marketValue) + '</td><td class="r">' + plain(h.weight) + '</td>' +
      '<td class="r ' + dir(h.unrealized) + '">' + smoney(h.unrealized) + '<br><small>' + pct(h.unrealizedPct) + '</small></td>' +
      '<td class="r">' + (h.dividendBasis === 'unknown' ? '<small class="nm">unknown</small>' : money(h.dividendsReceived)) + '</td></tr>').join('') +
      (r.totals.cash > 0.005 ? '<tr><td><span class="tk">Cash</span></td><td></td><td></td><td></td><td class="r">' + money(r.totals.cash) + '</td><td class="r">' + plain(r.totals.cash / r.totals.totalValue) + '</td><td></td><td></td></tr>' : '');
  }

  const WD = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const weekday = iso => WD[new Date(iso + 'T00:00:00Z').getUTCDay()];
  function renderTransactions() {
    const r = state.result, by = {};
    if (r && r.ledger) r.ledger.forEach(e => { by[e.input] = e; });
    const txs = state.pf.transactions.map((t, i) => Object.assign({ i }, t)).sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : b.i - a.i));
    $('txCap').textContent = priv() ? 'Stored privately in a file on this computer, outside the code repository. Nothing is sent anywhere and no brokerage is connected. Each transaction keeps the date you entered; “Applied on” is the trading day the calculations use.'
      : 'Simulated demonstration data, read-only. Entering your own holdings is possible only in the private personal edition running on your computer.';
    $('txForm').hidden = !editable();
    const applied = e => !e ? '' : e.status === 'same_day' ? '<span class="nm">same day</span>' : e.status === 'next_trading_day' ? CS.date(e.effectiveDate) + '<br><small class="nm">next trading day</small>'
      : e.status === 'before_start' ? CS.date(e.effectiveDate) + '<br><small class="nm">first price date</small>' : '<small class="nm">not applied: after the last price</small>';
    $('txBody').innerHTML = txs.map(t => '<tr><td>' + weekday(t.date) + ' ' + CS.date(t.date) + '</td><td>' + applied(by[t.i]) + '</td><td>' + E(t.type) + (t.external ? ' <small class="nm">(outside-funded)</small>' : '') + (t.reinvest ? ' <small class="nm">(reinvested)</small>' : '') + '</td><td class="tk">' + E(lab(t.symbol || '')) + '</td>' +
      '<td class="r">' + (t.shares != null ? shares(t.shares) : '') + '</td><td class="r">' + (t.price != null ? money(t.price) : '') + '</td>' +
      '<td class="r">' + (t.amount != null ? money(t.amount) : t.shares != null ? money(t.shares * t.price + (t.type === 'buy' ? 1 : -1) * (t.fee || 0)) : '') + '</td>' +
      '<td class="r">' + (editable() ? '<button class="rm" type="button" data-i="' + t.i + '" aria-label="Delete this transaction">Delete</button>' : '') + '</td></tr>').join('');
    const sug = r && r.dividendSuggestions || [];
    $('divBar').hidden = !(editable() && sug.length);
    if (sug.length) {
      $('divBtn').textContent = 'Record ' + sug.length + ' dividend' + (sug.length === 1 ? '' : 's') + ' from market data as transactions';
      $('divCap').textContent = 'Total ' + money(sug.reduce((a, d) => a + d.amount, 0)) + ' for shares you held on the ex-dates. Once recorded they become your own entries (you can then reinvest them); automatic crediting stops for those securities.';
    }
  }

  function renderAll() {
    const r = state.result;
    buildAlias(r && !(r.errors && r.errors.length) ? r : null);
    $('app').hidden = false;
    renderTransactions();
    const hasData = r && !(r.errors && r.errors.length);
    if (!hasData) {
      const e = (r && r.errors && r.errors[0]) || { code: 'NONE', message: 'no data' };
      const empty = e.code === 'EMPTY' || !state.pf.transactions.length;
      $('summary').innerHTML = '<div class="ex-empty" style="grid-column:1/-1"><h2>' + (empty ? 'No transactions yet' : 'This ledger cannot be analysed yet') + '</h2><p>' + E(empty ? (PERSONAL ? 'Add a deposit and a buy below, or an existing position marked “funded from outside”.' : 'Nothing to show.') : clean(e.message)) + '</p></div>';
      ['recon', 'perfTiles', 'perfMore', 'conc', 'holdBody', 'allocLegend', 'notes', 'periods'].forEach(id => { $(id).innerHTML = ''; });
      Object.keys(charts).forEach(k => { charts[k].destroy(); delete charts[k]; });
      $('asOf').textContent = ''; $('holdCap').textContent = '';
      return;
    }
    $('chValue').closest('details').hidden = masked();
    $('txPanel').open = $('txPanel').open || (editable() && !state.pf.transactions.length);
    $('modeNote').textContent = r.basisLabel;
    $('modeSel').value = state.mode;
    renderSummary(r); renderPerf(r); renderCharts(r); renderConcentration(r); renderHoldings(r);
  }

  async function analyzeNow() {
    await ensureSeries(symbolsOf(state.pf));
    const r = Portfolio.analyze(state.pf, state.series, { mode: state.mode });
    if (r.errors && r.errors.length) {
      const failed = Object.keys(state.failed);
      if (failed.length && r.errors[0].code === 'NO_PRICES') r.errors[0].message += ' (' + failed.map(s => s + ': ' + state.failed[s]).join('; ') + ')';
    }
    return r;
  }

  /* ---------- editing (personal edition only) ---------- */
  const msg = (text) => { const m = $('txMsg'); m.hidden = !text; m.innerHTML = text ? '<span>' + E(text) + '</span>' : ''; };
  async function commit(newTxs) {
    msg('');
    const pf = Object.assign({}, state.pf, { transactions: newTxs });
    const bad = Portfolio.validate(pf);
    if (bad.length) return msg(bad[0].message + (bad[0].index >= 0 ? ' (transaction ' + (bad[0].index + 1) + ')' : ''));
    const saved = state.pf; state.pf = pf;
    const r = await analyzeNow();
    if (r.errors && r.errors.length && r.errors[0].code !== 'EMPTY') { state.pf = saved; return msg(r.errors[0].message); }
    try {
      const res = await fetch('api/portfolio', { method: 'PUT', cache: 'no-store', headers: { 'Content-Type': 'application/json', 'X-CreditScope': '1' }, body: JSON.stringify({ baseRevision: state.rev, portfolio: pf }) });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) { state.pf = saved; return msg(res.status === 409 ? 'The portfolio changed in another tab. Reload this page and try again.' : (body.details ? body.details[0] : body.error) || 'Could not save.'); }
      state.rev = body.revision; state.result = r; renderAll();
    } catch (e) { state.pf = saved; msg('Could not reach the local server: ' + e.message); }
  }
  const newId = () => 't' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
  function syncForm() {
    const type = $('fType').value;
    document.querySelectorAll('#txForm [data-for]').forEach(el => { el.hidden = el.dataset.for.split(' ').indexOf(type) < 0; });
  }
  function bindControls() {
    $('modeSel').addEventListener('change', async () => { state.mode = $('modeSel').value; syncHash(); state.result = await analyzeNow(); renderAll(); });
    $('divBtn').addEventListener('click', () => {
      const sug = state.result.dividendSuggestions;
      if (!sug.length || !window.confirm('Add ' + sug.length + ' dividend transactions?')) return;
      commit(state.pf.transactions.concat(sug.map(d => ({ id: newId(), date: d.date, type: 'dividend', symbol: d.symbol, amount: Math.round(d.amount * 100) / 100, group: 'mkt' }))));
    });
    $('viewSel').addEventListener('change', () => { state.view = $('viewSel').value; syncHash(); location.reload(); });
  }
  function bindForm() {
    $('fType').addEventListener('change', syncForm); syncForm();
    $('fDate').value = new Date().toISOString().slice(0, 10);
    $('fExternal').checked = !state.pf.transactions.some(t => t.type === 'deposit');
    $('txForm').addEventListener('submit', e => {
      e.preventDefault();
      const type = $('fType').value, t = { id: newId(), date: $('fDate').value, type };
      const n = id => (document.getElementById(id).value === '' ? NaN : Number(document.getElementById(id).value));
      if (['buy', 'sell', 'dividend', 'drip'].indexOf(type) >= 0) t.symbol = $('fSymbol').value.trim().toUpperCase();
      if (type === 'drip') {
        const g = 'g' + Math.random().toString(36).slice(2, 8), sym = $('fSymbol').value.trim().toUpperCase();
        const div = { id: newId(), date: t.date, type: 'dividend', symbol: sym, amount: n('fAmount'), group: g };
        const buy = { id: newId(), date: t.date, type: 'buy', symbol: sym, shares: n('fShares'), price: n('fPrice'), fee: 0, external: false, reinvest: true, group: g };
        return commit(state.pf.transactions.concat([div, buy]));
      }
      if (type === 'buy' || type === 'sell') { t.shares = n('fShares'); t.price = n('fPrice'); t.fee = $('fFee').value === '' ? 0 : n('fFee'); t.external = $('fExternal').checked; }
      else t.amount = n('fAmount');
      commit(state.pf.transactions.concat([t])).then(() => { if (!$('txMsg').hidden) return; ['fShares', 'fPrice', 'fAmount', 'fSymbol'].forEach(id => { $(id).value = ''; }); });
    });
    $('txBody').addEventListener('click', e => {
      const b = e.target.closest('button.rm'); if (!b) return;
      const t = state.pf.transactions[+b.dataset.i];
      if (t && window.confirm('Delete this ' + t.type + (t.symbol ? ' of ' + t.symbol : '') + ' on ' + t.date + '?')) commit(state.pf.transactions.filter((_, i) => i !== +b.dataset.i));
    });
  }

  /* ---------- address-bar state: period, benchmark methodology and view only (never holdings) ---------- */
  function parseHash() {
    const q = new URLSearchParams(location.hash.slice(1).replace(/^(\w+)$/, 'p=$1'));
    if (Portfolio.PERIODS.indexOf(q.get('p')) >= 0) state.period = q.get('p');
    if (Portfolio.MODES.indexOf(q.get('mode')) >= 0) state.mode = q.get('mode');
    if (['real', 'mask', 'hide', 'sample'].indexOf(q.get('view')) >= 0 && PERSONAL) state.view = q.get('view');
  }
  function syncHash() {
    const q = new URLSearchParams(); q.set('p', state.period);
    if (state.mode !== 'auto') q.set('mode', state.mode);
    if (state.view !== 'real') q.set('view', state.view);
    history.replaceState(null, '', '#' + q.toString());
  }

  /* ---------- start ---------- */
  async function start() {
    $('periods').addEventListener('click', e => {
      const b = e.target.closest('button[data-p]'); if (!b || !state.result || !state.result.perf) return;
      state.period = b.dataset.p; syncHash(); renderPerf(state.result); renderCharts(state.result);
    });
    parseHash();
    window.addEventListener('hashchange', () => location.reload());
    $('themeBtn').addEventListener('click', () => setTimeout(() => state.result && !(state.result.errors && state.result.errors.length) && renderCharts(state.result), 30));
    try {
      if (PERSONAL) { $('viewBar').hidden = false; $('viewSel').value = state.view; }
      if (priv()) {
        const r = await getJSON('api/portfolio'); state.pf = r.portfolio; state.rev = r.revision;
        try { state.meta = (await getJSON('private-data/index.json')).meta || {}; } catch (e) { state.meta = {}; }
        const f = String(state.meta.feed || '').toLowerCase();
        $('privateBanner').hidden = false;
        $('privateBanner').firstElementChild.innerHTML = hidden()
          ? '<b>Tickers, company names, share counts and dollar amounts are hidden.</b> Securities appear as “Holding A, B, …” and risk statistics are unchanged. Percentages, weights, transaction dates and per-holding returns are still real, so this is safer for screenshots but is <b>not anonymous</b>.'
          : masked()
          ? '<b>Dollar amounts and share counts are hidden.</b> Percentages, symbols and weights are still real, so this is safer for screenshots but is <b>not anonymous</b>. Use “Show the simulated sample instead” to hide holdings entirely.'
          : '<b>Private: real holdings, local only.</b> Your ledger is stored outside the code repository and served to this computer only; it is never published, cached offline or put in browser storage. Do not screenshot or screen-share this page; use the View menu for a safe version.';
        if (f === 'iex' || !f) $('privateBanner').firstElementChild.innerHTML += ' <b>Prices come from the IEX feed (one exchange).</b> Trade-price returns track the market closely, but <b>volume is not shown here</b>: IEX volume is a small fraction of consolidated market volume.';
      } else {
        state.pf = await getJSON('explorer/sample/portfolio.json');
        state.meta = (await getJSON('explorer/sample/index.json')).meta || {};
        $('synthBanner').hidden = false;
      }
    } catch (e) {
      CS.banner('dataBanner', 'error', '<span><b>Could not load the portfolio.</b> ' + E(clean(e.message)) + (PERSONAL ? ' Run <code>python3 -m personal serve</code> again, and check <code>~/.creditscope/portfolio.json</code>.' : '') + '</span>');
      CS.doneLoading(); return;
    }
    state.result = await analyzeNow();
    renderAll();
    bindControls();
    if (PERSONAL) bindForm();
    CS.doneLoading();
  }
  start();
})();
