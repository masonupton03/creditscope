/* CreditScope shared behaviour: theme, data loading, formatting, service worker, install prompt. */
(function () {
  'use strict';
  const THEME_KEY = 'creditscope.theme';
  const root = document.documentElement;
  const CS = window.CS = {};

  /* ---------- theme (dark by default, light toggle, remembered) ---------- */
  function currentTheme() { return root.dataset.theme === 'light' ? 'light' : 'dark'; }
  function setTheme(t) {
    root.dataset.theme = t;
    try { localStorage.setItem(THEME_KEY, t); } catch (e) { /* private mode */ }
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', t === 'light' ? '#f3f6fb' : '#060a10');
    const btn = document.getElementById('themeBtn');
    if (btn) { btn.textContent = t === 'light' ? '☾' : '☀'; btn.setAttribute('aria-label', t === 'light' ? 'Switch to dark theme' : 'Switch to light theme'); }
    window.dispatchEvent(new CustomEvent('cs-theme', { detail: t }));
  }
  CS.theme = currentTheme;
  CS.cssVar = name => getComputedStyle(root).getPropertyValue(name).trim();

  /* ---------- formatting ---------- */
  const nf = (min, max) => new Intl.NumberFormat('en-US', { minimumFractionDigits: min, maximumFractionDigits: max });
  const f2 = nf(2, 2); const f0 = nf(0, 0); const f1 = nf(1, 1);
  CS.money = v => (v == null ? '—' : '$' + f2.format(v));
  CS.num = (v, d) => (v == null ? '—' : nf(d, d).format(v));
  CS.int = v => (v == null ? '—' : f0.format(Math.round(v)));
  CS.pct = (v, d) => (v == null ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '') + nf(d == null ? 2 : d, d == null ? 2 : d).format(Math.abs(v)) + '%');
  CS.signed = v => (v == null ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '') + f2.format(Math.abs(v)));
  CS.compact = v => {
    if (v == null) return '—';
    const a = Math.abs(v);
    if (a >= 1e9) return f2.format(v / 1e9) + 'B';
    if (a >= 1e6) return f1.format(v / 1e6) + 'M';
    if (a >= 1e3) return f1.format(v / 1e3) + 'K';
    return f0.format(v);
  };
  CS.dir = v => (v == null || v === 0 ? 'flat' : v > 0 ? 'up' : 'down');
  CS.esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  /** '2026-11-13' -> 'Nov 13, 2026' (no timezone shifting: it is a calendar date). */
  CS.date = (iso, short) => {
    if (!iso) return '—';
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
    if (!m) return iso;
    return MONTHS[+m[2] - 1] + ' ' + (+m[3]) + (short ? '' : ', ' + m[1]);
  };
  CS.weekday = iso => {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
    return m ? ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).getUTCDay()] : '';
  };
  CS.runTime = iso => {
    if (!iso) return '—';
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return CS.date(iso.slice(0, 10)) + ', ' + iso.slice(11, 16) + ' UTC';
  };
  CS.ago = iso => {
    const d = new Date(iso);
    if (isNaN(d)) return '';
    const mins = Math.round((Date.now() - d.getTime()) / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return mins + ' min ago';
    if (mins < 60 * 48) return Math.round(mins / 60) + ' h ago';
    return Math.round(mins / 1440) + ' days ago';
  };

  /* ---------- data ---------- */
  async function getText(url) {
    const res = await fetch(url, { cache: 'no-cache' });
    if (!res.ok) throw new Error(url + ' returned HTTP ' + res.status);
    return { text: await res.text(), stale: res.headers.get('X-CS-Cache') === '1' };
  }
  /** Load data/history.csv and data/status.json. `stale` is true when served from the offline cache. */
  CS.load = async function () {
    const [h, s] = await Promise.all([getText('data/history.csv'), getText('data/status.json')]);
    return { rows: Stats.parseHistory(h.text), status: JSON.parse(s.text), stale: h.stale || s.stale };
  };
  CS.doneLoading = () => { const l = document.getElementById('loading'); if (l) { l.classList.add('done'); setTimeout(() => l.remove(), 500); } };
  CS.banner = (id, kind, html) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = 'banner ' + kind; el.hidden = !html; el.innerHTML = html || '';
  };
  /** Banner shown for offline/stale data and for load errors (shared by all pages). */
  CS.dataBanner = function (data, err) {
    if (err) {
      CS.banner('dataBanner', 'error', '<span><b>Could not load the data files.</b> ' + CS.esc(err.message) +
        ' If you are offline and have never opened the site online before, there is no saved copy yet.</span>');
    } else if (data.stale) {
      CS.banner('dataBanner', 'warn', '<span><b>You are offline.</b> Showing the last data this device loaded (run ' + CS.esc(CS.runTime(data.status.run_time)) + ').</span>');
    } else CS.banner('dataBanner', '', '');
  };

  /* ---------- shortlist (stars) stored in the browser ---------- */
  const SL_KEY = 'creditscope.shortlist';
  CS.shortlist = {
    get() { try { return JSON.parse(localStorage.getItem(SL_KEY) || '[]'); } catch (e) { return []; } },
    set(list) { try { localStorage.setItem(SL_KEY, JSON.stringify(Array.from(new Set(list)).sort())); } catch (e) { /* ignore */ } },
    has(id) { return this.get().indexOf(id) >= 0; },
    toggle(id) { const l = this.get(); const i = l.indexOf(id); if (i >= 0) l.splice(i, 1); else l.push(id); this.set(l); return i < 0; }
  };

  /* ---------- install + service worker ---------- */
  let deferredPrompt = null;
  window.addEventListener('beforeinstallprompt', e => {
    e.preventDefault(); deferredPrompt = e;
    const b = document.getElementById('installBtn'); if (b) b.hidden = false;
  });
  window.addEventListener('appinstalled', () => { deferredPrompt = null; const b = document.getElementById('installBtn'); if (b) b.hidden = true; });

  document.addEventListener('DOMContentLoaded', () => {
    setTheme(currentTheme());
    const tb = document.getElementById('themeBtn');
    if (tb) tb.addEventListener('click', () => setTheme(currentTheme() === 'light' ? 'dark' : 'light'));
    const ib = document.getElementById('installBtn');
    if (ib) ib.addEventListener('click', async () => {
      if (!deferredPrompt) return;
      deferredPrompt.prompt(); await deferredPrompt.userChoice.catch(() => null); deferredPrompt = null; ib.hidden = true;
    });
    const yr = document.getElementById('year'); if (yr) yr.textContent = new Date().getFullYear();
  });
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => { navigator.serviceWorker.register('sw.js').catch(() => null); });
  }
})();
