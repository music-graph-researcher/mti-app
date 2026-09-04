/* Service worker: lo que convierte esta página en una app que funciona sin red.
 *
 * Todo es del mismo origen —Pyodide incluido, que viaja en vendor/— así que la
 * política es única: caché primero, revalidación silenciosa en segundo plano.
 * El intérprete pesa unos 12 MB y se precarga al instalar; por eso la primera
 * visita tarda y las siguientes abren al instante, con o sin red.
 */

// Subir este número en cada publicación: la caché es «primero lo guardado»,
// así que sin cambiarlo un móvil que ya tenga la app seguiría con la anterior.
const VERSION = "mti-movil-v6";
const CACHE_APP = `${VERSION}-app`;
const CACHE_MOTOR = `${VERSION}-motor`;

const RECURSOS = [
  "./",
  "index.html",
  "styles.css?v=6",
  "app.js?v=6",
  "worker.js?v=6",
  "manifest.webmanifest",
  "iconos/icono.svg",
  "py/mti_bridge.py",
  "py/mticore/__init__.py",
  "py/mticore/midi.py",
  "py/mticore/mti.py",
  "py/mticore/analysis.py",
  "py/mticore/compare.py",
  "py/mticore/context.py",
  "py/mticore/version.py",
  "py/mticore/portable.py",
  "py/mticore/hierarchy.py",
  "py/mticore/operations.py",
  "py/mticore/operational_topology.py",
  "py/mticore/persistent_homology.py",
  "py/mticore/ai_summaries.py",
  "ejemplos/beethoven_5_motif.mid",
  "ejemplos/guillermo_tell_motivo.mid",
  "corpus/corpus.json",
  "corpus/informe.json",
  "corpus/extendido.json",
  "validacion/informe.json",
  "validacion/resumen.md",
];

// El intérprete: aparte, porque son pocos archivos muy grandes y conviene
// poder invalidarlos sin tocar la caché de la app.
const MOTOR = [
  "vendor/pyodide/pyodide.mjs",
  "vendor/pyodide/pyodide.asm.mjs",
  "vendor/pyodide/pyodide.asm.wasm",
  "vendor/pyodide/python_stdlib.zip",
  "vendor/pyodide/pyodide-lock.json",
];

self.addEventListener("install", (evento) => {
  evento.waitUntil(
    caches.open(CACHE_APP)
      // addAll es todo-o-nada; añadir uno a uno evita que un recurso ausente
      // deje la app entera sin caché.
      .then((cache) => Promise.all(RECURSOS.map((r) => cache.add(r).catch(() => {}))))
      .then(() => caches.open(CACHE_MOTOR))
      .then((cache) => Promise.all(MOTOR.map((r) => cache.add(r).catch(() => {}))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches.keys()
      .then((claves) => Promise.all(
        claves.filter((c) => !c.startsWith(VERSION)).map((c) => caches.delete(c))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (evento) => {
  const peticion = evento.request;
  if (peticion.method !== "GET") return;
  const url = new URL(peticion.url);

  if (url.origin !== self.location.origin) return;
  const esMotor = url.pathname.includes("/vendor/pyodide/");
  evento.respondWith(cacheAntes(peticion, esMotor ? CACHE_MOTOR : CACHE_APP));
});

async function cacheAntes(peticion, nombreCache) {
  const cache = await caches.open(nombreCache);
  const guardado = await cache.match(peticion, { ignoreSearch: false });
  if (guardado) {
    // Revalidación silenciosa: si hay red, la próxima visita ya tiene lo nuevo.
    fetch(peticion).then((respuesta) => {
      if (respuesta && respuesta.ok) cache.put(peticion, respuesta.clone());
    }).catch(() => {});
    return guardado;
  }
  try {
    const respuesta = await fetch(peticion);
    if (respuesta && respuesta.ok) cache.put(peticion, respuesta.clone());
    return respuesta;
  } catch (error) {
    const alternativa = await cache.match("index.html");
    if (alternativa && peticion.mode === "navigate") return alternativa;
    throw error;
  }
}
