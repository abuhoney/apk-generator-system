/**
 * sw.js — v3.0 Service Worker
 *
 * Transparent offline-first cache. No manual IndexedDB code needed in the app.
 * Strategy: NetworkFirst (try network, fallback to cache, serve offline page).
 *
 * The app works offline automatically — zero configuration needed.
 */
const CACHE_NAME = 'html-to-apk-v3';
const ASSETS_TO_CACHE = [
  './',
  './index.html',
  './core_engine.js',
  './components.js',
  './sw.js',
];

// ═════════════════════════════════════════════════════════════════════
// INSTALL — Pre-cache core assets
// ═════════════════════════════════════════════════════════════════════
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE).catch(() => {});
    })
  );
  self.skipWaiting();
});

// ═════════════════════════════════════════════════════════════════════
// ACTIVATE — Clean old caches
// ═════════════════════════════════════════════════════════════════════
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) => {
      return Promise.all(
        names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n))
      );
    })
  );
  self.clients.claim();
});

// ═════════════════════════════════════════════════════════════════════
// FETCH — NetworkFirst strategy
// ═════════════════════════════════════════════════════════════════════
self.addEventListener('fetch', (event) => {
  // Skip non-GET requests (POST/PUT go to server)
  if (event.request.method !== 'GET') return;

  // Skip cross-origin requests (e.g., CDN scripts)
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Success: cache a copy and return
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => {
          cache.put(event.request, clone).catch(() => {});
        });
        return response;
      })
      .catch(() => {
        // Offline: try cache
        return caches.match(event.request).then((cached) => {
          if (cached) return cached;
          // If navigating to a page, serve index.html
          if (event.request.mode === 'navigate') {
            return caches.match('./index.html');
          }
          return new Response('Offline', { status: 503, statusText: 'Offline' });
        });
      })
  );
});

// ═════════════════════════════════════════════════════════════════════
// BACKGROUND SYNC — Push queued changes when back online
// ═════════════════════════════════════════════════════════════════════
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-queue') {
    event.waitUntil(
      self.clients.matchAll().then((clients) => {
        clients.forEach((client) => {
          client.postMessage({ type: 'SYNC_TRIGGER' });
        });
      })
    );
  }
});

console.log('[ServiceWorker] v3.0 registered');
