/* Motor MTI en un hilo aparte.
 *
 * Carga Pyodide (CPython compilado a WebAssembly) y monta dentro los mismos
 * módulos que usa `backend/server.py`. La interfaz nunca calcula: manda
 * mensajes aquí y recibe JSON. Al vivir en un worker, un análisis pesado no
 * congela la pantalla.
 */

// Pyodide viaja dentro de la carpeta (vendor/pyodide, ~13 MB). No se toca
// ningún CDN: la app funciona sin red desde el primer segundo y no depende de
// que jsdelivr sea accesible en la sala donde se presente.
import { loadPyodide } from "./vendor/pyodide/pyodide.mjs";

const PYODIDE_URL = new URL("vendor/pyodide/", self.location.href).href;

// El núcleo MTI, copiado sin cambios desde backend/. El orden es irrelevante:
// se escriben todos en el sistema de archivos virtual antes de importar nada.
const ARCHIVOS_PY = [
  "mti_bridge.py",
  "mticore/__init__.py",
  "mticore/midi.py",
  "mticore/mti.py",
  "mticore/analysis.py",
  "mticore/compare.py",
  "mticore/context.py",
  "mticore/version.py",
  "mticore/portable.py",
];

let pyodide = null;
let puente = null;
let arranque = null;

function avisar(estado, texto) {
  self.postMessage({ tipo: "motor", estado, texto });
}

async function arrancarMotor() {
  avisar("cargando", "Arrancando el intérprete de Python…");
  pyodide = await loadPyodide({
    indexURL: PYODIDE_URL,
    stdout: () => {},
    stderr: (linea) => console.warn("[python]", linea),
  });

  avisar("cargando", "Montando el núcleo MTI…");
  pyodide.FS.mkdirTree("/mti/mticore");
  await Promise.all(
    ARCHIVOS_PY.map(async (ruta) => {
      const url = new URL(`py/${ruta}`, self.location.href);
      const respuesta = await fetch(url);
      if (!respuesta.ok) {
        throw new Error(`No se pudo cargar ${ruta} (HTTP ${respuesta.status})`);
      }
      pyodide.FS.writeFile(`/mti/${ruta}`, await respuesta.text());
    })
  );

  pyodide.runPython("import sys\nif '/mti' not in sys.path: sys.path.insert(0, '/mti')");
  puente = pyodide.pyimport("mti_bridge");

  // Un análisis mínimo en frío deja el intérprete caliente: la primera pulsación
  // real del usuario ya no paga el coste de importar fractions, itertools, etc.
  const version = JSON.parse(puente.version());
  avisar("listo", "Motor listo");
  return version.software_version;
}

function asegurarMotor() {
  if (!arranque) {
    arranque = arrancarMotor().catch((error) => {
      arranque = null; // permite reintentar tras un fallo de red
      avisar("error", "El motor no arrancó");
      throw error;
    });
  }
  return arranque;
}

const acciones = {
  async preparar() {
    const version = await asegurarMotor();
    return { software_version: version };
  },

  async inspeccionar({ b64 }) {
    await asegurarMotor();
    return JSON.parse(puente.inspect(b64));
  },

  async analizar({ b64, tonica, indices, nombre }) {
    await asegurarMotor();
    return JSON.parse(
      puente.analyze(b64, tonica, JSON.stringify(indices), nombre)
    );
  },

  async portable({ resultado }) {
    await asegurarMotor();
    return JSON.parse(puente.portable(JSON.stringify(resultado)));
  },

  async comparar({ familiaA, familiaB, parametros, contextoA, contextoB }) {
    await asegurarMotor();
    if (contextoA && contextoB) {
      return JSON.parse(
        puente.compare_with_context(
          JSON.stringify(familiaA),
          JSON.stringify(familiaB),
          JSON.stringify(parametros),
          JSON.stringify(contextoA),
          JSON.stringify(contextoB)
        )
      );
    }
    return JSON.parse(
      puente.compare(
        JSON.stringify(familiaA),
        JSON.stringify(familiaB),
        JSON.stringify(parametros)
      )
    );
  },
};

self.onmessage = async (evento) => {
  const { id, accion, args } = evento.data || {};
  const ejecutar = acciones[accion];
  if (!ejecutar) {
    self.postMessage({ id, ok: false, error: `Acción desconocida: ${accion}` });
    return;
  }
  try {
    const datos = await ejecutar(args || {});
    self.postMessage({ id, ok: true, datos });
  } catch (error) {
    self.postMessage({ id, ok: false, error: String(error && error.message || error) });
  }
};
