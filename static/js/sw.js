/* Service worker.
   ------------------------------------------------------------------
   Chrome will not offer "install" without one that handles fetch, so this
   exists mostly to make the shop installable. It deliberately does almost
   nothing else: the menu, prices and stock change during the day, and a
   cached copy of those would show a customer yesterday's shop.

   So: network first, always. The cache only answers when the network is
   gone, which turns a dead tab into the shop's phone number instead. */

const CACHE = 'cobong-v1';
const OFFLINE_URL = '/offline';

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE).then((c) => c.add(OFFLINE_URL)).then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(
                keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
            .then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    const req = event.request;

    // Never touch anything that changes the shop: orders, the cart, admin.
    if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin) {
        return;
    }

    event.respondWith(
        fetch(req).catch(() => {
            // offline: a page request gets the fallback, everything else fails
            if (req.mode === 'navigate') {
                return caches.match(OFFLINE_URL);
            }
            return caches.match(req);
        })
    );
});
