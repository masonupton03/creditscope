/* CreditScope statistics. Pure functions (no DOM) so the same code runs in the browser and in
 * Node tests. Every number on the Trends page is computed here from the rows of data/history.csv.
 *
 * Vocabulary
 *   run       one collection date (UTC) in history.csv: a row's `date`
 *   session   one market trading date: a row's `price_date`. Weekend or holiday runs carry the last
 *             session's quotes again, so they repeat a session instead of adding one.
 *   a session observation = the last row (latest run) for each (item_id, session).
 */
(function (root) {
  'use strict';
  const NUMERIC = ['price', 'volume', 'net_change', 'pct_change'];

  /** Parse CSV text (RFC 4180 quoting) into an array of arrays. */
  function parseCSVText(text) {
    const out = []; let row = []; let cell = ''; let q = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (q) {
        if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += c;
      } else if (c === '"') q = true;
      else if (c === ',') { row.push(cell); cell = ''; }
      else if (c === '\n') { row.push(cell); out.push(row); row = []; cell = ''; }
      else if (c !== '\r') cell += c;
    }
    if (cell !== '' || row.length) { row.push(cell); out.push(row); }
    return out;
  }

  /** CSV text -> row objects. Numeric columns become numbers; empty cells become null. */
  function parseHistory(text) {
    const table = parseCSVText(text).filter(r => r.length > 1 || (r[0] || '') !== '');
    if (!table.length) return [];
    const head = table[0];
    return table.slice(1).map(cells => {
      const o = {};
      head.forEach((h, i) => { o[h] = cells[i] === undefined ? '' : cells[i]; });
      NUMERIC.forEach(k => {
        const v = o[k];
        o[k] = v === '' || v == null || !isFinite(Number(v)) ? null : Number(v);
      });
      return o;
    });
  }

  const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const mean = a => a.reduce((s, x) => s + x, 0) / a.length;
  const sessionOf = r => r.price_date || r.date;

  /** Deduplicated session observations: Map item_id -> [{sd, run, ...row}] sorted by session. */
  function sessionsByItem(rows) {
    const best = new Map();
    rows.forEach(r => {
      const key = r.item_id + '\u0000' + sessionOf(r);
      const cur = best.get(key);
      if (!cur || r.date >= cur.date) best.set(key, r);
    });
    const byItem = new Map();
    best.forEach(r => {
      if (!byItem.has(r.item_id)) byItem.set(r.item_id, []);
      byItem.get(r.item_id).push(Object.assign({ sd: sessionOf(r) }, r));
    });
    byItem.forEach(list => list.sort((a, b) => cmpStr(a.sd, b.sd)));
    return byItem;
  }

  /** The latest run vs the previous run (the move rule from the README). */
  function runComparison(rows, topN) {
    topN = topN || 5;
    const dates = Array.from(new Set(rows.map(r => r.date))).sort();
    const latest = dates[dates.length - 1] || null;
    const prev = dates.length > 1 ? dates[dates.length - 2] : null;
    const now = new Map(rows.filter(r => r.date === latest).map(r => [r.item_id, r]));
    const before = new Map(rows.filter(r => prev && r.date === prev).map(r => [r.item_id, r]));
    const changes = new Map();
    now.forEach((r, id) => {
      const p = before.get(id);
      let diff = null; let pct = null;
      if (p && p.price != null && r.price != null && p.price !== 0) {
        diff = r.price - p.price; pct = (r.price - p.price) / p.price * 100;
      }
      changes.set(id, { prev: p || null, diff, pct });
    });
    const movers = Array.from(changes.entries())
      .filter(([, c]) => c.pct != null && c.pct !== 0)
      .map(([id, c]) => ({ item_id: id, item: now.get(id).item, old_price: c.prev.price, new_price: now.get(id).price, pct: c.pct, old_volume: c.prev.volume, new_volume: now.get(id).volume }))
      .sort((a, b) => Math.abs(b.pct) - Math.abs(a.pct) || cmpStr(a.item_id, b.item_id))
      .slice(0, topN);
    const maxPd = m => { let x = ''; m.forEach(r => { if (r.price_date && r.price_date > x) x = r.price_date; }); return x; };
    const nowPd = maxPd(now); const prevPd = maxPd(before);
    return {
      latest, prev, now, before, changes, movers,
      newItems: prev ? Array.from(now.keys()).filter(i => !before.has(i)).sort() : [],
      goneItems: prev ? Array.from(before.keys()).filter(i => !now.has(i)).sort() : [],
      latestPriceDate: nowPd, prevPriceDate: prevPd,
      newSession: !!(nowPd && prevPd && nowPd > prevPd)
    };
  }

  /** Everything the Trends page needs, from the history rows only. */
  function trendsReport(rows) {
    const byItem = sessionsByItem(rows);
    const runs = Array.from(new Set(rows.map(r => r.date))).sort();
    const sessionDates = Array.from(new Set(Array.from(byItem.values()).flatMap(l => l.map(o => o.sd)))).sort();
    const itemIds = Array.from(byItem.keys()).sort();
    const klass = new Map(); rows.forEach(r => klass.set(r.item_id, r.asset_class));
    const meta = {
      n_rows: rows.length, n_runs: runs.length, n_sessions: sessionDates.length, n_items: itemIds.length,
      first_run_date: runs[0] || null, last_run_date: runs[runs.length - 1] || null,
      session_dates: sessionDates, first_session: sessionDates[0] || null, last_session: sessionDates[sessionDates.length - 1] || null
    };

    // 1. return since the first session
    const returns = [];
    itemIds.forEach(id => {
      const list = byItem.get(id).filter(o => o.price != null);
      if (list.length < 2) return;
      const a = list[0]; const b = list[list.length - 1];
      returns.push({ item_id: id, asset_class: klass.get(id), first_sd: a.sd, last_sd: b.sd, first_price: a.price, last_price: b.price, ret_pct: (b.price - a.price) / a.price * 100 });
    });
    returns.sort((x, y) => y.ret_pct - x.ret_pct || cmpStr(x.item_id, y.item_id));

    // latest session moves as reported by the source (works from the first session)
    const lastSession = meta.last_session;
    const latestMoves = [];
    itemIds.forEach(id => {
      const o = byItem.get(id).find(x => x.sd === lastSession);
      if (o && o.pct_change != null) latestMoves.push({ item_id: id, asset_class: klass.get(id), pct_change: o.pct_change });
    });
    latestMoves.sort((x, y) => y.pct_change - x.pct_change || cmpStr(x.item_id, y.item_id));

    // 2. biggest single-session move (reported pct_change), per session and overall
    const perSession = [];
    let biggest = null;
    sessionDates.forEach(sd => {
      const vals = [];
      itemIds.forEach(id => {
        const o = byItem.get(id).find(x => x.sd === sd);
        if (o && o.pct_change != null) vals.push({ item_id: id, pct: o.pct_change });
      });
      if (!vals.length) return;
      const top = vals.slice().sort((a, b) => Math.abs(b.pct) - Math.abs(a.pct) || cmpStr(a.item_id, b.item_id))[0];
      perSession.push({ sd, n: vals.length, avg_abs_pct: mean(vals.map(v => Math.abs(v.pct))), max_item: top.item_id, max_pct: top.pct });
      if (!biggest || Math.abs(top.pct) > Math.abs(biggest.pct)) biggest = { sd, item_id: top.item_id, pct: top.pct };
    });

    // 3. stocks vs bonds
    const classDaily = sessionDates.map(sd => {
      const row = { sd };
      ['Stock', 'Bond'].forEach(c => {
        const v = [];
        itemIds.forEach(id => {
          if (klass.get(id) !== c) return;
          const o = byItem.get(id).find(x => x.sd === sd);
          if (o && o.pct_change != null) v.push(o.pct_change);
        });
        row[c] = v.length ? mean(v) : null;
      });
      return row;
    });
    const cum = {};
    ['Stock', 'Bond'].forEach(c => {
      const v = returns.filter(r => r.asset_class === c).map(r => r.ret_pct);
      cum[c] = v.length ? mean(v) : null;
    });
    const classCumulative = {
      Stock: cum.Stock, Bond: cum.Bond, gap: cum.Stock != null && cum.Bond != null ? cum.Stock - cum.Bond : null,
      best: returns.length ? returns[0].item_id : null, worst: returns.length ? returns[returns.length - 1].item_id : null,
      range: returns.length ? returns[0].ret_pct - returns[returns.length - 1].ret_pct : null
    };

    // 4. volume
    const volume = [];
    itemIds.forEach(id => {
      const list = byItem.get(id).filter(o => o.volume != null);
      if (!list.length) return;
      const avg = mean(list.map(o => o.volume));
      const lastO = list[list.length - 1];
      volume.push({ item_id: id, asset_class: klass.get(id), avg_volume: avg, latest_volume: lastO.volume, latest_sd: lastO.sd, ratio: lastO.volume / avg, n: list.length });
    });
    const total = volume.reduce((s, v) => s + v.avg_volume, 0);
    volume.forEach(v => { v.share = v.avg_volume / total; });
    volume.sort((a, b) => b.avg_volume - a.avg_volume || cmpStr(a.item_id, b.item_id));

    return { meta, returns, latestMoves, perSession, biggest, classDaily, classCumulative, volume };
  }

  const api = { parseCSVText, parseHistory, sessionsByItem, runComparison, trendsReport, sessionOf };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.Stats = api;
})(typeof window !== 'undefined' ? window : globalThis);
