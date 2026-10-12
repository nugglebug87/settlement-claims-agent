'use strict';
// Installation only: never cache profile, claim, PDF, session, or API responses.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
  if (event.request.method === 'GET' && event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).catch(() => new Response(
      'Settlement Assistant needs an internet connection. Reconnect, then reopen the app.',
      {status:503, headers:{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store'}}
    )));
  }
});
