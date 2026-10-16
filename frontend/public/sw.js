/* Service worker ETSL ERP — mode hors-ligne terrain (CL-OM-08).
 *
 * Stratégies :
 *  - navigation (pages)        : réseau d'abord, repli sur la coquille de l'application en cache ;
 *  - /assets/* (fichiers hachés): cache d'abord (immuables) ;
 *  - API en lecture            : réseau d'abord + copie locale UNIQUEMENT pour les données terrain
 *                                (liste blanche ci-dessous) — jamais la paie, la compta, le juridique… ;
 *  - tout le reste / écritures : réseau (les écritures hors-ligne passent par la file d'attente de l'appli).
 *
 * Le cache d'API est vidé à la déconnexion (message `clear-api-cache`) : une session suivante sur le même
 * téléphone ne retrouve pas les données du précédent utilisateur.
 */
const VERSION = "v1";
const SHELL_CACHE = `etls-shell-${VERSION}`;
const ASSET_CACHE = `etls-assets-${VERSION}`;
const API_CACHE = `etls-api-${VERSION}`;

const SCOPE = new URL(self.registration.scope).pathname; // "/" ou "/erp_etsl/"
const SHELL_URLS = [SCOPE, `${SCOPE}manifest.webmanifest`, `${SCOPE}icons/icon-192.png`, `${SCOPE}etsl-logo.jpg`];

// Données de référence nécessaires à la saisie terrain (lecture seule, non financières).
const API_WHITELIST = [
  /\/api\/operations\/ordres\/$/,
  /\/api\/achats\/receipts\/$/,
  /\/api\/achats\/order-lines\/$/,
  /\/api\/hse\/permis\/$/,
  /\/api\/qualite\/controles\/$/,
  /\/api\/rh-paie\/mon-espace\/profil\/$/,
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL_CACHE).then((c) => c.addAll(SHELL_URLS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => ![SHELL_CACHE, ASSET_CACHE, API_CACHE].includes(k)).map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("message", (event) => {
  if (event.data === "clear-api-cache") event.waitUntil(caches.delete(API_CACHE));
});

async function networkFirst(request, cacheName, fallbackUrl) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch (err) {
    const cached = (await cache.match(request)) || (fallbackUrl && (await caches.match(fallbackUrl)));
    if (cached) return cached;
    throw err;
  }
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) cache.put(request, response.clone());
  return response;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return; // écritures : jamais interceptées
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(networkFirst(request, SHELL_CACHE, SCOPE));
  } else if (url.pathname.startsWith(`${SCOPE}assets/`)) {
    event.respondWith(cacheFirst(request, ASSET_CACHE));
  } else if (url.pathname.includes("/api/")) {
    if (API_WHITELIST.some((re) => re.test(url.pathname))) {
      event.respondWith(networkFirst(request, API_CACHE));
    }
  } else if (SHELL_URLS.includes(url.pathname)) {
    event.respondWith(networkFirst(request, SHELL_CACHE));
  }
});
