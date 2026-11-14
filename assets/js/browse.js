/* Browse page: latest values for every ETF with search, filters, sorting and a saved shortlist. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const NUMERIC = ['price', 'net_change', 'pct_change', 'volume'];
  const LABELS = { item_id: 'ETF', item: 'Name', asset_class: 'Class', category: 'Category', price: 'Price', net_change: 'Change', pct_change: 'Change %', volume: 'Volume', price_date: 'Quote date' };
  let all = []; let latestRun = '';
  const state = { q: '', cls: '', cat: '', dir: '', star: false, key: 'item_id', desc: false };

  function latestPerItem(rows) {
    const m = new Map();
    rows.forEach(r => { const c = m.get(r.item_id); if (!c || r.date >= c.date) m.set(r.item_id, r); });
    return Array.from(m.values());
  }

  function options(sel, values, firstLabel) {
    sel.innerHTML = '<option value="">' + firstLabel + '</option>' + values.map(v => '<option>' + CS.esc(v) + '</option>').join('');
  }

  function visible() {
    const q = state.q.trim().toLowerCase();
    const stars = CS.shortlist.get();
    let list = all.filter(r =>
      (!q || r.item.toLowerCase().includes(q) || r.item_id.toLowerCase().includes(q) || r.category.toLowerCase().includes(q)) &&
      (!state.cls || r.asset_class === state.cls) && (!state.cat || r.category === state.cat) &&
      (!state.dir || CS.dir(r.pct_change) === state.dir) && (!state.star || stars.indexOf(r.item_id) >= 0));
    const k = state.key; const sign = state.desc ? -1 : 1;
    list = list.slice().sort((a, b) => {
      const x = a[k], y = b[k];
      if (x == null && y == null) return a.item_id < b.item_id ? -1 : 1;
      if (x == null) return 1; if (y == null) return -1;       // missing values always last
      const c = typeof x === 'number' ? x - y : String(x).localeCompare(String(y));
      return c * sign || (a.item_id < b.item_id ? -1 : 1);
    });
    return list;
  }

  function render() {
    const list = visible(); const stars = CS.shortlist.get();
    $('count').textContent = 'Showing ' + list.length + ' of ' + all.length + ' ETFs · sorted by ' + LABELS[state.key] + ' (' + (state.desc ? 'high to low' : 'low to high') + ')';
    $('none').hidden = list.length > 0;
    $('tbl').hidden = list.length === 0;
    $('tbl').querySelector('tbody').innerHTML = list.map(r => {
      const dir = CS.dir(r.pct_change); const on = stars.indexOf(r.item_id) >= 0;
      const old = r.date < latestRun ? ' <span class="chip" title="This ETF was not collected in the latest run; showing its most recent values">last seen ' + CS.esc(CS.date(r.date, true)) + '</span>' : '';
      return '<tr data-id="' + CS.esc(r.item_id) + '">' +
        '<td class="c-star"><button class="star" type="button" aria-pressed="' + on + '" aria-label="' + (on ? 'Remove ' : 'Add ') + CS.esc(r.item_id) + (on ? ' from' : ' to') + ' shortlist" title="' + (on ? 'Remove from shortlist' : 'Add to shortlist') + '">' + (on ? '★' : '☆') + '</button></td>' +
        '<td class="c-tk"><span class="tk">' + CS.esc(r.item_id) + '</span></td>' +
        '<td class="nm c-name" title="' + CS.esc(r.item) + '">' + CS.esc(r.item) + old + '</td>' +
        '<td class="c-hide"><span class="cls ' + r.asset_class.toLowerCase() + '">' + CS.esc(r.asset_class) + '</span></td>' +
        '<td class="c-hide">' + CS.esc(r.category) + '</td>' +
        '<td class="r c-price">' + CS.money(r.price) + '</td>' +
        '<td class="r c-hide ' + dir + '">' + (r.net_change == null ? '—' : CS.signed(r.net_change)) + '</td>' +
        '<td class="r c-pct"><span class="badge ' + dir + '">' + (r.pct_change == null ? '—' : CS.pct(r.pct_change)) + '</span></td>' +
        '<td class="r c-hide">' + CS.int(r.volume) + '</td>' +
        '<td class="c-hide">' + CS.esc(CS.date(r.price_date, true)) + '</td>' +
        '<td class="c-more"><span class="cls ' + r.asset_class.toLowerCase() + '">' + CS.esc(r.asset_class) + ' · ' + CS.esc(r.category) + '</span><span>Vol ' + CS.compact(r.volume) + '</span><span>' + (r.net_change == null ? '' : CS.signed(r.net_change)) + '</span><span>' + CS.esc(CS.date(r.price_date, true)) + '</span></td></tr>';
    }).join('');
    document.querySelectorAll('#tbl thead th[data-key]').forEach(th => {
      const on = th.dataset.key === state.key;
      if (on) th.setAttribute('aria-sort', state.desc ? 'descending' : 'ascending'); else th.removeAttribute('aria-sort');
      th.querySelector('.arrow').textContent = on ? (state.desc ? '▼' : '▲') : '▲▼';
    });
    $('sortKey').value = state.key;
    $('ascBtn').setAttribute('aria-pressed', String(!state.desc)); $('descBtn').setAttribute('aria-pressed', String(state.desc));
    shortlist();
  }

  function shortlist() {
    const ids = CS.shortlist.get().filter(id => all.some(r => r.item_id === id));
    $('shortlist').innerHTML = ids.length ? ids.map(id => {
      const r = all.find(x => x.item_id === id); const dir = CS.dir(r.pct_change);
      return '<span class="sl"><b>' + CS.esc(id) + '</b>' + CS.money(r.price) + ' <span class="' + dir + '">' + (r.pct_change == null ? '' : CS.pct(r.pct_change)) + '</span></span>';
    }).join('') : '<span class="empty">No ETFs saved yet. Press ☆ next to an ETF to add it.</span>';
  }

  function bind() {
    $('q').addEventListener('input', e => { state.q = e.target.value; render(); });
    $('fClass').addEventListener('change', e => { state.cls = e.target.value; render(); });
    $('fCat').addEventListener('change', e => { state.cat = e.target.value; render(); });
    $('fDir').addEventListener('change', e => { state.dir = e.target.value; render(); });
    $('fStar').addEventListener('change', e => { state.star = e.target.checked; render(); });
    $('sortKey').addEventListener('change', e => { state.key = e.target.value; state.desc = NUMERIC.indexOf(state.key) >= 0; render(); });
    $('ascBtn').addEventListener('click', () => { state.desc = false; render(); });
    $('descBtn').addEventListener('click', () => { state.desc = true; render(); });
    $('reset').addEventListener('click', () => {
      Object.assign(state, { q: '', cls: '', cat: '', dir: '', star: false, key: 'item_id', desc: false });
      $('q').value = ''; $('fClass').value = ''; $('fCat').value = ''; $('fDir').value = ''; $('fStar').checked = false; render();
    });
    document.querySelectorAll('#tbl thead th[data-key] button').forEach(b => b.addEventListener('click', () => {
      const key = b.closest('th').dataset.key;
      if (state.key === key) state.desc = !state.desc; else { state.key = key; state.desc = NUMERIC.indexOf(key) >= 0; }
      render();
    }));
    $('tbl').addEventListener('click', e => {
      const btn = e.target.closest('button.star'); if (!btn) return;
      CS.shortlist.toggle(btn.closest('tr').dataset.id);
      render();
      const again = document.querySelector('tr[data-id="' + btn.closest('tr').dataset.id + '"] button.star'); if (again) again.focus();
    });
  }

  CS.load().then(data => {
    CS.dataBanner(data);
    all = latestPerItem(data.rows);
    if (!all.length) throw new Error('data/history.csv has no rows yet');
    latestRun = all.reduce((m, r) => (r.date > m ? r.date : m), '');
    const uniq = k => Array.from(new Set(all.map(r => r[k]))).sort();
    options($('fClass'), uniq('asset_class'), 'All classes'); options($('fCat'), uniq('category'), 'All categories');
    $('sortKey').innerHTML = Object.keys(LABELS).map(k => '<option value="' + k + '">' + LABELS[k] + '</option>').join('');
    const q = new URLSearchParams(location.search).get('q');
    if (q) { state.q = q; $('q').value = q; }
    $('heroLead').textContent = all.length + ' ETFs · latest values from the ' + CS.date(latestRun) + ' run. Quotes are from the ' + CS.date(all.reduce((m, r) => (r.price_date > m ? r.price_date : m), '')) + ' trading session.';
    bind(); render();
  }).catch(err => { CS.dataBanner(null, err); $('heroLead').textContent = 'The data could not be loaded.'; })
    .finally(CS.doneLoading);
})();
