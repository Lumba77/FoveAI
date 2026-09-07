// FoveAI PWA SERVICE WORKER — EMERGENCY SELF-DESTRUCT
// Unregisters itself immediately to fix the "Offline" lock without wiping IndexedDB.

self.addEventListener('install', (event) => {
  console.log('[PWA SW] Installed bypass version.');
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  console.log('[PWA SW] Activated bypass version. Unregistering...');
  event.waitUntil(
    self.registration.unregister().then(() => {
      return self.clients.claim();
    })
  );
});

self.addEventListener('fetch', (event) => {
  // Do nothing. Let the browser handle the network request entirely natively.
  // This completely bypasses the .catch() that was returning "Offline".
  return;
});