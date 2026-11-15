/* Trends page. Every figure is computed in the browser from data/history.csv (see stats.js);
 * the text of each finding is generated from those figures, so it changes as the history grows. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const E = CS.esc;
  // each ETF keeps one colour slot (the validated categorical order); stocks are solid lines and bonds dashed, so six colours serve twelve ETFs
  const SLOT = { SPY: 1, QQQ: 2, IWM: 3, EFA: 4, EEM: 5, XLF: 6, SHY: 1, IEF: 2, TLT: 3, AGG: 4, LQD: 5, HYG: 6 };
  const colorOf = id => CS.cssVar('--s' + (SLOT[id] || 1));
  const charts = {};
  let rows = [], report = null, byItem = null, classOf = {}, ids = [];
  let ex = { value: 'rebased', picked: ['SPY', 'QQQ', 'TLT', 'HYG'] };

  /* ---------- text helpers ---------- */
  const sg = v => '<b class="' + CS.dir(v) + '">' + CS.pct(v) + '</b>';
  const plural = (n, w) => n + ' ' + w + (n === 1 ? '' : 's');
  const dayLabel = sd => CS.weekday(sd) + ' ' + CS.date(sd);

  /* ---------- chart plumbing ---------- */
  function setDefaults() {
    CS.chartDefaults();
    Chart.defaults.animation = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? false : { duration: 350 };
  }
  function make(id, config) {
    if (charts[id]) charts[id].destroy();
    const el = $(id); if (!el) return;
    charts[id] = new Chart(el, config);
  }
  const grid = () => ({ color: CS.cssVar('--grid') });
const tickPct = v => (Math.round(v * 100) / 100) + '%';
  const tooltip = extra => Object.assign({ backgroundColor: CS.cssVar('--surface-3'), titleColor: CS.cssVar('--text'), bodyColor: CS.cssVar('--text-2'), borderColor: CS.cssVar('--border'), borderWidth: 1, padding: 10 }, extra || {});

  /* ---------- explorer ---------- */
  function exSeries(id) {
    const list = byItem.get(id) || [];
    const first = list.find(o => o.price != null);
    return report.meta.session_dates.map(sd => {
      const o = list.find(x => x.sd === sd);
      if (!o) return null;
      if (ex.value === 'rebased') return o.price != null && first ? o.price / first.price * 100 : null;
      return o[ex.value];
    });
  }
  const EX_LABEL = { rebased: 'Rebased price (first session = 100)', price: 'Price (USD)', volume: 'Volume (shares)', net_change: 'Net change (USD)', pct_change: 'Daily change (%)' };
  function exFormat(v) {
    if (v == null) return '—';
    if (ex.value === 'volume') return CS.compact(v);
    if (ex.value === 'pct_change') return CS.pct(v);
    if (ex.value === 'price') return CS.money(v);
    return CS.num(v, 2);
  }
  function drawExplorer() {
    const labels = report.meta.session_dates;
    const datasets = ex.picked.filter(id => ids.indexOf(id) >= 0).map(id => ({
      label: id, data: exSeries(id), borderColor: colorOf(id), backgroundColor: colorOf(id),
      borderDash: classOf[id] === 'Bond' ? [6, 4] : [], borderWidth: 2, pointRadius: labels.length > 25 ? 0 : 3, pointHoverRadius: 5, tension: 0.15, spanGaps: true
    }));
    $('exNote').textContent = datasets.length
      ? EX_LABEL[ex.value] + ' · ' + datasets.length + ' ETF' + (datasets.length === 1 ? '' : 's') + ' · ' + plural(labels.length, 'trading session') + (labels.length < 2 ? '. A line needs at least two sessions; points show what exists so far.' : '. Stocks are solid lines, bonds dashed.')
      : 'Pick at least one ETF above to draw the chart.';
    make('exChart', {
      type: 'line', data: { labels: labels.map(sd => CS.date(sd, true)), datasets },
      options: {
        responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
        scales: { x: { grid: grid() }, y: { grid: grid(), title: { display: true, text: EX_LABEL[ex.value] }, ticks: { callback: v => (ex.value === 'volume' ? CS.compact(v) : ex.value === 'pct_change' ? tickPct(v) : Math.round(v * 100) / 100) } } },
        plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: tooltip({ callbacks: { label: c => ' ' + c.dataset.label + ': ' + exFormat(c.parsed.y) } }) }
      }
    });
  }
  function drawPick() {
    $('exPick').innerHTML = ids.map(id => '<button type="button" class="' + (classOf[id] || '').toLowerCase() + '" data-id="' + E(id) + '" aria-pressed="' + (ex.picked.indexOf(id) >= 0) + '">' + E(id) + '</button>').join('');
    document.querySelectorAll('[data-grp]').forEach(b => {
      const g = b.dataset.grp;
      const want = g === 'all' ? ids : g === 'none' ? [] : ids.filter(i => classOf[i] === g);
      b.setAttribute('aria-pressed', String(want.length === ex.picked.length && want.every(i => ex.picked.indexOf(i) >= 0) && (g !== 'none' || !ex.picked.length)));
    });
  }

  /* ---------- findings ---------- */
  function section(n, id, title, bodyHtml, chartId, tall, pill) {
    return '<section class="finding" id="' + id + '"><div class="no">FINDING 0' + n + (pill ? '<span class="pill">' + pill + '</span>' : '') + '</div><h2>' + title + '</h2>' + bodyHtml +
      (chartId ? '<div class="card chart-card"><div class="chart-box' + (tall ? ' tall' : '') + '"><canvas id="' + chartId + '" role="img" aria-label="Chart for finding ' + n + '"></canvas></div></div>' : '') + '</section>';
  }
  const how = t => '<p class="how"><b>How it is computed:</b> ' + t + '</p>';
  const why = t => '<details class="why"><summary>Why it matters</summary><p class="sig">' + t + '</p></details>';

  function finding1() {
    const R = report.returns, m = report.meta;
    if (R.length) {
      const best = R[0], worst = R[R.length - 1];
      const up = R.filter(r => r.ret_pct > 0).length, down = R.filter(r => r.ret_pct < 0).length;
      const mean = R.reduce((s, r) => s + r.ret_pct, 0) / R.length;
      let title;
      if (best.ret_pct <= 0) title = 'Every ETF is down since the first run; ' + E(best.item_id) + ' fell the least (' + CS.pct(best.ret_pct) + ')';
      else if (worst.ret_pct >= 0) title = 'Every ETF is up since the first run; ' + E(best.item_id) + ' leads at ' + CS.pct(best.ret_pct);
      else title = E(best.item_id) + ' rose the most since the first run (' + CS.pct(best.ret_pct) + ') while ' + E(worst.item_id) + ' fell the most (' + CS.pct(worst.ret_pct) + ')';
      const body = '<p>Between the first trading session on record (<b>' + CS.date(m.first_session) + '</b>) and the latest (<b>' + CS.date(m.last_session) + '</b>), <b>' + up + '</b> of ' + R.length + ' ETFs gained and <b>' + down + '</b> fell; the average ETF moved ' + sg(mean) + '. ' +
        '<b>' + E(best.item_id) + '</b> ' + (classOf[best.item_id] === 'Bond' ? '(a bond ETF)' : '(a stock ETF)') + ' went from ' + CS.money(best.first_price) + ' to ' + CS.money(best.last_price) + ' (' + sg(best.ret_pct) + '), and <b>' + E(worst.item_id) + '</b> from ' + CS.money(worst.first_price) + ' to ' + CS.money(worst.last_price) + ' (' + sg(worst.ret_pct) + '). The gap between best and worst is <b>' + CS.num(best.ret_pct - worst.ret_pct, 2) + ' percentage points</b>.</p>' +
        how('for each ETF, <code>(latest price − first price) ÷ first price</code> from <code>history.csv</code>, using its first and latest trading session (distinct <code>price_date</code> values). ' + plural(m.n_sessions, 'session') + ' are in the history so far.') +
        why('this is cumulative performance since tracking began. When Treasury ETFs (SHY, IEF, TLT) lead, investors are favouring safety; when stock ETFs (SPY, QQQ, IWM) lead, they are taking risk. Over a short window the ranking can reverse quickly.');
      return { html: section(1, 'f1', title, body, 'c1'), draw: () => make('c1', barConfig(R.map(r => r.item_id), R.map(r => r.ret_pct), R.map(r => (r.ret_pct >= 0 ? CS.cssVar('--up') : CS.cssVar('--down'))), v => CS.pct(v), 'Return since first session (%)')) };
    }
    const L = report.latestMoves;
    if (L.length) {
      const top = L[0], bot = L[L.length - 1];
      const title = E(top.item_id) + ' led the latest session (' + CS.pct(top.pct_change) + '); ' + E(bot.item_id) + ' lagged (' + CS.pct(bot.pct_change) + ')';
      const body = '<p>Only one trading session (<b>' + CS.date(m.last_session) + '</b>) is in the history so far, so a return <i>since the first run</i> cannot be measured yet. Instead this shows each ETF\'s reported change for that session: <b>' + E(top.item_id) + '</b> ' + sg(top.pct_change) + ' was the strongest and <b>' + E(bot.item_id) + '</b> ' + sg(bot.pct_change) + ' the weakest. This finding switches to cumulative returns automatically once a second trading session is collected.</p>' +
        how('the <code>pct_change</code> column (change versus the previous close, as reported by the source) for the latest session in <code>history.csv</code>.') +
        why('a one-day ranking shows what the market rewarded or punished that day, but one day is noise: wait for several sessions before reading a trend.');
      return { html: section(1, 'f1', title, body, 'c1', false, 'single session'), draw: () => make('c1', barConfig(L.map(r => r.item_id), L.map(r => r.pct_change), L.map(r => (r.pct_change >= 0 ? CS.cssVar('--up') : CS.cssVar('--down'))), v => CS.pct(v), 'Reported change, latest session (%)')) };
    }
    return { html: section(1, 'f1', 'Waiting for data', '<p>No price history is available yet.</p>' + how('computed from <code>history.csv</code> once it contains prices.'), null, false, 'pending'), draw: () => {} };
  }

  function finding2() {
    const P = report.perSession, b = report.biggest;
    if (!b) return { html: section(2, 'f2', 'Waiting for data', '<p>No daily changes are available yet.</p>' + how('computed from the <code>pct_change</code> column.'), null, false, 'pending'), draw: () => {} };
    const sorted = P.slice().sort((x, y) => y.avg_abs_pct - x.avg_abs_pct || (x.sd < y.sd ? -1 : 1));
    const wild = sorted[0], calm = sorted[sorted.length - 1];
    const title = 'The biggest single-day move was ' + E(b.item_id) + ' at ' + CS.pct(b.pct) + ' on ' + dayLabel(b.sd);
    let body = '<p>Across <b>' + plural(P.length, 'trading session') + '</b>, the largest one-day change in any ETF was <b>' + E(b.item_id) + '</b> (' + (classOf[b.item_id] === 'Bond' ? 'bond' : 'stock') + ' ETF), ' + sg(b.pct) + ' on <b>' + dayLabel(b.sd) + '</b>. ';
    if (P.length > 1) body += 'Averaged over all ETFs, the most volatile session was <b>' + dayLabel(wild.sd) + '</b> (average absolute move <b>' + CS.num(wild.avg_abs_pct, 2) + '%</b>, led by ' + E(wild.max_item) + ' at ' + CS.pct(wild.max_pct) + ') and the calmest was <b>' + dayLabel(calm.sd) + '</b> (<b>' + CS.num(calm.avg_abs_pct, 2) + '%</b>).';
    else body += 'The average absolute move across ETFs in that session was <b>' + CS.num(wild.avg_abs_pct, 2) + '%</b>; comparisons between sessions appear once more days are collected.';
    body += '</p>' + how('each ETF\'s <code>pct_change</code> (its percent change versus the previous close) is read for every trading session. The biggest move is the largest absolute value; each bar below is the mean of the absolute values across all ETFs in that session. Weekend and holiday runs are not counted again.') +
      why('big moves in broad stock ETFs mean market-wide stress or a surprise; big moves in bond ETFs mean rates or credit conditions shifted. The average absolute move is a simple gauge of how turbulent a session was.');
    return { html: section(2, 'f2', title, body, 'c2'), draw: () => make('c2', {
      type: 'bar', data: { labels: P.map(p => CS.date(p.sd, true)), datasets: [{ label: 'Average absolute daily move (%)', data: P.map(p => p.avg_abs_pct), backgroundColor: P.map(p => (p.sd === b.sd ? CS.cssVar('--s2') : CS.cssVar('--stock'))), borderRadius: 4, maxBarThickness: 90 }] },
      options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { display: false } }, y: { grid: grid(), beginAtZero: true, title: { display: true, text: 'Average |daily change| (%)' } } },
        plugins: { legend: { display: false }, tooltip: tooltip({ callbacks: { label: c => ' Average move ' + CS.num(c.parsed.y, 2) + '%', afterLabel: c => ' Biggest: ' + P[c.dataIndex].max_item + ' ' + CS.pct(P[c.dataIndex].max_pct) } }) } } }) };
  }

  function finding3() {
    const D = report.classDaily.filter(d => d.Stock != null && d.Bond != null), C = report.classCumulative;
    if (!D.length) return { html: section(3, 'f3', 'Waiting for data', '<p>Both stock and bond ETFs need at least one reported daily change.</p>' + how('computed from <code>asset_class</code> and <code>pct_change</code>.'), null, false, 'pending'), draw: () => {} };
    const last = D[D.length - 1];
    let title, body;
    if (C.gap != null) {
      title = (C.gap >= 0 ? 'Stocks have beaten bonds by ' : 'Bonds have beaten stocks by ') + CS.num(Math.abs(C.gap), 2) + ' percentage points since the first run';
      body = '<p>Since <b>' + CS.date(report.meta.first_session) + '</b>, the average stock ETF returned ' + sg(C.Stock) + ' and the average bond ETF ' + sg(C.Bond) + ': a gap of <b>' + CS.num(Math.abs(C.gap), 2) + ' points</b> in favour of ' + (C.gap >= 0 ? 'stocks' : 'bonds') + '. ' +
        'Individual ETFs are even further apart: the best (<b>' + E(C.best) + '</b>) and worst (<b>' + E(C.worst) + '</b>) differ by <b>' + CS.num(C.range, 2) + ' points</b>. In the latest session (' + CS.date(last.sd) + ') stocks moved ' + sg(last.Stock) + ' on average and bonds ' + sg(last.Bond) + '.</p>';
    } else {
      title = 'On ' + dayLabel(last.sd) + ' stocks moved ' + CS.pct(last.Stock) + ' on average and bonds ' + CS.pct(last.Bond);
      body = '<p>The average stock ETF changed ' + sg(last.Stock) + ' and the average bond ETF ' + sg(last.Bond) + ' in the only session recorded so far (<b>' + CS.date(last.sd) + '</b>). Cumulative stock-versus-bond performance appears once a second session is collected.</p>';
    }
    body += how('ETFs are grouped by the <code>asset_class</code> column. Each bar is the simple average of the <code>pct_change</code> values of the stock ETFs (or bond ETFs) in a trading session. The cumulative gap averages each group\'s return since the first session (finding 1) and subtracts.') +
      why('stocks and bonds usually respond differently to the economy. Stocks up and bonds down suggests investors want risk; bonds up and stocks down is a "flight to quality". Both falling together points to rising interest rates hurting everything.');
    return { html: section(3, 'f3', title, body, 'c3'), draw: () => make('c3', {
      type: 'bar', data: { labels: D.map(d => CS.date(d.sd, true)), datasets: [
        { label: 'Stock ETFs (average)', data: D.map(d => d.Stock), backgroundColor: CS.cssVar('--stock'), borderRadius: 4, maxBarThickness: 90 },
        { label: 'Bond ETFs (average)', data: D.map(d => d.Bond), backgroundColor: CS.cssVar('--bond'), borderRadius: 4, maxBarThickness: 90 }] },
      options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { display: false } }, y: { grid: grid(), title: { display: true, text: 'Average daily change (%)' }, ticks: { callback: tickPct } } },
        plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: tooltip({ callbacks: { label: c => ' ' + c.dataset.label + ': ' + CS.pct(c.parsed.y) } }) } } }) };
  }

  function finding4() {
    const V = report.volume;
    if (!V.length) return { html: section(4, 'f4', 'Waiting for data', '<p>No volume figures are available yet.</p>' + how('computed from the <code>volume</code> column.'), null, false, 'pending'), draw: () => {} };
    const top = V[0], low = V[V.length - 1], multi = report.meta.n_sessions > 1;
    const top3 = V.slice(0, 3).reduce((s, v) => s + v.share, 0);
    const title = E(top.item_id) + ' is the busiest ETF, trading ' + CS.compact(top.avg_volume) + ' shares a session (' + CS.num(top.share * 100, 1) + '% of all tracked volume)';
    let body = '<p>Averaged over the sessions collected, <b>' + E(top.item_id) + '</b> trades <b>' + CS.int(top.avg_volume) + '</b> shares a session, about <b>' + CS.num(top.avg_volume / low.avg_volume, 0) + '×</b> the quietest ETF, <b>' + E(low.item_id) + '</b> (' + CS.int(low.avg_volume) + '). The three busiest ETFs (' + V.slice(0, 3).map(v => E(v.item_id)).join(', ') + ') account for <b>' + CS.num(top3 * 100, 1) + '%</b> of all volume. ';
    if (multi) {
      const hi = V.filter(v => v.n > 1 && v.ratio >= 1.5), lo = V.filter(v => v.n > 1 && v.ratio <= 0.5);
      const list = a => a.map(v => E(v.item_id) + ' (' + CS.num(v.ratio, 2) + '× its average)').join(', ');
      body += 'In the latest session, ' + (hi.length ? 'unusually <b>heavy</b> trading showed up in ' + list(hi) : 'no ETF traded 1.5× or more above its own average') + (lo.length ? ', while trading was unusually <b>light</b> in ' + list(lo) : '') + '.';
    } else body += 'Spotting unusually heavy or light days needs more than one session.';
    body += '</p>' + how('<code>volume</code> (shares traded) is averaged per ETF across its trading sessions; share of volume = an ETF\'s average ÷ the sum of all ETFs\' averages; the latest-session ratio = latest volume ÷ that ETF\'s own average. Empty volume cells are skipped.') +
      why('volume measures how easily an ETF can be bought or sold. Heavily traded ETFs have tight prices; a volume spike versus the ETF\'s own norm often marks news, rebalancing or stress, especially in credit ETFs such as HYG and LQD.');
    return { html: section(4, 'f4', title, body, 'c4', true), draw: () => make('c4', {
      type: 'bar', data: { labels: V.map(v => v.item_id), datasets: [
        { label: 'Average volume per session', data: V.map(v => v.avg_volume), backgroundColor: V.map(v => (v.asset_class === 'Bond' ? CS.cssVar('--bond') : CS.cssVar('--stock'))), borderRadius: 4 }
        ].concat(multi ? [{ label: 'Latest session', data: V.map(v => v.latest_volume), backgroundColor: CS.cssVar('--s2'), borderRadius: 4 }] : []) },
      options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, scales: { x: { grid: grid(), ticks: { callback: v => CS.compact(v) }, title: { display: true, text: 'Shares per session' } }, y: { grid: { display: false } } },
        plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: tooltip({ callbacks: { label: c => ' ' + c.dataset.label + ': ' + CS.int(c.parsed.x) } }) } } }) };
  }

  function barConfig(labels, data, colors, fmt, axisTitle) {
    return { type: 'bar', data: { labels, datasets: [{ data, backgroundColor: colors, borderRadius: 4 }] },
      options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, scales: { x: { grid: grid(), title: { display: true, text: axisTitle }, ticks: { callback: tickPct } }, y: { grid: { display: false } } },
        plugins: { legend: { display: false }, tooltip: tooltip({ callbacks: { label: c => ' ' + fmt(c.parsed.x) } }) } } };
  }

  /* ---------- page ---------- */
  let drawers = [];
  function renderFindings() {
    const fs = [finding1(), finding2(), finding3(), finding4()];
    $('findings').innerHTML = fs.map(f => f.html).join('');
    drawers = fs.map(f => f.draw);
    drawers.forEach(d => d());
  }
  function histNotes() {
    const m = report.meta; const notes = [];
    if (m.n_sessions < 2) notes.push('<b>Early history:</b> only ' + plural(m.n_sessions, 'trading session') + ' so far, so some findings use the latest session on its own. Charts and findings fill in automatically as the daily runs add sessions.');
    else if (m.n_sessions < 5) notes.push('<b>Early history:</b> ' + plural(m.n_sessions, 'trading session') + ' so far. Rankings can still change a lot; treat them as a snapshot, not a trend.');
    const span = (Date.parse(m.last_run_date) - Date.parse(m.first_run_date)) / 864e5 + 1;
    if (span > m.n_runs) notes.push(plural(span - m.n_runs, 'day') + ' in the run range had no successful collection, so those days are absent from the history.');
    const short = ids.filter(id => (byItem.get(id) || []).length < m.n_sessions);
    if (short.length) notes.push(short.join(', ') + ' ' + (short.length === 1 ? 'is' : 'are') + ' missing from some sessions (a failed download or an empty value).');
    CS.banner('histBanner', notes.length ? 'warn' : '', notes.join(' '));
  }
  function bind() {
    $('exValue').addEventListener('change', e => { ex.value = e.target.value; drawExplorer(); });
    $('exPick').addEventListener('click', e => {
      const b = e.target.closest('button[data-id]'); if (!b) return;
      const i = ex.picked.indexOf(b.dataset.id); if (i >= 0) ex.picked.splice(i, 1); else ex.picked.push(b.dataset.id);
      drawPick(); drawExplorer();
    });
    document.querySelectorAll('[data-grp]').forEach(b => b.addEventListener('click', () => {
      const g = b.dataset.grp;
      ex.picked = g === 'all' ? ids.slice() : g === 'none' ? [] : ids.filter(i => classOf[i] === g);
      drawPick(); drawExplorer();
    }));
    window.addEventListener('cs-theme', () => { if (!report) return; setDefaults(); drawExplorer(); drawers.forEach(d => d()); });
  }

  CS.load().then(data => {
    CS.dataBanner(data);
    rows = data.rows;
    if (!rows.length) throw new Error('data/history.csv has no rows yet');
    report = Stats.trendsReport(rows); byItem = Stats.sessionsByItem(rows);
    rows.forEach(r => { classOf[r.item_id] = r.asset_class; });
    ids = Object.keys(classOf).sort((a, b) => (classOf[a] === classOf[b] ? (a < b ? -1 : 1) : classOf[a] === 'Stock' ? -1 : 1));
    ex.picked = ex.picked.filter(i => ids.indexOf(i) >= 0);
    const m = report.meta;
    $('heroLead').textContent = 'Computed live from ' + CS.int(m.n_rows) + ' rows of history.csv: ' + plural(m.n_sessions, 'trading session') + ' across ' + plural(m.n_runs, 'daily run') + ' (' + CS.date(m.first_run_date) + ' to ' + CS.date(m.last_run_date) + '), ' + m.n_items + ' ETFs.';
    $('tiles').innerHTML = [['Trading sessions', m.n_sessions, 'distinct market dates'], ['Daily runs', m.n_runs, 'collection dates (UTC)'], ['Rows in history', CS.int(m.n_rows), 'one per ETF per run'], ['ETFs', m.n_items, 'stock and bond']]
      .map(t => '<div class="tile"><span class="v">' + t[1] + '</span><span class="l">' + t[0] + '</span><span class="s">' + t[2] + '</span></div>').join('');
    setDefaults(); histNotes(); drawPick(); drawExplorer(); renderFindings(); bind();
  }).catch(err => { CS.dataBanner(null, err); $('heroLead').textContent = 'The history file could not be loaded.'; console.error(err); })
    .finally(CS.doneLoading);
})();
