// TATANGA Hub - Service Worker (PWA)
const CACHE_NAME = 'tatanga-hub-v1';
const STATIC_ASSETS = [
    '/',
    '/static/css/hub.css',
    '/static/js/hub.js',
    '/static/manifest.json',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css',
];

// Install: cache static assets
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS);
        })
    );
    self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter((key) => key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            );
        })
    );
    self.clients.claim();
});

// Fetch: network-first for API, cache-first for static
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // API istekleri icin always network
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws')) {
        event.respondWith(fetch(event.request));
        return;
    }

    // Static assets icin cache-first
    event.respondWith(
        caches.match(event.request).then((cached) => {
            if (cached) return cached;
            return fetch(event.request).then((response) => {
                // Cache successful responses
                if (response.status === 200) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, clone);
                    });
                }
                return response;
            }).catch(() => {
                // Offline fallback
                if (event.request.mode === 'navigate') {
                    return new Response('<h1>TATANGA Hub - Offline</h1><p>Internet baglantisi gerekli</p>', {
                        headers: {'Content-Type': 'text/html; charset=utf-8'}
                    });
                }
            });
        })
    );
});
