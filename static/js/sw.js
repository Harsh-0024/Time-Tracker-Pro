/*
 * Service worker: only gives the installed app a proper "You're offline" page.
 * Nothing else is cached - every page and API call still goes to the network,
 * so there is no stale content to worry about after a deploy.
 */
const OFFLINE_CACHE = 'ttp-offline-v1';
const OFFLINE_URL = '/offline';

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(OFFLINE_CACHE)
            .then((cache) => cache.add(new Request(OFFLINE_URL, { cache: 'reload' })))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        const keys = await caches.keys();
        await Promise.all(keys.filter((key) => key !== OFFLINE_CACHE).map((key) => caches.delete(key)));
        // Lets the browser start the page request while the worker boots.
        if (self.registration.navigationPreload) {
            await self.registration.navigationPreload.enable();
        }
        await self.clients.claim();
    })());
});

self.addEventListener('fetch', (event) => {
    if (event.request.mode !== 'navigate') return;
    event.respondWith((async () => {
        try {
            const preloaded = await event.preloadResponse;
            if (preloaded) return preloaded;
            return await fetch(event.request);
        } catch (err) {
            const offline = await caches.match(OFFLINE_URL);
            return offline || Response.error();
        }
    })());
});
