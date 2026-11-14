/* Today page: last run, source status, counts, latest values with change, biggest moves. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);

  function sparkline(points, dir) {
    if (!points || points.length < 2) return '<span class="muted">—</span>';
    const w = 84, h = 26, pad = 2;
    const lo = Math.min.apply(null, points), hi = Math.max.apply(null, points), span = hi - lo || 1;
    const xy = points.map((v, i) => [pad + i * (w - 2 * pad) / (points.length - 1), h - pad - (v - lo) / span * (h - 2 * pad)]);
    const d = xy.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join('');
    const col = dir === 'up' ? 'var(--up)' : dir === 'down' ? 'var(--down)' : 'var(--flat)';
    return '<svg class="spark" viewBox="0 0 ' + w + ' ' + h + '" role="img" aria-label="Price trend over ' + points.length + ' trading sessions"><path d="' + d + '" fill="none" stroke="' + col + '" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/><circle cx="' + xy[xy.length - 1][0].toFixed(1) + '" cy="' + xy[xy.length - 1][1].toFixed(1) + '" r="2.2" fill="' + col + '"/></svg>';
  }

  function tiles(status, cmp) {
    const bad = status.sources.filter(s => !s.ok).length;
    const total = status.sources.length;
    const list = a => (a.length ? a.join(', ') : 'none');
    const items = [
      ['Last run (UTC)', status.run_time.slice(11, 16), CS.date(status.run_time.slice(0, 10)) + ' · ' + CS.ago(status.run_time)],
      ['Sources OK', (total - bad) + '/' + total, bad ? bad + ' failed today' : 'all sources healthy'],
      ['ETFs tracked', CS.int(status.items), 'in the latest run'],
      ['New today', CS.int(status.new_today.length), list(status.new_today)],
      ['Gone today', CS.int(status.gone_today.length), list(status.gone_today)],
      ['Days collected', CS.int(status.days_with_success), 'since ' + CS.date(status.first_run_date)]
    ];
    $('tiles').innerHTML = items.map(t => '<div class="tile"><span class="v' + (t[0] === 'Sources OK' && bad ? ' down' : '') + '">' + CS.esc(t[1]) + '</span><span class="l">' + t[0] + '</span><span class="s">' + CS.esc(t[2]) + '</span></div>').join('');
  }

  function hero(status, cmp) {
    const run = cmp.latest;
    const pd = cmp.latestPriceDate;
    let lead;
    if (!cmp.now.size) {
      lead = 'No ETF values were collected in the latest run. See the source status below.';
    } else if (pd && pd < run) {
      lead = 'The ' + CS.date(run) + ' run (UTC) collected ' + cmp.now.size + ' ETFs. Markets were closed, so the source repeated the ' + CS.weekday(pd) + ' ' + CS.date(pd) + ' quotes: unchanged values below are carried over, not new market activity.';
    } else {
      lead = 'The ' + CS.date(run) + ' run (UTC) collected ' + cmp.now.size + ' ETFs with quotes from the ' + CS.weekday(pd) + ' ' + CS.date(pd) + ' trading session.';
    }
    $('heroLead').textContent = lead;
  }

  function movers(cmp) {
    const el = $('movers'); const cap = $('movCap');
    if (!cmp.prev) {
      cap.textContent = 'Compared with the previous run.';
      el.innerHTML = '<p class="empty">This is the first run, so there is nothing to compare with yet. Moves will appear after the next daily run.</p>';
      return;
    }
    cap.textContent = 'Top 5 by absolute % change in price, ' + CS.date(cmp.prev, true) + ' → ' + CS.date(cmp.latest, true) + ' (the previous run to the latest run).';
    if (!cmp.movers.length) {
      el.innerHTML = '<p class="empty">No ETF changed price since the previous run. ' +
        (cmp.newSession ? '' : 'The source still reports the ' + CS.date(cmp.latestPriceDate) + ' trading session, so these are carried-over quotes, not new market activity.') + '</p>';
      return;
    }
    const maxAbs = Math.max.apply(null, cmp.movers.map(m => Math.abs(m.pct)));
    el.innerHTML = '<ol class="movers">' + cmp.movers.map(m => {
      const dir = CS.dir(m.pct); const wd = Math.max(3, Math.abs(m.pct) / maxAbs * 50);
      return '<li class="mover"><a class="tk" href="browse.html?q=' + encodeURIComponent(m.item_id) + '">' + CS.esc(m.item_id) + '</a>' +
        '<span class="barwrap" role="img" aria-label="' + CS.esc(m.item_id) + ' ' + CS.pct(m.pct) + '"><span class="bar ' + dir + '" style="width:' + wd.toFixed(1) + '%"></span></span>' +
        '<span class="pc ' + dir + '">' + CS.pct(m.pct) + '</span>' +
        '<span class="sub">' + CS.money(m.old_price) + ' → ' + CS.money(m.new_price) + ' · volume ' + CS.compact(m.old_volume) + ' → ' + CS.compact(m.new_volume) + '</span></li>';
    }).join('') + '</ol>';
  }

  function sources(status) {
    const ok = status.sources.filter(s => s.ok).length;
    $('srcCap').textContent = ok + ' of ' + status.sources.length + ' sources succeeded in the latest run (run time ' + CS.runTime(status.run_time) + '). One source = one ETF quote request to Nasdaq.';
    $('sources').innerHTML = status.sources.map(s => '<div class="src ' + (s.ok ? 'ok' : 'fail') + '" title="' + CS.esc(s.name) + ': ' + (s.ok ? 'ok, ' + s.count + ' row' : 'failed') + '"><span class="dot"></span>' +
      CS.esc(s.name.replace(/^nasdaq-/, '')) + '<small>' + (s.ok ? s.count + ' row' + (s.count === 1 ? '' : 's') : 'failed') + '</small></div>').join('');
  }

  function changes(status) {
    const card = $('changesCard');
    const parts = [];
    if (status.new_today.length) parts.push('<p><b>Appeared:</b> ' + status.new_today.map(i => '<span class="chip ok">' + CS.esc(i) + '</span>').join(' ') + '</p>');
    if (status.gone_today.length) parts.push('<p><b>Disappeared:</b> ' + status.gone_today.map(i => '<span class="chip fail">' + CS.esc(i) + '</span>').join(' ') + '</p>');
    card.hidden = !parts.length; $('changes').innerHTML = parts.join('');
  }

  function table(cmp, byItem) {
    const rows = Array.from(cmp.now.values()).sort((a, b) => (a.asset_class === b.asset_class ? 0 : a.asset_class === 'Stock' ? -1 : 1) || (a.item_id < b.item_id ? -1 : 1));
    $('tblCap').textContent = cmp.prev
      ? 'Change compares each price with the previous run (' + CS.date(cmp.prev) + '). The trend line shows the price at each trading session collected so far.'
      : 'First run: change columns fill in after the next run. The trend line shows the price at each trading session collected so far.';
    $('tbl').querySelector('tbody').innerHTML = rows.map(r => {
      const c = cmp.changes.get(r.item_id); const dir = CS.dir(c.pct);
      const pts = (byItem.get(r.item_id) || []).filter(o => o.price != null).map(o => o.price).slice(-30);
      const carried = r.price_date && r.price_date < r.date;
      return '<tr><td><a class="tk" href="browse.html?q=' + encodeURIComponent(r.item_id) + '">' + CS.esc(r.item_id) + '</a></td>' +
        '<td class="nm hm" title="' + CS.esc(r.item) + '">' + CS.esc(r.item) + '</td>' +
        '<td class="ht"><span class="cls ' + r.asset_class.toLowerCase() + '">' + CS.esc(r.asset_class) + '</span></td>' +
        '<td class="r">' + CS.money(r.price) + '</td>' +
        '<td class="r hs ' + dir + '">' + (c.diff == null ? '—' : CS.signed(c.diff)) + '</td>' +
        '<td class="r"><span class="badge ' + dir + '">' + (c.pct == null ? '—' : CS.pct(c.pct)) + '</span></td>' +
        '<td class="r hm">' + CS.int(r.volume) + '</td>' +
        '<td class="hv">' + sparkline(pts, dir) + '</td>' +
        '<td class="ht">' + CS.esc(CS.date(r.price_date, true)) + (carried ? ' <span class="chip" title="Markets were closed: quotes carried over from this session">carried over</span>' : '') + '</td></tr>';
    }).join('');
  }

  CS.load().then(data => {
    CS.dataBanner(data);
    const cmp = Stats.runComparison(data.rows);
    if (!cmp.latest) throw new Error('data/history.csv has no rows yet');
    tiles(data.status, cmp); hero(data.status, cmp); movers(cmp); sources(data.status); changes(data.status);
    table(cmp, Stats.sessionsByItem(data.rows));
  }).catch(err => {
    CS.dataBanner(null, err);
    $('heroLead').textContent = 'The data could not be loaded.';
  }).finally(CS.doneLoading);
})();
