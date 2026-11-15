/* CreditScope service worker.
 *  - App shell (pages, CSS, JS, icons): cached on install, served from cache and refreshed in the
 *    background (stale-while-revalidate), so the site opens offline.
 *  - Data files (data/history.csv, data/status.json): network first, so an online visit always gets
 *    the latest data; when offline the last copy that was loaded is served, marked X-CS-Cache: 1.
 */
const VERSION = 'creditscope-v6';
const SHELL = [
  './', 'index.html', 'browse.html', 'trends.html', 'explorer.html', 'portfolio.html', 'fundamentals.html', 'compare.html', 'platform.html', 'manifest.webmanifest',
  'assets/css/site.css', 'assets/css/explorer.css', 'assets/css/portfolio.css',
  'assets/js/common.js', 'assets/js/stats.js', 'assets/js/today.js', 'assets/js/browse.js', 'assets/js/trends.js',
  'assets/js/finance.js', 'assets/js/search.js', 'assets/js/explorer.js', 'assets/js/portfolio.js', 'assets/js/portfolio-page.js', 'assets/js/picker.js', 'assets/js/fundamentals-calc.js', 'assets/js/fundamentals.js', 'assets/js/compare-calc.js', 'assets/js/compare.js', 'explorer/sample/index.json', 'explorer/sample/portfolio.json', 'explorer/sec/index.json', 'explorer/sec-sample/index.json',
  'assets/vendor/chart.umd.min.js',
  'assets/icons/icon.svg', 'assets/icons/icon-192.png', 'assets/icons/icon-512.png',
  'assets/icons/icon-maskable-512.png', 'assets/icons/apple-touch-icon.png'
];
const DATA = ['data/history.csv', 'data/status.json'];
const scopeUrl = p => new URL(p, self.registration.scope).href;

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(VERSION)
      .then(cache => Promise.all(SHELL.map(p => cache.add(scopeUrl(p)).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function flagged(response) {
  const headers = new Headers(response.headers);
  headers.set('X-CS-Cache', '1');
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

async function networkFirstData(request) {
  const cache = await caches.open(VERSION);
  try {
    const fresh = await fetch(request, { cache: 'no-store' });
    if (fresh.ok) await cache.put(request.url.split('?')[0], fresh.clone());
    return fresh;
  } catch (err) {
    const hit = await cache.match(request.url.split('?')[0]);
    if (hit) return flagged(hit);
    return new Response('offline and no cached copy yet', { status: 503 });
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(VERSION);
  const hit = await cache.match(request, { ignoreSearch: true });
  const refresh = fetch(request).then(res => {
    if (res.ok && res.type === 'basic') cache.put(request, res.clone());
    return res;
  }).catch(() => null);
  if (hit) { refresh.catch(() => null); return hit; }
  const res = await refresh;
  if (res) return res;
  if (request.mode === 'navigate') return (await cache.match(scopeUrl('index.html'))) || Response.error();
  return Response.error();
}

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  const path = url.pathname.slice(new URL(self.registration.scope).pathname.length);
  if (path.startsWith('private-data/') || path.startsWith('api/')) return;      // private personal-edition data is never cached
  if (DATA.includes(path)) { event.respondWith(networkFirstData(request)); return; }
  event.respondWith(staleWhileRevalidate(request));
});
