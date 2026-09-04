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
  // Capítulos 5 y 6. `ai_summaries` es un sustituto inerte: el módulo original
  // llama a una API externa y no viaja en esta app.
  "mticore/hierarchy.py",
  "mticore/operations.py",
  "mticore/operational_topology.py",
  "mticore/persistent_homology.py",
  "mticore/ai_summaries.py",
];

let pyodide = null;
let puente = null;
let arranque = null;
let corpusCargado = null;

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

/* El corpus solo se carga si el usuario entra en esa parte de la app: son
   44 KB y 50 conversiones que no tiene sentido pagar en cada arranque. */
async function asegurarCorpus() {
  if (!corpusCargado) {
    corpusCargado = (async () => {
      await asegurarMotor();
      avisar("cargando", "Cargando el corpus…");
      const respuesta = await fetch(new URL("corpus/corpus.json", self.location.href));
      if (!respuesta.ok) throw new Error(`No se pudo cargar el corpus (HTTP ${respuesta.status})`);
      const carga = JSON.parse(puente.load_corpus(await respuesta.text()));
      if (!carga.ok) throw new Error(carga.error);
      avisar("listo", "Motor listo");
      return carga;
    })().catch((error) => { corpusCargado = null; throw error; });
  }
  return corpusCargado;
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

  async corpus() {
    return asegurarCorpus();
  },

  async rankearCorpus({ familia, parametros }) {
    await asegurarCorpus();
    return JSON.parse(
      puente.rank_corpus(JSON.stringify(familia), JSON.stringify(parametros))
    );
  },

  async opFixtures() {
    await asegurarMotor();
    return JSON.parse(puente.operations_fixtures());
  },

  async opTrayectoria({ origen, destino, acciones, parametros }) {
    await asegurarMotor();
    return JSON.parse(puente.operations_trajectory(
      JSON.stringify(origen), JSON.stringify(destino),
      JSON.stringify(acciones || []), JSON.stringify(parametros)));
  },

  async opAlcance({ origen, destino, parametros }) {
    await asegurarMotor();
    return JSON.parse(puente.operations_reachability(
      JSON.stringify(origen), JSON.stringify(destino), JSON.stringify(parametros)));
  },

  async opBusqueda({ origen, destino, parametros, envolvente }) {
    await asegurarMotor();
    return JSON.parse(puente.operations_search(
      JSON.stringify(origen), JSON.stringify(destino),
      JSON.stringify(parametros), JSON.stringify(envolvente || {})));
  },

  async opTopologia({ parametros }) {
    await asegurarMotor();
    return JSON.parse(puente.operations_topology(JSON.stringify(parametros)));
  },

  async opInforme() {
    await asegurarMotor();
    return JSON.parse(puente.operations_report());
  },

  async jerarquiaFixtures() {
    await asegurarMotor();
    return JSON.parse(puente.hierarchy_fixtures());
  },

  async jerarquiaDesdeFamilia({ familia }) {
    await asegurarMotor();
    return JSON.parse(puente.configuration_from_family(JSON.stringify(familia)));
  },

  async jerarquiaConstituir({ configuracion }) {
    await asegurarMotor();
    return JSON.parse(puente.hierarchy_constitute(JSON.stringify(configuracion)));
  },

  async jerarquiaPreimagen({ motivo }) {
    await asegurarMotor();
    return JSON.parse(puente.hierarchy_preimage(JSON.stringify(motivo)));
  },

  async jerarquiaElevacion({ configuracion, operador, descriptor, delta }) {
    await asegurarMotor();
    return JSON.parse(
      puente.hierarchy_lift(
        JSON.stringify(configuracion), operador,
        JSON.stringify(descriptor), JSON.stringify(delta ?? null)
      )
    );
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
