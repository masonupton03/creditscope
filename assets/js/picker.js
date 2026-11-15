/* An accessible search combobox shared by the Fundamentals and Compare pages (same ARIA pattern as the Explorer).
 *   Picker.attach({ input, list, entries, onChoose(entry), limit, noneText })  ->  { setEntries(entries) }
 * Needs search.js (ExplorerSearch). Entries are { s: ticker, n: name, t: 'E' | 'S', ... }. */
(function (root) {
  'use strict';
  function attach(o) {
    const E = root.CS ? root.CS.esc : (s => String(s));
    let idx = root.ExplorerSearch.buildIndex(o.entries || []), shown = [], active = -1;
    const input = o.input, list = o.list, limit = o.limit || 8;
    const close = () => { list.hidden = true; input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant'); };
    const mark = i => {
      list.querySelectorAll('li[role=option]').forEach((li, k) => li.setAttribute('aria-selected', String(k === i)));
      const li = list.querySelector('#' + list.id + '-o' + i); if (li) { li.scrollIntoView({ block: 'nearest' }); input.setAttribute('aria-activedescendant', li.id); }
    };
    function render() {
      const q = input.value;
      if (!q.trim()) return close();
      shown = root.ExplorerSearch.search(idx, q, limit); active = shown.length ? 0 : -1;
      list.innerHTML = shown.length
        ? shown.map((e, i) => '<li role="option" id="' + list.id + '-o' + i + '" data-i="' + i + '" aria-selected="' + (i === 0) + '"><span class="tk">' + E(e.s) + '</span><span class="nm">' + E(e.n) + '</span><span class="chip">' + (e.t === 'E' ? 'ETF' : 'Stock') + '</span></li>').join('')
        : '<li class="none" role="option" aria-disabled="true">' + E(o.noneText || 'No match.') + '</li>';
      list.hidden = false; input.setAttribute('aria-expanded', 'true');
    }
    const choose = e => { input.value = ''; close(); o.onChoose(e); };
    input.addEventListener('input', render);
    input.addEventListener('focus', render);
    input.addEventListener('keydown', ev => {
      if (ev.key === 'ArrowDown' && shown.length) { ev.preventDefault(); active = (active + 1) % shown.length; mark(active); }
      else if (ev.key === 'ArrowUp' && shown.length) { ev.preventDefault(); active = (active - 1 + shown.length) % shown.length; mark(active); }
      else if (ev.key === 'Enter') { ev.preventDefault(); const e = shown[active] || shown[0]; if (e) choose(e); }
      else if (ev.key === 'Escape') close();
    });
    list.addEventListener('mousedown', ev => { const li = ev.target.closest('li[data-i]'); if (li) { ev.preventDefault(); choose(shown[+li.dataset.i]); } });
    document.addEventListener('click', ev => { if (!ev.target.closest(o.scope || '.ex-search')) close(); });
    return { setEntries(entries) { idx = root.ExplorerSearch.buildIndex(entries); } };
  }
  root.Picker = { attach };
})(window);
