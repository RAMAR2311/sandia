/* Service worker de VetCare · Sandía.
   Estrategia deliberadamente simple: cachea el "app shell" estático (CSS/JS/
   fuentes/logo) para que la interfaz cargue instantáneamente y funcione sin
   red, y muestra static/offline.html cuando una navegación falla por falta de
   conexión. NO cachea respuestas HTML dinámicas ni datos (historias clínicas,
   inventario, ventas): esos siempre deben venir frescos del servidor. */

const VERSION = 'v1';
const CACHE_SHELL = `vetcare-shell-${VERSION}`;

const ARCHIVOS_SHELL = [
  '/static/css/sandia.css',
  '/static/css/fonts.css',
  '/static/vendor/bootstrap/bootstrap.min.css',
  '/static/vendor/bootstrap/bootstrap.bundle.min.js',
  '/static/vendor/bootstrap-icons/bootstrap-icons.min.css',
  '/static/vendor/bootstrap-icons/fonts/bootstrap-icons.woff2',
  '/static/js/app.js',
  '/static/img/logo.svg',
  '/static/img/favicon.svg',
  '/static/fonts/fredoka-variable.woff2',
  '/static/fonts/nunito-variable.woff2',
  '/static/offline.html',
];

self.addEventListener('install', (evento) => {
  evento.waitUntil(
    caches.open(CACHE_SHELL).then((cache) => cache.addAll(ARCHIVOS_SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (evento) => {
  evento.waitUntil(
    caches.keys().then((nombres) =>
      Promise.all(nombres.filter((n) => n !== CACHE_SHELL).map((n) => caches.delete(n)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (evento) => {
  const peticion = evento.request;
  if (peticion.method !== 'GET') { return; }

  const url = new URL(peticion.url);

  // Navegación de página completa: red primero, y si falla (sin conexión),
  // la página offline. Nunca sirve una vista clínica/POS "vieja" desde caché.
  if (peticion.mode === 'navigate') {
    evento.respondWith(
      fetch(peticion).catch(() => caches.match('/static/offline.html'))
    );
    return;
  }

  // Archivos estáticos del "app shell": caché primero, con actualización en
  // segundo plano (stale-while-revalidate).
  if (url.pathname.startsWith('/static/')) {
    evento.respondWith(
      caches.open(CACHE_SHELL).then((cache) =>
        cache.match(peticion).then((respuestaCache) => {
          const actualizar = fetch(peticion)
            .then((respuestaRed) => {
              cache.put(peticion, respuestaRed.clone());
              return respuestaRed;
            })
            .catch(() => respuestaCache);
          return respuestaCache || actualizar;
        })
      )
    );
  }
  // Todo lo demás (APIs, datos) pasa directo a la red sin interceptar.
});
