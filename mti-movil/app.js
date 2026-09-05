/* MTI móvil · interfaz
 *
 * Responsabilidad única: leer el MIDI, dejar elegir fragmento y tónica, y
 * presentar lo que devuelve el núcleo. Ni un solo cálculo del marco vive aquí;
 * todo pasa por `worker.js` → `mti_bridge.py` → `mticore/`.
 */

"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const NOMBRES = ["Do", "Do♯", "Re", "Re♯", "Mi", "Fa", "Fa♯", "Sol", "Sol♯", "La", "La♯", "Si"];
const NEGRAS = new Set([1, 3, 6, 8, 10]);
const LIMITE_GRAFO = 200;   // eventos por encima de los cuales no se dibuja solo
const LIMITE_AVISO = 250;   // eventos por encima de los cuales se avisa antes

const estado = {
  archivo: null,     // { nombre, b64, bytes }
  notas: [],         // salida de inspect()
  pistas: new Set(),
  canales: new Set(),
  rango: null,       // { t0, t1 } en ticks, o null = todo
  tonica: 60,
  resultado: null,
  ultimoSvg: null,
};

/* ══════════════════ Motor ══════════════════ */

const motor = (() => {
  let worker = null;
  const pendientes = new Map();
  let siguiente = 0;

  function crear() {
    worker = new Worker("worker.js?v=7", { type: "module" });
    worker.onmessage = ({ data }) => {
      if (data.tipo === "motor") {
        pintarEstadoMotor(data.estado, data.texto);
        return;
      }
      const pendiente = pendientes.get(data.id);
      if (!pendiente) return;
      pendientes.delete(data.id);
      data.ok ? pendiente.resolver(data.datos) : pendiente.rechazar(new Error(data.error));
    };
    worker.onerror = (evento) => {
      pintarEstadoMotor("error", "El motor falló");
      console.error("worker", evento);
    };
  }
  crear();

  const enviar = (accion, args) =>
    new Promise((resolver, rechazar) => {
      const id = ++siguiente;
      pendientes.set(id, { resolver, rechazar });
      worker.postMessage({ id, accion, args });
    });

  // Python dentro del worker no se puede interrumpir a media función: la única
  // forma real de abortar un cálculo desmedido es matar el hilo y levantar otro.
  // Cuesta unos segundos de rearranque, y es preferible a quedarse atrapado.
  enviar.cancelar = () => {
    worker.terminate();
    pendientes.forEach((p) => p.rechazar(new Error("CANCELADO")));
    pendientes.clear();
    crear();
    pintarEstadoMotor("cargando", "Reiniciando el motor…");
    enviar("preparar", {}).catch(() => {});
  };

  return enviar;
})();

function pintarEstadoMotor(estadoMotor, texto) {
  $("#motor-texto").textContent = texto;
  $(".punto").dataset.estado = estadoMotor;
}

/* ══════════════════ Utilidades ══════════════════ */

function aBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  const trozo = 0x8000;
  let cadena = "";
  for (let i = 0; i < bytes.length; i += trozo) {
    cadena += String.fromCharCode.apply(null, bytes.subarray(i, i + trozo));
  }
  return btoa(cadena);
}

function nombreNota(midi) {
  return `${NOMBRES[((midi % 12) + 12) % 12]}${Math.floor(midi / 12) - 1}`;
}

function brindis(mensaje, ms = 2600) {
  const caja = $("#brindis");
  caja.textContent = mensaje;
  caja.hidden = false;
  clearTimeout(brindis.reloj);
  brindis.reloj = setTimeout(() => { caja.hidden = true; }, ms);
}

function mostrarAviso(selector, html, suave = false) {
  const caja = $(selector);
  caja.innerHTML = html;
  caja.classList.toggle("suave", suave);
  caja.hidden = false;
}

function ocultarAviso(selector) { $(selector).hidden = true; }

function descargar(contenido, tipo, nombre) {
  const blob = new Blob([contenido], { type: tipo });
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombre;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

function baseNombre(nombre) {
  return (nombre || "motivo").replace(/\.[^.]+$/, "").replace(/[^\w.-]+/g, "_");
}

/* ══════════════════ Navegación ══════════════════ */

function irA(idPanel) {
  $$(".panel").forEach((p) => p.classList.toggle("activo", p.id === idPanel));
  $$(".paso").forEach((b) => {
    const activo = b.dataset.panel === idPanel;
    b.classList.toggle("activo", activo);
    // En una pantalla estrecha la barra de pasos no cabe entera: el paso actual
    // tiene que traerse a la vista o el usuario pierde de vista dónde está.
    if (activo) b.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
  // Un canvas dentro de un panel oculto mide cero. Solo se puede dibujar
  // cuando el panel ya está visible y el navegador ha hecho el reflow.
  if (idPanel === "p-fragmento" && estado.notas.length) {
    requestAnimationFrame(dibujarRollo);
  }
  if (idPanel === "p-cuadricula" && cuadricula.datos) {
    requestAnimationFrame(redibujarCuadricula);
  }
}

function habilitarPaso(idPanel, habilitado = true) {
  const boton = $$(".paso").find((b) => b.dataset.panel === idPanel);
  if (boton) boton.disabled = !habilitado;
}

$$(".paso").forEach((boton) => {
  boton.addEventListener("click", () => {
    if (boton.disabled) return;
    if (boton.dataset.panel === "p-biblioteca") pintarBiblioteca();
    if (boton.dataset.panel === "p-corpus") pintarCorpus();
    if (boton.dataset.panel === "p-validacion") pintarValidacion();
    if (boton.dataset.panel === "p-extendido") pintarExtendido();
    if (boton.dataset.panel === "p-jerarquia") pintarJerarquia();
    if (boton.dataset.panel === "p-operacional") pintarOperacional();
    if (boton.dataset.panel === "p-cuadricula") pintarCuadricula();
    irA(boton.dataset.panel);
  });
});

/* ══════════════════ 1 · Carga del archivo ══════════════════ */

const zona = $("#zona-carga");
$("#archivo").addEventListener("change", (e) => {
  const archivo = e.target.files && e.target.files[0];
  if (archivo) cargarArchivo(archivo);
});

["dragenter", "dragover"].forEach((tipo) =>
  zona.addEventListener(tipo, (e) => { e.preventDefault(); zona.classList.add("encima"); })
);
["dragleave", "drop"].forEach((tipo) =>
  zona.addEventListener(tipo, (e) => { e.preventDefault(); zona.classList.remove("encima"); })
);
zona.addEventListener("drop", (e) => {
  const archivo = e.dataTransfer.files && e.dataTransfer.files[0];
  if (archivo) cargarArchivo(archivo);
});

$("#ejemplos").addEventListener("click", async (e) => {
  const boton = e.target.closest("button[data-src]");
  if (!boton) return;
  ocultarAviso("#aviso-archivo");
  try {
    const respuesta = await fetch(boton.dataset.src);
    if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
    const buffer = await respuesta.arrayBuffer();
    await procesarMidi(buffer, boton.dataset.src.split("/").pop());
  } catch (error) {
    mostrarAviso("#aviso-archivo", `<b>No se pudo abrir el ejemplo</b>${error.message}`);
  }
});

async function cargarArchivo(archivo) {
  ocultarAviso("#aviso-archivo");
  if (archivo.size > 16 * 1024 * 1024) {
    mostrarAviso("#aviso-archivo", "<b>Archivo demasiado grande</b>El límite es 16 MB, el mismo del servidor del proyecto.");
    return;
  }
  await procesarMidi(await archivo.arrayBuffer(), archivo.name);
}

async function procesarMidi(buffer, nombre) {
  pintarEstadoMotor("cargando", "Leyendo el MIDI…");
  const b64 = aBase64(buffer);
  try {
    const datos = await motor("inspeccionar", { b64 });
    if (!datos.ok) {
      mostrarAviso("#aviso-archivo", `<b>MIDI no admitido</b>${datos.error}`);
      pintarEstadoMotor("listo", "Motor listo");
      return;
    }
    estado.archivo = { nombre, b64, bytes: buffer.byteLength, sha256: datos.sha256 };
    estado.notas = datos.notes;
    estado.pistas = new Set(datos.tracks_present);
    estado.canales = new Set(datos.channels_present);
    estado.rango = null;
    estado.resultado = null;

    if (!datos.notes.length) {
      mostrarAviso("#aviso-archivo", "<b>Sin notas utilizables</b>El archivo no contiene ninguna nota con duración positiva.");
      return;
    }

    pintarFiltros(datos);
    actualizarSeleccion();
    habilitarPaso("p-fragmento");
    habilitarPaso("p-tonica");
    habilitarPaso("p-resultado", false);

    if (datos.warnings.length) {
      mostrarAviso("#aviso-tamano", `<b>${datos.warnings.length} aviso(s) de lectura</b>${datos.warnings.slice(0, 3).join("<br>")}`, true);
    }
    irA("p-fragmento");
    pintarEstadoMotor("listo", "Motor listo");
  } catch (error) {
    mostrarAviso("#aviso-archivo", `<b>Error al leer</b>${error.message}`);
    pintarEstadoMotor("error", "Error");
  }
}

/* ══════════════════ 2 · Fragmento ══════════════════ */

function pintarFiltros(datos) {
  const caja = $("#filtros");
  caja.innerHTML = "";
  const hacerGrupo = (etiqueta, valores, conjunto, clave) => {
    if (valores.length < 2) return; // un solo valor no es un filtro, es ruido
    valores.forEach((valor) => {
      const boton = document.createElement("button");
      boton.type = "button";
      boton.className = "filtro";
      boton.textContent = `${etiqueta} ${valor + 1}`;
      boton.setAttribute("aria-pressed", "true");
      boton.addEventListener("click", () => {
        const activo = boton.getAttribute("aria-pressed") === "true";
        if (activo && conjunto.size === 1) return; // nunca dejar la vista vacía
        activo ? conjunto.delete(valor) : conjunto.add(valor);
        boton.setAttribute("aria-pressed", String(!activo));
        dibujarRollo();
        actualizarSeleccion();
      });
      caja.appendChild(boton);
      void clave;
    });
  };
  hacerGrupo("Pista", datos.tracks_present, estado.pistas, "track");
  hacerGrupo("Canal", datos.channels_present, estado.canales, "channel");
}

function notasVisibles() {
  return estado.notas.filter((n) => estado.pistas.has(n.track) && estado.canales.has(n.channel));
}

function notasSeleccionadas() {
  const visibles = notasVisibles();
  if (!estado.rango) return visibles;
  const { t0, t1 } = estado.rango;
  return visibles.filter((n) => n.onset >= t0 && n.onset <= t1);
}

const lienzo = $("#rollo");
const ctx = lienzo.getContext("2d");
let metricas = null; // { tMin, tMax, pMin, pMax, ancho, alto }

function dibujarRollo() {
  const visibles = notasVisibles();
  $("#rollo-vacio").hidden = visibles.length > 0;
  if (!visibles.length) { metricas = null; return; }

  const dpr = window.devicePixelRatio || 1;
  const ancho = lienzo.clientWidth;
  const alto = lienzo.clientHeight;
  lienzo.width = Math.round(ancho * dpr);
  lienzo.height = Math.round(alto * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, ancho, alto);

  const estilo = getComputedStyle(document.body);
  const tinta = estilo.getPropertyValue("--tinta").trim();
  const tinta3 = estilo.getPropertyValue("--tinta-3").trim();
  const acento = estilo.getPropertyValue("--acento").trim();
  const linea = estilo.getPropertyValue("--linea").trim();

  const tMin = Math.min(...visibles.map((n) => n.onset));
  const tMax = Math.max(...visibles.map((n) => n.onset + n.duration));
  const pMin = Math.min(...visibles.map((n) => n.pitch));
  const pMax = Math.max(...visibles.map((n) => n.pitch));
  const margen = 12;
  const spanT = Math.max(1, tMax - tMin);
  const spanP = Math.max(1, pMax - pMin + 1);
  metricas = { tMin, tMax, pMin, pMax, ancho, alto, margen, spanT, spanP };

  const x = (tick) => margen + ((tick - tMin) / spanT) * (ancho - margen * 2);
  const y = (pitch) => alto - margen - ((pitch - pMin + 0.5) / spanP) * (alto - margen * 2);
  const grosor = Math.max(2.5, Math.min(9, (alto - margen * 2) / spanP - 1.5));

  // Rejilla de octavas: da escala vertical sin saturar
  ctx.strokeStyle = linea;
  ctx.lineWidth = 1;
  for (let p = Math.ceil(pMin / 12) * 12; p <= pMax; p += 12) {
    ctx.beginPath();
    ctx.moveTo(margen, Math.round(y(p)) + 0.5);
    ctx.lineTo(ancho - margen, Math.round(y(p)) + 0.5);
    ctx.stroke();
  }

  // Banda de selección
  if (estado.rango) {
    ctx.fillStyle = acento;
    ctx.globalAlpha = 0.14;
    ctx.fillRect(x(estado.rango.t0), 0, Math.max(2, x(estado.rango.t1) - x(estado.rango.t0)), alto);
    ctx.globalAlpha = 1;
    ctx.strokeStyle = acento;
    ctx.lineWidth = 1.5;
    [estado.rango.t0, estado.rango.t1].forEach((t) => {
      ctx.beginPath();
      ctx.moveTo(Math.round(x(t)) + 0.5, 0);
      ctx.lineTo(Math.round(x(t)) + 0.5, alto);
      ctx.stroke();
    });
  }

  // Notas: las seleccionadas en tinta, el resto atenuadas
  const dentro = new Set(notasSeleccionadas().map((n) => n.i));
  ctx.lineCap = "round";
  ctx.lineWidth = grosor;
  visibles.forEach((n) => {
    const activa = dentro.has(n.i);
    ctx.strokeStyle = activa ? (estado.rango ? acento : tinta) : tinta3;
    ctx.globalAlpha = activa ? 0.95 : 0.28;
    const x0 = x(n.onset);
    const x1 = Math.max(x0 + grosor * 0.6, x(n.onset + n.duration));
    ctx.beginPath();
    ctx.moveTo(x0, y(n.pitch));
    ctx.lineTo(x1, y(n.pitch));
    ctx.stroke();
  });
  ctx.globalAlpha = 1;
}

/* Arrastre de selección sobre el rollo */
let arrastre = null;

function tickDesdeX(clientX) {
  if (!metricas) return null;
  const caja = lienzo.getBoundingClientRect();
  const relativo = (clientX - caja.left - metricas.margen) / (metricas.ancho - metricas.margen * 2);
  const acotado = Math.min(1, Math.max(0, relativo));
  return Math.round(metricas.tMin + acotado * metricas.spanT);
}

lienzo.addEventListener("pointerdown", (e) => {
  if (!metricas) return;
  lienzo.setPointerCapture(e.pointerId);
  arrastre = { inicio: tickDesdeX(e.clientX), x0: e.clientX };
});

lienzo.addEventListener("pointermove", (e) => {
  if (!arrastre) return;
  const actual = tickDesdeX(e.clientX);
  if (Math.abs(e.clientX - arrastre.x0) < 4) return;
  e.preventDefault();
  estado.rango = { t0: Math.min(arrastre.inicio, actual), t1: Math.max(arrastre.inicio, actual) };
  dibujarRollo();
  actualizarSeleccion();
});

lienzo.addEventListener("pointerup", (e) => {
  if (!arrastre) return;
  const movido = Math.abs(e.clientX - arrastre.x0) >= 4;
  arrastre = null;
  if (!movido) { estado.rango = null; dibujarRollo(); actualizarSeleccion(); }
});

lienzo.addEventListener("pointercancel", () => { arrastre = null; });

$("#sel-todo").addEventListener("click", () => {
  estado.rango = null;
  estado.pistas = new Set(estado.notas.map((n) => n.track));
  estado.canales = new Set(estado.notas.map((n) => n.channel));
  $$("#filtros .filtro").forEach((b) => b.setAttribute("aria-pressed", "true"));
  dibujarRollo(); actualizarSeleccion();
});

$("#sel-limpiar").addEventListener("click", () => {
  estado.rango = null;
  dibujarRollo(); actualizarSeleccion();
});

$("#sel-primeras").addEventListener("click", () => {
  const visibles = notasVisibles();
  if (!visibles.length) return;
  const primeras = visibles.slice(0, 16);
  estado.rango = {
    t0: primeras[0].onset,
    t1: primeras[primeras.length - 1].onset,
  };
  dibujarRollo(); actualizarSeleccion();
});

function actualizarSeleccion() {
  const elegidas = notasSeleccionadas();
  const total = estado.notas.length;
  const resumen = $("#resumen-sel");

  if (!elegidas.length) {
    resumen.innerHTML = "<b>Ninguna nota seleccionada.</b> Arrastra sobre el rollo o pulsa «Todo el archivo».";
    $("#ir-tonica").disabled = true;
    ocultarAviso("#aviso-tamano");
    return;
  }

  const alturas = elegidas.map((n) => n.pitch);
  const duracion = Math.max(...elegidas.map((n) => n.onset + n.duration)) - Math.min(...elegidas.map((n) => n.onset));
  resumen.innerHTML =
    `<b>${elegidas.length}</b> nota(s) de ${total} · registro <b>${nombreNota(Math.min(...alturas))}</b>–<b>${nombreNota(Math.max(...alturas))}</b>` +
    ` · extensión <b>${duracion}</b> ticks` +
    (estado.rango ? "" : " · <i>archivo completo</i>");

  $("#ir-tonica").disabled = false;

  if (elegidas.length > LIMITE_AVISO) {
    mostrarAviso(
      "#aviso-tamano",
      `<b>Fragmento muy grande (${elegidas.length} eventos)</b>` +
      `El grafo tendrá miles de aristas y el cálculo puede tardar decenas de segundos en un móvil. ` +
      `Un motivo, en el sentido del marco, rara vez pasa de unas pocas decenas de notas. Puedes continuar igualmente.`,
      true
    );
  } else {
    ocultarAviso("#aviso-tamano");
  }
}

$("#ir-tonica").addEventListener("click", () => {
  pintarSugerencias();
  irA("p-tonica");
});

if ("ResizeObserver" in window) {
  let anchoPrevio = 0;
  new ResizeObserver(() => {
    const ancho = lienzo.clientWidth;
    if (ancho && ancho !== anchoPrevio && estado.notas.length) {
      anchoPrevio = ancho;
      dibujarRollo();
    }
  }).observe(lienzo);
} else {
  window.addEventListener("resize", () => { if (estado.notas.length) dibujarRollo(); });
}

/* ══════════════════ 3 · Tónica ══════════════════ */

function pintarTeclas() {
  const caja = $("#teclas");
  caja.innerHTML = "";
  NOMBRES.forEach((nombre, clase) => {
    const boton = document.createElement("button");
    boton.type = "button";
    boton.textContent = nombre;
    boton.className = NEGRAS.has(clase) ? "negra" : "";
    boton.dataset.clase = String(clase);
    boton.addEventListener("click", () => {
      const octava = Number($("#octava").value);
      fijarTonica((octava + 1) * 12 + clase);
    });
    caja.appendChild(boton);
  });
}

function fijarTonica(midi) {
  estado.tonica = Math.min(127, Math.max(0, Math.round(midi)));
  $("#tonica-rango").value = String(estado.tonica);
  $("#tonica-nombre").textContent = nombreNota(estado.tonica);
  $("#tonica-midi").textContent = `MIDI ${estado.tonica}`;
  $("#octava").value = String(Math.floor(estado.tonica / 12) - 1);
  const clase = ((estado.tonica % 12) + 12) % 12;
  $$("#teclas button").forEach((b) =>
    b.setAttribute("aria-pressed", String(Number(b.dataset.clase) === clase))
  );
}

$("#tonica-rango").addEventListener("input", (e) => fijarTonica(Number(e.target.value)));
$("#octava").addEventListener("input", (e) => {
  const octava = Number(e.target.value);
  if (Number.isFinite(octava)) fijarTonica((octava + 1) * 12 + (estado.tonica % 12));
});

function pintarSugerencias() {
  const caja = $("#sugerencias");
  const elegidas = notasSeleccionadas();
  caja.innerHTML = "";
  if (!elegidas.length) return;

  const alturas = elegidas.map((n) => n.pitch);
  const conteo = new Map();
  elegidas.forEach((n) => conteo.set(n.pitch, (conteo.get(n.pitch) || 0) + 1));
  const masFrecuente = [...conteo.entries()].sort((a, b) => b[1] - a[1] || a[0] - b[0])[0][0];

  const opciones = [
    { midi: Math.min(...alturas), etiqueta: "Nota más grave" },
    { midi: elegidas[0].pitch, etiqueta: "Primera nota" },
    { midi: masFrecuente, etiqueta: "Altura más repetida" },
    { midi: 60, etiqueta: "Do central" },
  ];

  const vistos = new Set();
  opciones.forEach(({ midi, etiqueta }) => {
    if (vistos.has(midi)) return;
    vistos.add(midi);
    const boton = document.createElement("button");
    boton.type = "button";
    boton.innerHTML = `${nombreNota(midi)} <small>${etiqueta} · MIDI ${midi}</small>`;
    boton.addEventListener("click", () => { fijarTonica(midi); brindis(`p_ton = ${nombreNota(midi)}`); });
    caja.appendChild(boton);
  });
}

/* ══════════════════ 4 · Análisis ══════════════════ */

$("#analizar").addEventListener("click", analizar);

async function analizar() {
  const elegidas = notasSeleccionadas();
  if (!elegidas.length) { brindis("Selecciona al menos una nota"); return; }

  habilitarPaso("p-resultado");
  irA("p-resultado");
  ocultarAviso("#aviso-resultado");
  $("#resultado-cuerpo").hidden = true;
  $("#resultado-cargando").hidden = false;
  $("#cargando-texto").textContent = elegidas.length > LIMITE_AVISO
    ? `Analizando ${elegidas.length} eventos. En un fragmento así el cálculo puede tardar; la pantalla sigue respondiendo.`
    : "Construyendo el grafo MTI…";

  const indices = estado.rango || notasVisibles().length !== estado.notas.length
    ? elegidas.map((n) => n.i)
    : [];

  try {
    const inicio = performance.now();
    const datos = await motor("analizar", {
      b64: estado.archivo.b64,
      tonica: estado.tonica,
      indices,
      nombre: estado.archivo.nombre,
    });
    const ms = Math.round(performance.now() - inicio);

    if (!datos.ok) {
      $("#resultado-cargando").hidden = true;
      mostrarAviso("#aviso-resultado", `<b>No se pudo analizar</b>${datos.error}`);
      return;
    }
    estado.resultado = datos.result;
    pintarResultado(datos.result, ms);
  } catch (error) {
    $("#resultado-cargando").hidden = true;
    if (error.message === "CANCELADO") {
      mostrarAviso(
        "#aviso-resultado",
        "<b>Cálculo cancelado</b>Vuelve al paso 2 y acota un fragmento más pequeño.",
        true
      );
    } else {
      mostrarAviso("#aviso-resultado", `<b>Error del motor</b>${error.message}`);
    }
  }
}

$("#cancelar-analisis").addEventListener("click", () => {
  motor.cancelar();
  brindis("Cálculo cancelado");
});

function pintarResultado(resultado, ms) {
  $("#resultado-cargando").hidden = true;
  $("#resultado-cuerpo").hidden = false;

  const familia = resultado.normalized_family || [];
  const sincronias = (resultado.nodes && resultado.nodes.sync) || [];
  const aristas = resultado.edges || [];

  $("#cifras").innerHTML = [
    [familia.length, "eventos"],
    [sincronias.length, "sincronías"],
    [aristas.length, "aristas"],
    [`${(ms / 1000).toFixed(ms < 1000 ? 2 : 1)} s`, "cálculo"],
  ].map(([valor, etiqueta]) => `<div class="cifra"><b>${valor}</b><span>${etiqueta}</span></div>`).join("");

  // Grafo
  const caja = $("#grafo-caja");
  const nota = $("#grafo-nota");
  if (familia.length > LIMITE_GRAFO) {
    caja.innerHTML = `<p class="nota" style="padding:24px 8px;text-align:center">
      El fragmento tiene ${familia.length} eventos y ${aristas.length} aristas.
      Dibujarlo produciría una maraña ilegible y lenta en un móvil.
      <br><br><button type="button" class="sec" id="forzar-grafo">Dibujarlo de todos modos</button></p>`;
    nota.textContent = "";
    $("#forzar-grafo").addEventListener("click", () => {
      caja.innerHTML = "";
      caja.appendChild(construirSvg(resultado));
      nota.textContent = "Eje horizontal: soporte normalizado [0,1]. Vertical: altura relativa h = p − p_ton.";
    });
  } else {
    caja.innerHTML = "";
    caja.appendChild(construirSvg(resultado));
    nota.textContent = "Eje horizontal: soporte normalizado [0,1]. Vertical: altura relativa h = p − p_ton. Los puntos de la base son las sincronías.";
  }

  // Firma canónica
  const firma = resultado.canonical_signature || {};
  $("#firma").innerHTML = `
    <div><dt>Cardinales</dt><dd>m = ${firma.m} · R = ${firma.R}</dd></div>
    <div><dt>Palabra temporal</dt><dd>${(firma.temporal_word || []).join(" · ") || "—"}</dd></div>
    <div><dt>Descriptores de evento (h, u, v)</dt><dd>${(firma.event_descriptors || []).map((d) => `[${d.join(", ")}]`).join(" ") || "—"}</dd></div>`;

  // Tabla de familia normalizada
  const filas = familia.map((d, i) => `<tr>
      <td>${i + 1}</td><td>${d.h}</td>
      <td>${d.u.exact}</td><td>${d.v.exact}</td>
      <td>${d.u.value.toFixed(4)}</td><td>${d.v.value.toFixed(4)}</td>
    </tr>`).join("");
  $("#tabla-familia").innerHTML =
    `<thead><tr><th>#</th><th>h</th><th>u exacto</th><th>v exacto</th><th>u</th><th>v</th></tr></thead><tbody>${filas}</tbody>`;

  // Procedencia
  const fuente = resultado.source || {};
  const rep = fuente.reproducibility || {};
  $("#proc").innerHTML = [
    ["Archivo", fuente.filename],
    ["Segmentación", rep.segmentation === "seleccion_manual" ? "selección manual" : "archivo completo"],
    ["Notas del archivo", rep.file_note_count],
    ["Notas analizadas", rep.selected_note_indices],
    ["Duplicados exactos retirados", fuente.duplicates_removed],
    ["p_ton", `${estado.tonica} (${nombreNota(estado.tonica)})`],
    ["División", `${fuente.division} ${fuente.division_mode === "ticks_per_quarter_note" ? "ppq" : ""}`],
    ["Extensión", `${fuente.span_ticks} ticks`],
    ["Aritmética", rep.exact_arithmetic],
    ["Núcleo", rep.app_version],
    ["SHA-256 del MIDI", (rep.input_sha256 || "").slice(0, 16) + "…"],
  ].map(([k, v]) => `<div><span>${k}</span><span>${v ?? "—"}</span></div>`).join("");

  if ((resultado.warnings || []).length) {
    mostrarAviso("#aviso-resultado", `<b>Avisos del análisis</b>${resultado.warnings.join("<br>")}`, true);
  }

  pintarCercania(familia);
}

/* ══════════════════ Proximidad al corpus ══════════════════ */

const PESOS_BASE = { omega_pc: 1, omega_lin: 1, omega_on: 1, omega_off: 1, gamma: 1 };

async function pintarCercania(familia) {
  const caja = $("#cercania");
  caja.innerHTML = `<p class="nota">Comparando con los 50 registros del corpus…</p>`;
  try {
    const datos = await motor("rankearCorpus", { familia, parametros: PESOS_BASE });
    if (!datos.ok) { caja.innerHTML = `<p class="nota">No disponible: ${datos.error}</p>`; return; }

    const filas = datos.filas;
    const primeros = filas.slice(0, 6);
    const diezSectores = new Set(filas.slice(0, 10).map((f) => f.sector));

    caja.innerHTML = `
      <div class="ranking">
        ${primeros.map((f, i) => `
          <div class="rank-fila">
            <span class="rank-num">${i + 1}</span>
            <div class="rank-cuerpo">
              <b>${f.obra}</b>
              <small>${f.compositor} · ${f.textura} · ${f.eventos} eventos</small>
              <div class="rank-barra"><i style="width:${(f.relativa.value * 100).toFixed(1)}%"></i></div>
            </div>
            <div class="rank-cifras">
              <span class="mono">${f.relativa.value.toFixed(3)}</span>
              <span class="sector">${f.sector}</span>
            </div>
          </div>`).join("")}
      </div>
      <p class="nota siempre">
        Ordenado de más parecido a menos. La cifra va de 0, idénticos, a 1, lo más distinto.
      </p>
      <p class="nota">
        Ordenado por índice relativo <span class="mono">D̄γ</span>, de 0 (idéntico) a 1.
        Los diez registros más próximos pertenecen a <b>${diezSectores.size}</b>
        sectores distintos de los quince del corpus.
      </p>
      <div class="aviso suave">
        <b>Esto es proximidad, no clasificación</b>
        El sector es una etiqueta externa que no interviene en <span class="mono">Dγ</span>.
        Con 25 obras en 15 categorías, seis de ellas con una sola obra, ninguna
        lectura clasificatoria se sostiene.
      </div>`;
  } catch (error) {
    caja.innerHTML = `<p class="nota">No se pudo comparar con el corpus: ${error.message}</p>`;
  }
}

/* ══════════════════ Panel del corpus ══════════════════ */

let informeCorpus = null;
let sectorElegido = null;

async function pintarCorpus() {
  if (!informeCorpus) {
    try {
      const respuesta = await fetch("corpus/informe.json");
      if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
      informeCorpus = await respuesta.json();
    } catch (error) {
      $("#corpus-cifras").innerHTML = `<p class="nota">No se pudo cargar el informe: ${error.message}</p>`;
      return;
    }
  }

  const r = informeCorpus.resumen;
  $("#corpus-cifras").innerHTML = [
    [r.items, "registros"],
    [r.comparisons, "comparaciones"],
    [r.advertising_types, "sectores"],
    [r.silhouette.toFixed(3), "silueta"],
  ].map(([v, e]) => `<div class="cifra"><b>${v}</b><span>${e}</span></div>`).join("");

  // Familias con su composición por sector: la lectura honesta del clustering
  const asociaciones = informeCorpus.asociaciones.rows;
  $("#corpus-familias").innerHTML = asociaciones.map((fila) => {
    const cuentas = Object.entries(fila.counts).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]);
    const [dominante, n] = cuentas[0] || ["—", 0];
    const pureza = fila.total ? n / fila.total : 0;
    return `
      <div class="familia">
        <div class="familia-cab">
          <b>${fila.family}</b>
          <span>${fila.total} registro(s)</span>
        </div>
        <div class="familia-sectores">
          ${cuentas.map(([s, c]) => `<span class="sector">${s} · ${c}</span>`).join("")}
        </div>
        <p class="nota">
          Sector dominante <b>${dominante}</b>, con una pureza del
          <b>${(pureza * 100).toFixed(1)} %</b>.
        </p>
      </div>`;
  }).join("") + `
    <div class="aviso suave">
      <b>Cómo leer esto</b>
      El clustering estructural agrupa casi todo el corpus en una sola familia,
      y su composición reproduce el reparto de sectores de partida. Con estos
      pesos y esta lectura, la estructura del motivo no separa por sector.
      Las lecturas contextuales y categóricas del capítulo del corpus extendido
      interrogan ese mismo eje por otras vías.
    </div>`;

  // Obras, filtrables por sector
  const sectores = [...new Set(informeCorpus.items.map((i) => i.sector))].sort();
  $("#corpus-sectores").innerHTML =
    `<button type="button" class="filtro" data-sector="" aria-pressed="${!sectorElegido}">Todos</button>` +
    sectores.map((s) => `<button type="button" class="filtro" data-sector="${s}" aria-pressed="${sectorElegido === s}">${s}</button>`).join("");

  $$("#corpus-sectores .filtro").forEach((boton) => {
    boton.addEventListener("click", () => {
      sectorElegido = boton.dataset.sector || null;
      pintarCorpus();
    });
  });

  // Una fila por obra, no por registro: las dos texturas son la misma obra
  const porObra = new Map();
  informeCorpus.items.forEach((i) => {
    if (sectorElegido && i.sector !== sectorElegido) return;
    if (!porObra.has(i.obra)) porObra.set(i.obra, { ...i, texturas: [] });
    porObra.get(i.obra).texturas.push(i.textura);
  });

  $("#corpus-obras").innerHTML = [...porObra.values()]
    .sort((a, b) => a.sector.localeCompare(b.sector) || a.obra.localeCompare(b.obra))
    .map((i) => `
      <div class="ficha" style="cursor:default">
        <div class="cuerpo">
          <b>${i.obra}</b>
          <small>${i.compositor} · ${i.texturas.join(" y ")} · p_ton ${nombreNota(i.tonica)}</small>
        </div>
        <span class="sector">${i.sector}</span>
      </div>`).join("") || `<div class="vacio">Sin obras en ese sector</div>`;
}

function construirSvg(resultado) {
  const familia = resultado.normalized_family || [];
  const sincronias = (resultado.nodes && resultado.nodes.sync) || [];
  const eventos = (resultado.nodes && resultado.nodes.events) || [];

  const alturas = familia.map((d) => d.h);
  const hMin = Math.min(0, ...alturas);
  const hMax = Math.max(0, ...alturas);
  const spanH = Math.max(1, hMax - hMin);

  const anchoBase = Math.max(320, Math.min(1200, 90 + familia.length * 26));
  const alto = Math.max(220, Math.min(520, 110 + spanH * 12));
  const izq = 42, der = 18, arriba = 18, abajo = 58;
  const x = (u) => izq + u * (anchoBase - izq - der);
  const y = (h) => arriba + (1 - (h - hMin) / spanH) * (alto - arriba - abajo);

  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${anchoBase} ${alto}`);
  svg.setAttribute("width", String(anchoBase));
  svg.setAttribute("height", String(alto));
  svg.setAttribute("xmlns", ns);
  svg.setAttribute("font-family", "ui-monospace, Menlo, monospace");

  const crear = (tipo, atributos, texto) => {
    const nodo = document.createElementNS(ns, tipo);
    Object.entries(atributos).forEach(([k, v]) => nodo.setAttribute(k, String(v)));
    if (texto !== undefined) nodo.textContent = texto;
    svg.appendChild(nodo);
    return nodo;
  };

  const estilo = getComputedStyle(document.body);
  const tinta = estilo.getPropertyValue("--tinta").trim() || "#17150f";
  const tinta3 = estilo.getPropertyValue("--tinta-3").trim() || "#7d7565";
  const acento = estilo.getPropertyValue("--acento").trim() || "#8a5a2b";
  const linea = estilo.getPropertyValue("--linea").trim() || "#e0d9c8";

  crear("rect", { x: 0, y: 0, width: anchoBase, height: alto, fill: "none" });

  // Referencia h = 0 (la propia tónica)
  crear("line", {
    x1: izq, y1: y(0), x2: anchoBase - der, y2: y(0),
    stroke: linea, "stroke-width": 1, "stroke-dasharray": "3 3",
  });
  crear("text", {
    x: anchoBase - der, y: y(0) - 5, fill: tinta3, "font-size": 9, "text-anchor": "end",
  }, "h = 0 · p_ton");

  // Base de sincronías
  const yBase = alto - abajo + 20;
  crear("line", { x1: izq, y1: yBase, x2: anchoBase - der, y2: yBase, stroke: tinta3, "stroke-width": 1 });
  sincronias.forEach((s) => {
    crear("circle", { cx: x(s.normalized.value), cy: yBase, r: 3, fill: tinta3 });
  });
  crear("text", { x: 6, y: yBase + 3.5, fill: tinta3, "font-size": 9 }, "θ");

  // Aristas de incidencia: del evento a su sincronía de ataque y de terminación
  eventos.forEach((evento) => {
    const u = evento.onset_normalized.value;
    const v = evento.offset_normalized.value;
    const yh = y(evento.relative_pitch);
    [[u, yh], [v, yh]].forEach(([px, py]) => {
      crear("line", {
        x1: x(px), y1: py, x2: x(px), y2: yBase,
        stroke: linea, "stroke-width": 1,
      });
    });
  });

  // Eventos como segmentos [u, v] a la altura relativa h
  eventos.forEach((evento) => {
    const u = evento.onset_normalized.value;
    const v = evento.offset_normalized.value;
    const yh = y(evento.relative_pitch);
    crear("line", {
      x1: x(u), y1: yh, x2: Math.max(x(u) + 3, x(v)), y2: yh,
      stroke: tinta, "stroke-width": 4, "stroke-linecap": "round",
    });
    crear("circle", { cx: x(u), cy: yh, r: 3.2, fill: acento });
  });

  // Escala vertical de alturas relativas
  const paso = spanH > 24 ? 12 : spanH > 12 ? 6 : spanH > 6 ? 3 : 1;
  for (let h = Math.ceil(hMin / paso) * paso; h <= hMax; h += paso) {
    if (h === 0) continue;
    crear("text", { x: 6, y: y(h) + 3.5, fill: tinta3, "font-size": 9 }, String(h));
  }
  crear("text", { x: izq, y: yBase + 16, fill: tinta3, "font-size": 9, "text-anchor": "middle" }, "0");
  crear("text", { x: anchoBase - der, y: yBase + 16, fill: tinta3, "font-size": 9, "text-anchor": "middle" }, "1");

  estado.ultimoSvg = svg;
  return svg;
}

/* ── Exportaciones ── */

$("#exp-analisis").addEventListener("click", () => {
  if (!estado.resultado) return;
  descargar(JSON.stringify(estado.resultado, null, 2), "application/json",
    `${baseNombre(estado.archivo.nombre)}.analisis.json`);
});

$("#exp-portable").addEventListener("click", async () => {
  if (!estado.resultado) return;
  try {
    const datos = await motor("portable", { resultado: estado.resultado });
    if (!datos.ok) { brindis(datos.error); return; }
    descargar(JSON.stringify(datos.document, null, 2), "application/json",
      `${baseNombre(estado.archivo.nombre)}.mti.json`);
  } catch (error) {
    brindis(error.message);
  }
});

$("#exp-svg").addEventListener("click", () => {
  if (!estado.ultimoSvg) { brindis("Dibuja antes el grafo"); return; }
  const copia = estado.ultimoSvg.cloneNode(true);
  copia.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  descargar(new XMLSerializer().serializeToString(copia), "image/svg+xml",
    `${baseNombre(estado.archivo.nombre)}.grafo.svg`);
});

/* ══════════════════ 5 · Biblioteca ══════════════════ */

const CLAVE = "mti-movil-biblioteca-v1";

function leerBiblioteca() {
  try { return JSON.parse(localStorage.getItem(CLAVE) || "[]"); }
  catch { return []; }
}

function escribirBiblioteca(lista) {
  try {
    localStorage.setItem(CLAVE, JSON.stringify(lista));
    return true;
  } catch {
    brindis("No hay espacio en el almacenamiento del navegador");
    return false;
  }
}

$("#guardar").addEventListener("click", () => {
  if (!estado.resultado) return;
  const familia = estado.resultado.normalized_family || [];
  const lista = leerBiblioteca();
  lista.unshift({
    id: `m${Date.now()}`,
    nombre: estado.archivo.nombre,
    fecha: new Date().toISOString(),
    eventos: familia.length,
    tonica: estado.tonica,
    fragmento: estado.resultado.source.reproducibility.segmentation === "seleccion_manual",
    familia,
    contexto: estado.resultado.context || null,
    firma: estado.resultado.canonical_signature || null,
  });
  if (escribirBiblioteca(lista.slice(0, 60))) {
    brindis("Guardado en la biblioteca");
    habilitarPaso("p-biblioteca");
  }
});

const elegidos = new Set();

function pintarBiblioteca() {
  const lista = leerBiblioteca();
  const caja = $("#lista-biblioteca");
  if (!lista.length) {
    caja.innerHTML = `<div class="vacio">Todavía no has guardado ningún motivo.<br>Analiza un fragmento y pulsa «Guardar en la biblioteca».</div>`;
    $("#comparar-caja").hidden = true;
    return;
  }

  caja.innerHTML = "";
  lista.forEach((item) => {
    const ficha = document.createElement("div");
    ficha.className = "ficha";
    ficha.setAttribute("aria-selected", String(elegidos.has(item.id)));
    const orden = [...elegidos].indexOf(item.id);
    ficha.innerHTML = `
      <div class="marca-sel">${orden >= 0 ? orden + 1 : ""}</div>
      <div class="cuerpo">
        <b>${item.nombre}</b>
        <small>${item.eventos} eventos · p_ton ${nombreNota(item.tonica)} · ${item.fragmento ? "fragmento" : "archivo completo"} · ${new Date(item.fecha).toLocaleDateString("es")}</small>
      </div>
      <button class="quitar" type="button" aria-label="Quitar">×</button>`;

    ficha.addEventListener("click", (e) => {
      if (e.target.closest(".quitar")) {
        escribirBiblioteca(leerBiblioteca().filter((x) => x.id !== item.id));
        elegidos.delete(item.id);
        pintarBiblioteca();
        return;
      }
      if (elegidos.has(item.id)) elegidos.delete(item.id);
      else {
        if (elegidos.size >= 2) elegidos.delete([...elegidos][0]);
        elegidos.add(item.id);
      }
      pintarBiblioteca();
    });
    caja.appendChild(ficha);
  });

  const dos = elegidos.size === 2;
  $("#comparar-caja").hidden = !dos;
  if (dos) {
    const [a, b] = [...elegidos].map((id) => lista.find((x) => x.id === id));
    $("#comparar-quienes").textContent = `${a.nombre} (${a.eventos} eventos) frente a ${b.nombre} (${b.eventos} eventos).`;
  }
  $("#resultado-comparacion").innerHTML = "";
}

$("#btn-comparar").addEventListener("click", async () => {
  const lista = leerBiblioteca();
  const [a, b] = [...elegidos].map((id) => lista.find((x) => x.id === id));
  if (!a || !b) return;

  const parametros = {
    omega_pc: Number($("#w-pc").value),
    omega_lin: Number($("#w-lin").value),
    omega_on: Number($("#w-on").value),
    omega_off: Number($("#w-off").value),
    gamma: Number($("#w-gamma").value),
  };

  const salida = $("#resultado-comparacion");
  salida.innerHTML = `<p class="nota">Calculando Dγ…</p>`;

  try {
    const datos = await motor("comparar", {
      familiaA: a.familia, familiaB: b.familia, parametros,
      contextoA: a.contexto, contextoB: b.contexto,
    });
    if (!datos.ok) { salida.innerHTML = `<div class="aviso"><b>No se pudo comparar</b>${datos.error}</div>`; return; }
    pintarComparacion(datos, salida);
  } catch (error) {
    salida.innerHTML = `<div class="aviso"><b>Error del motor</b>${error.message}</div>`;
  }
});

function pintarComparacion(datos, salida) {
  const c = datos.comparison;
  const relativo = c.relative_index || {};
  const componentes = c.components || {};
  const bloques = [];

  bloques.push(`
    <div class="dist-grande">
      <span class="etiq">Distancia Dγ</span>
      <span class="val">${c.distance.value.toFixed(4)}</span>
      <span class="exacta">${c.distance.exact}</span>
    </div>`);

  if (relativo.dissimilarity) {
    bloques.push(`
      <div class="dist-grande">
        <span class="etiq">Índice relativo D̄γ</span>
        <span class="val">${relativo.dissimilarity.value.toFixed(4)}</span>
        <span class="exacta">${relativo.dissimilarity.exact} · acotado en [0,1] · no sustituye a Dγ</span>
      </div>`);
  }

  if (c.equivalent) {
    bloques.push(`<div class="aviso suave"><b>Motivos MTI-equivalentes</b>Sus familias normalizadas coinciden: misma clase bajo el marco.</div>`);
  }

  const exacto = (valor) => (valor && valor.exact !== undefined ? valor.exact : "—");
  const numero = (valor) => (valor && valor.value !== undefined ? valor.value.toFixed(4) : "—");

  bloques.push(`<h2>Descomposición del coste</h2>
    <div class="proc">
      <div><span>Altura</span><span>${numero(componentes.height)}</span></div>
      <div><span>Ataque</span><span>${numero(componentes.attack)}</span></div>
      <div><span>Terminación</span><span>${numero(componentes.termination)}</span></div>
      <div><span>Eliminación</span><span>${numero(componentes.deletion)}</span></div>
      <div><span>Inserción</span><span>${numero(componentes.insertion)}</span></div>
    </div>`);

  bloques.push(`<h2>Asignación de coste mínimo</h2>
    <div class="proc">
      <div><span>Emparejamientos</span><span>${(c.matches || []).length}</span></div>
      <div><span>Eliminaciones</span><span>${(c.deletions || []).length}</span></div>
      <div><span>Inserciones</span><span>${(c.insertions || []).length}</span></div>
      <div><span>Cardinalidad</span><span>${c.cardinality_mode || "—"}</span></div>
      <div><span>Estatus métrico</span><span>${c.metric_status}</span></div>
      <div><span>¿Es métrica?</span><span>${c.distance_is_metric ? "sí" : "no"}</span></div>
      <div><span>Coste de la correspondencia vacía</span><span>${exacto(relativo.empty_correspondence_cost)}</span></div>
    </div>`);

  bloques.push(pintarContextual(datos));
  salida.innerHTML = bloques.join("");
}

/* La lectura contextual §3.6 solo existe si el motivo trae anotaciones. Un MIDI
   desnudo no las transporta, y decirlo es más honesto que enseñar guiones. */
function pintarContextual(datos) {
  if (datos.contextual_error) {
    return `<div class="aviso suave"><b>Sin lectura contextual</b>${datos.contextual_error}</div>`;
  }
  const ctxt = datos.contextual;
  if (!ctxt) return "";

  const filas = [];
  const anotar = (etiqueta, nodo) => {
    if (!nodo) return;
    const disponible = nodo.status !== "missing" && nodo.value !== null && nodo.value !== undefined;
    filas.push([etiqueta, disponible, disponible ? Number(nodo.value.value ?? nodo.value).toFixed(4) : "sin datos"]);
  };

  ["in", "out"].forEach((sentido) => {
    const nombre = sentido === "in" ? "interno" : "externo";
    const mel = ctxt.melodic && ctxt.melodic[sentido];
    if (mel) filas.push([`Melódico ${nombre}`, mel.status !== "missing", mel.status !== "missing" ? "calculado" : "sin datos"]);
    const arm = ctxt.harmonic && ctxt.harmonic[sentido];
    if (arm) {
      anotar(`Armónico ${nombre} · fundamental`, arm.root);
      anotar(`Armónico ${nombre} · inversión`, arm.inversion);
      anotar(`Armónico ${nombre} · movimiento del bajo`, arm.bass_motion);
      anotar(`Armónico ${nombre} · constitución interválica`, arm.interval_constitution);
    }
  });
  if (ctxt.rhythmic_metric) {
    anotar("Rítmico-métrico · fase", ctxt.rhythmic_metric.phase);
    anotar("Rítmico-métrico · inicio", ctxt.rhythmic_metric.start);
  }

  const conDatos = filas.filter(([, disponible]) => disponible).length;
  if (!conDatos) {
    return `<h2>Lectura contextual §3.6</h2>
      <div class="aviso suave">
        <b>No hay contexto que comparar</b>
        Un MIDI transporta alturas y tiempos, no las anotaciones melódicas,
        armónicas y rítmico-métricas que pide el §3.6. Estos bloques se activan
        con documentos <span class="mono">.mti.json</span> enriquecidos, como los
        del corpus JKU-PDD.
      </div>`;
  }

  return `<h2>Lectura contextual §3.6</h2>
    <p class="nota">Bloques separados: no se agregan entre sí ni con Dγ.</p>
    <div class="proc">
      ${filas.map(([etiqueta, , valor]) => `<div><span>${etiqueta}</span><span>${valor}</span></div>`).join("")}
    </div>`;
}

/* ══════════════════ Cuadrícula comparativa ══════════════════ */

const cuadricula = { datos: null, lectura: 0, sector: null, par: null };

// Rampa de un solo tono: claro = obras idénticas, oscuro = lo más distinto.
// Un solo tono evita sugerir categorías donde solo hay un continuo.
function colorDistancia(v, apagado) {
  if (v === null || v === undefined) return "rgba(0,0,0,0)";
  const k = Math.max(0, Math.min(1, v));
  const claro = [247, 244, 236], oscuro = [90, 55, 22];
  const c = claro.map((x, i) => Math.round(x + (oscuro[i] - x) * k));
  return `rgba(${c[0]},${c[1]},${c[2]},${apagado ? 0.12 : 1})`;
}

function paresVisibles() {
  // Un par cuenta si las dos obras comparten el sector aislado.
  if (!cuadricula.sector) return null;
  const sec = cuadricula.datos.sectores;
  return sec.map((lista) => lista.includes(cuadricula.sector));
}

function dibujarMatriz(lienzo, matriz, ladoCss, conRejilla) {
  const n = matriz.length;
  const dpr = window.devicePixelRatio || 1;
  lienzo.width = Math.round(ladoCss * dpr);
  lienzo.height = Math.round(ladoCss * dpr);
  lienzo.style.height = `${ladoCss}px`;
  const ctx = lienzo.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, ladoCss, ladoCss);

  const dentro = paresVisibles();
  const celda = ladoCss / n;
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const apagado = dentro ? !(dentro[i] && dentro[j]) : false;
      ctx.fillStyle = i === j
        ? getComputedStyle(document.body).getPropertyValue("--linea").trim()
        : colorDistancia(matriz[i][j], apagado);
      ctx.fillRect(j * celda, i * celda, Math.ceil(celda), Math.ceil(celda));
    }
  }

  if (conRejilla && celda > 6) {
    ctx.strokeStyle = getComputedStyle(document.body).getPropertyValue("--fondo").trim();
    ctx.lineWidth = 0.5;
    for (let k = 1; k < n; k++) {
      ctx.beginPath(); ctx.moveTo(k * celda, 0); ctx.lineTo(k * celda, ladoCss); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, k * celda); ctx.lineTo(ladoCss, k * celda); ctx.stroke();
    }
  }

  // La casilla elegida, marcada en las dos posiciones simétricas
  if (cuadricula.par && conRejilla) {
    const [a, b] = cuadricula.par;
    ctx.strokeStyle = getComputedStyle(document.body).getPropertyValue("--tinta").trim();
    ctx.lineWidth = 2;
    [[a, b], [b, a]].forEach(([i, j]) => {
      ctx.strokeRect(j * celda + 1, i * celda + 1, celda - 2, celda - 2);
    });
  }
}

function redibujarCuadricula() {
  const d = cuadricula.datos;
  if (!d) return;
  $$("#cl-miniaturas canvas").forEach((lienzo) => {
    const lado = lienzo.parentElement.clientWidth - 12;
    if (lado > 0) dibujarMatriz(lienzo, d.lecturas[Number(lienzo.dataset.mini)].matriz, lado, false);
  });
  const grande = $("#cl-lienzo");
  const lado = grande.parentElement.clientWidth - 20;
  if (lado > 0) dibujarMatriz(grande, d.lecturas[cuadricula.lectura].matriz, lado, true);
}

async function pintarCuadricula() {
  if (!cuadricula.datos) {
    try {
      const respuesta = await fetch("corpus/nueve-lecturas.json");
      if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
      cuadricula.datos = await respuesta.json();
    } catch (error) {
      $("#cl-pie").innerHTML = `No se pudo cargar la cuadrícula: ${error.message}`;
      return;
    }
  }
  const d = cuadricula.datos;

  // Miniaturas: las nueve lecturas a la vez, para comparar patrones de un vistazo
  if (!$("#cl-miniaturas").children.length) {
    $("#cl-miniaturas").innerHTML = d.lecturas.map((l, i) =>
      `<button type="button" class="mini" data-i="${i}" aria-pressed="${i === cuadricula.lectura}">
         <canvas data-mini="${i}"></canvas><span>${l.nombre}</span>
       </button>`).join("");
    $$("#cl-miniaturas .mini").forEach((boton) => {
      boton.addEventListener("click", () => {
        cuadricula.lectura = Number(boton.dataset.i);
        pintarCuadricula();
      });
    });
  }
  $$("#cl-miniaturas .mini").forEach((b) =>
    b.setAttribute("aria-pressed", String(Number(b.dataset.i) === cuadricula.lectura)));

  requestAnimationFrame(redibujarCuadricula);

  const l = d.lecturas[cuadricula.lectura];
  $("#cl-degradado").style.background =
    `linear-gradient(90deg, ${colorDistancia(0)}, ${colorDistancia(0.5)}, ${colorDistancia(1)})`;
  $("#cl-pie").innerHTML =
    `<b>${l.nombre}</b> — ${l.descripcion}. Media de la lectura: ${l["global"].toFixed(3)}.
     Cada casilla es un par de obras; la diagonal es cada obra consigo misma.`;

  // Sectores
  if (!$("#cl-sectores").children.length) {
    const entradas = Object.entries(d.catalogo);
    $("#cl-sectores").innerHTML =
      `<button type="button" class="filtro" data-sec="" aria-pressed="true">todo el corpus</button>` +
      entradas.map(([s, n]) => `<button type="button" class="filtro" data-sec="${s}" aria-pressed="false">${s} · ${n}</button>`).join("");
    $$("#cl-sectores .filtro").forEach((boton) => {
      boton.addEventListener("click", () => {
        cuadricula.sector = boton.dataset.sec || null;
        $$("#cl-sectores .filtro").forEach((b) =>
          b.setAttribute("aria-pressed", String((b.dataset.sec || null) === cuadricula.sector)));
        pintarCuadricula();
      });
    });
  }

  pintarPar();
}

if ("ResizeObserver" in window) {
  let anchoPrevio = 0;
  new ResizeObserver(() => {
    const ancho = $("#cl-lienzo").clientWidth;
    if (ancho && ancho !== anchoPrevio && cuadricula.datos) {
      anchoPrevio = ancho;
      redibujarCuadricula();
    }
  }).observe($("#cl-lienzo"));
}

$("#cl-lienzo").addEventListener("click", (e) => {
  const d = cuadricula.datos;
  if (!d) return;
  const caja = e.currentTarget.getBoundingClientRect();
  const n = d.obras.length;
  const j = Math.floor(((e.clientX - caja.left) / caja.width) * n);
  const i = Math.floor(((e.clientY - caja.top) / caja.height) * n);
  if (i < 0 || j < 0 || i >= n || j >= n || i === j) return;
  cuadricula.par = [i, j];
  pintarCuadricula();
});

function pintarPar() {
  const d = cuadricula.datos;
  const caja = $("#cl-detalle");
  if (!cuadricula.par) return;
  const [a, b] = cuadricula.par;

  // El interés del panel: el mismo par visto por las nueve lecturas a la vez
  const filas = d.lecturas.map((l) => ({
    nombre: l.nombre,
    valor: l.matriz[a][b],
    puesto: l.puestos ? l.puestos[a][b] : null,
  }));
  const masCerca = filas.reduce((x, y) => (y.valor < x.valor ? y : x));
  const masLejos = filas.reduce((x, y) => (y.valor > x.valor ? y : x));

  const compartidos = d.sectores[a].filter((s) => d.sectores[b].includes(s));

  caja.innerHTML = `
    <div class="par-cab">
      <b>${d.obras[a]} · ${d.obras[b]}</b>
      <small>${compartidos.length
        ? `Comparten ${compartidos.length} sector(es): ${compartidos.join(", ")}`
        : "No comparten ningún sector publicitario"}</small>
    </div>
    <div style="margin-top:12px">
      ${filas.map((f) => `
        <div class="par-fila">
          <span class="par-nombre">${f.nombre}</span>
          <span class="par-barra"><i style="width:${(f.valor * 100).toFixed(1)}%"></i></span>
          <span class="par-val">${f.valor.toFixed(3)}</span>
          <span class="par-puesto">${f.puesto !== null ? `${f.puesto + 1}/300` : ""}</span>
        </div>`).join("")}
    </div>
    <p class="nota">
      Este par es lo más parecido para <b>${masCerca.nombre}</b> (${masCerca.valor.toFixed(3)})
      y lo más distinto para <b>${masLejos.nombre}</b> (${masLejos.valor.toFixed(3)}).
      El número de la derecha es el puesto del par entre los trescientos de esa
      lectura: la barra sitúa el valor dentro de su propia matriz, así que una
      barra corta significa «próximo para esta lectura», no «próximo en absoluto».
    </p>`;
}

/* ══════════════════ Topología operacional ══════════════════ */

// Los dos estados del capítulo 5 salen de la biblioteca o del par canónico.
const PAR_CANONICO = {
  X: { events: [[0, "0", "1/4"], [2, "1/4", "1/2"], [4, "1/2", "1"]] },
  Y: { events: [[0, "0", "1/4"], [3, "1/4", "1/2"], [5, "1/2", "1"]] },
};

const operacional = { origen: "canonico", destino: "canonico", X: null, Y: null, hayGrafo: false };

async function motivoDeFuente(id, cual) {
  if (id === "canonico") return PAR_CANONICO[cual];
  const guardado = leerBiblioteca().find((m) => m.id === id);
  if (!guardado) return null;
  const datos = await motor("jerarquiaDesdeFamilia", { familia: guardado.familia });
  return datos.ok ? datos.motif : null;
}

function parametrosOperacionales() {
  return {
    omega_pc: 1, omega_lin: 1, omega_on: 1, omega_off: 1,
    gamma: Number($("#op-gamma").value) || 5,
  };
}

async function pintarOperacional() {
  const guardados = leerBiblioteca();
  const opciones = [{ id: "canonico", nombre: "Par canónico" }]
    .concat(guardados.map((m) => ({ id: m.id, nombre: `${m.nombre} · ${m.eventos} ev.` })));

  const pintarFila = (selector, clave) => {
    $(selector).innerHTML = opciones.map((o) =>
      `<button type="button" class="filtro" data-id="${o.id}" aria-pressed="${o.id === operacional[clave]}">${o.nombre}</button>`
    ).join("");
    $$(`${selector} .filtro`).forEach((boton) => {
      boton.addEventListener("click", async () => {
        operacional[clave] = boton.dataset.id;
        await pintarOperacional();
      });
    });
  };
  pintarFila("#op-origen", "origen");
  pintarFila("#op-destino", "destino");

  operacional.X = await motivoDeFuente(operacional.origen, "X");
  operacional.Y = await motivoDeFuente(operacional.destino, "Y");

  const iguales = JSON.stringify(operacional.X) === JSON.stringify(operacional.Y);
  $("#op-estados").innerHTML = !operacional.X || !operacional.Y
    ? "<b>Faltan estados.</b> Elige un origen y un destino."
    : `X con <b>${operacional.X.events.length}</b> evento(s) · Y con <b>${operacional.Y.events.length}</b>` +
      (iguales ? " · <i>son idénticos: G_R no puede materializarse</i>" : "");

  $("#op-buscar").disabled = !operacional.X || !operacional.Y || iguales;
  $("#op-topologia").disabled = !operacional.hayGrafo;
  $("#op-exportar").disabled = !operacional.hayGrafo;
}

$("#op-trayectoria").addEventListener("click", async () => {
  const caja = $("#op-alcance-res");
  caja.innerHTML = `<p class="nota">Evaluando…</p>`;
  try {
    const d = await motor("opTrayectoria", {
      origen: operacional.X, destino: operacional.Y, acciones: [],
      parametros: parametrosOperacionales(),
    });
    if (!d.ok) { caja.innerHTML = `<div class="aviso"><b>Error</b>${d.error}</div>`; return; }
    const c = d.comparacion || {};
    caja.innerHTML = `
      <div class="proc">
        <div><span>Coste C_op(π)</span><span>${d.coste.exact}</span></div>
        <div><span>Longitud</span><span>${d.pasos}</span></div>
        <div><span>Alcanza Y</span><span>${chapa(d.alcanza ? "SÍ" : "NO")}</span></div>
        ${c.D_gamma ? `<div><span>Dγ(X,Y)</span><span>${c.D_gamma.exact}</span></div>` : ""}
        ${c.D_gamma_le_trajectory !== undefined && c.D_gamma_le_trajectory !== null
          ? `<div><span>§5.9.1 · Dγ ≤ C_op(π)</span><span>${chapa(c.D_gamma_le_trajectory ? "PASS" : "FAIL")}</span></div>` : ""}
      </div>
      <p class="nota">Secuencia: ${(d.secuencia || []).join(" → ") || "ε (trayectoria vacía)"}</p>`;
  } catch (error) {
    caja.innerHTML = `<div class="aviso"><b>Error del motor</b>${error.message}</div>`;
  }
});

$("#op-alcance").addEventListener("click", async () => {
  const caja = $("#op-alcance-res");
  caja.innerHTML = `<p class="nota">Construyendo el testigo…</p>`;
  try {
    const d = await motor("opAlcance", {
      origen: operacional.X, destino: operacional.Y, parametros: parametrosOperacionales(),
    });
    if (!d.ok) { caja.innerHTML = `<div class="aviso"><b>Error</b>${d.error}</div>`; return; }
    caja.innerHTML = `
      <div class="proc">
        <div><span>Alcanza Y</span><span>${chapa(d.alcanza ? "TESTIGO_OK" : "SIN_TESTIGO")}</span></div>
        <div><span>Coste del testigo</span><span>${d.coste.exact}</span></div>
        <div><span>Dγ estática</span><span>${d.distancia_estatica ? d.distancia_estatica.exact : "—"}</span></div>
        <div><span>Pasos</span><span>${d.pasos} / ${d.cota}</span></div>
        <div><span>Dentro de la cota</span><span>${chapa(d.dentro_de_cota ? "SÍ" : "NO")}</span></div>
      </div>
      <p class="nota">${d.declaracion || ""}</p>
      ${d.muestra_pasos.length ? `<details class="atajos"><summary>Primeros pasos del testigo</summary>
        <div class="tabla-caja"><table><tbody>${d.muestra_pasos.map((p, i) =>
          `<tr><td>${i + 1}</td><td style="white-space:normal" class="mono">${p.accion || "—"}</td><td>${p.coste ? p.coste.exact : "—"}</td><td>${p.renormaliza ? "renorm." : ""}</td></tr>`).join("")}
        </tbody></table></div>
        ${d.pasos_omitidos ? `<p class="nota">y ${d.pasos_omitidos} paso(s) más.</p>` : ""}</details>` : ""}`;
  } catch (error) {
    caja.innerHTML = `<div class="aviso"><b>Error del motor</b>${error.message}</div>`;
  }
});

$("#op-buscar").addEventListener("click", async () => {
  const caja = $("#op-buscar-res");
  caja.innerHTML = `<p class="nota">Materializando G_R… puede tardar unos segundos.</p>`;
  $("#op-buscar").disabled = true;
  try {
    const d = await motor("opBusqueda", {
      origen: operacional.X, destino: operacional.Y,
      parametros: parametrosOperacionales(),
      envolvente: {
        max_steps: Number($("#op-pasos").value) || 4,
        max_nodes: Number($("#op-nodos").value) || 400,
        max_paths: Number($("#op-caminos").value) || 64,
      },
    });
    if (!d.ok) { caja.innerHTML = `<div class="aviso"><b>Error</b>${d.error}</div>`; return; }
    operacional.hayGrafo = true;
    $("#op-topologia").disabled = false;
    caja.innerHTML = `
      <div class="cifras">
        <div class="cifra"><b>${d.nodos}</b><span>nodos</span></div>
        <div class="cifra"><b>${d.aristas}</b><span>aristas</span></div>
        <div class="cifra"><b>${((d.ms || 0) / 1000).toFixed(1)} s</b><span>búsqueda</span></div>
      </div>
      <div class="estado-linea">${chapa(d.estado)}${d.truncado_por ? ` truncado por ${d.truncado_por}` : ""}</div>
      <div class="proc" style="margin-top:10px">
        <div><span>Mejor coste</span><span>${d.mejor_coste ? d.mejor_coste.exact : "—"}</span></div>
        <div><span>Exacto en la restricción</span><span>${chapa(String(d.exacto_en_restriccion))}</span></div>
        <div><span>Caminos óptimos</span><span>${d.procesos.caminos_optimos}</span></div>
        <div><span>Diamantes conmutativos</span><span>${d.procesos.diamantes}</span></div>
        <div><span>Ramificación / reconvergencia</span><span>${d.procesos.ramificacion} / ${d.procesos.reconvergencia}</span></div>
      </div>
      <p class="nota">${d.declaracion || ""}</p>`;
  } catch (error) {
    caja.innerHTML = `<div class="aviso"><b>Error del motor</b>${error.message}</div>`;
  } finally {
    $("#op-buscar").disabled = false;
  }
});

$("#op-topologia").addEventListener("click", async () => {
  const caja = $("#op-topologia-res");
  caja.innerHTML = `<p class="nota">Comparando topologías…</p>`;
  try {
    const d = await motor("opTopologia", { parametros: parametrosOperacionales() });
    if (!d.ok) { caja.innerHTML = `<div class="aviso"><b>Error</b>${d.error}</div>`; return; }
    const r = d.resumen || {};
    const ph = r.persistent_homology || {};
    $("#op-exportar").disabled = false;
    caja.innerHTML = `
      <div class="estado-linea">${chapa(d.estado)}</div>
      <div class="proc" style="margin-top:10px">
        <div><span>Nodos / aristas de G_R</span><span>${r.graph_node_count} / ${r.graph_edge_count}</span></div>
        <div><span>|C| · |C_R*|</span><span>${r.C_cardinality} · ${r.C_R_star_cardinality}</span></div>
        <div><span>Pares operacionales finitos</span><span>${chapa(String(r.all_operational_pairs_finite))}</span></div>
        <div><span>D_op es métrica</span><span>${chapa(String(r.metric_D_op))}</span></div>
        <div><span>La operacional distingue</span><span>${chapa(String(r.operational_topology_distinguishes))}</span></div>
        <div><span>H0 coincide</span><span>${chapa(String(ph.H0_agrees))}</span></div>
        <div><span>H1 coincide</span><span>${chapa(String(ph.H1_agrees))}</span></div>
        <div><span>Registros de trazabilidad</span><span>${r.traceability_record_count}</span></div>
      </div>
      <p class="nota">
        Que las firmas de homología persistente no coincidan no invalida nada:
        significa que la lectura operacional y la estructural ven cosas distintas
        sobre el mismo subgrafo finito, que es justamente lo que el capítulo
        pregunta.
      </p>`;
  } catch (error) {
    caja.innerHTML = `<div class="aviso"><b>Error del motor</b>${error.message}</div>`;
  }
});

$("#op-exportar").addEventListener("click", async () => {
  try {
    const d = await motor("opInforme", {});
    if (!d.ok) { brindis(d.error); return; }
    descargar(JSON.stringify(d.report, null, 2), "application/json",
      `cap5-topologia-${new Date().toISOString().slice(0, 10)}.json`);
  } catch (error) {
    brindis(error.message);
  }
});

/* ══════════════════ Jerarquía constitutiva ══════════════════ */

// El motor devuelve estados en mayúsculas; se colorean por familia de resultado
// en vez de enumerarlos, porque la lista crece con el capítulo.
function chapa(estado) {
  const texto = String(estado ?? "—");
  let clase = "neutra";
  if (/PASS|VALID|CONSTITUTED|EXTRACTED|SELECTED|VERIFIED/.test(texto)) clase = "ok";
  else if (/FAIL|MISMATCH|ERROR|INSUFFICIENT|OUT_OF_DOMAIN/.test(texto)) clase = "mal";
  else if (/NOT_TESTABLE|NOT_SPECIFIED|not_asserted|SKIPPED|DISABLED/.test(texto)) clase = "tibia";
  return `<span class="chapa ${clase}">${texto}</span>`;
}

const jerarquia = { fuente: "ejemplo", configuracion: null, motivo: null, etiqueta: "" };

const CONFIG_EJEMPLO_JER = {
  level: 0,
  occurrences: [
    { id: "e1", state: { pitch: 0, onset: "0", duration: "1/4", articulation: "alpha0" } },
    { id: "e2", state: { pitch: 2, onset: "1/4", duration: "1/8", articulation: "alpha0" } },
    { id: "e3", state: { pitch: 4, onset: "1/2", duration: "1/4", articulation: "alpha0" } },
    { id: "e4", state: { pitch: 7, onset: "3/4", duration: "1/4", articulation: "alpha0" } },
  ],
  relations: { type: "B(M)" },
  auxiliary_data: { p_ton: 0 },
};
const MOTIVO_EJEMPLO_JER = { events: [[0, "0", "1/4"], [2, "1/4", "3/8"], [4, "1/2", "3/4"], [7, "3/4", "1"]] };

async function pintarJerarquia() {
  const guardados = leerBiblioteca();
  const fuentes = [{ id: "ejemplo", nombre: "Ejemplo del capítulo" }]
    .concat(guardados.map((m) => ({ id: m.id, nombre: `${m.nombre} · ${m.eventos} ev.` })));

  $("#jer-fuentes").innerHTML = fuentes.map((f) =>
    `<button type="button" class="filtro" data-fuente="${f.id}" aria-pressed="${f.id === jerarquia.fuente}">${f.nombre}</button>`
  ).join("");
  $$("#jer-fuentes .filtro").forEach((boton) => {
    boton.addEventListener("click", () => { jerarquia.fuente = boton.dataset.fuente; pintarJerarquia(); });
  });

  if (jerarquia.fuente === "ejemplo") {
    jerarquia.configuracion = CONFIG_EJEMPLO_JER;
    jerarquia.motivo = MOTIVO_EJEMPLO_JER;
    jerarquia.etiqueta = "Ejemplo del capítulo 6";
  } else {
    const motivo = guardados.find((m) => m.id === jerarquia.fuente);
    if (!motivo) { jerarquia.fuente = "ejemplo"; return pintarJerarquia(); }
    $("#jer-material").textContent = "Construyendo la configuración basal…";
    try {
      const datos = await motor("jerarquiaDesdeFamilia", { familia: motivo.familia });
      if (!datos.ok) { $("#jer-material").innerHTML = `<b>No se pudo construir:</b> ${datos.error}`; return; }
      jerarquia.configuracion = datos.configuration;
      jerarquia.motivo = datos.motif;
      jerarquia.etiqueta = motivo.nombre;
    } catch (error) {
      $("#jer-material").innerHTML = `<b>Error:</b> ${error.message}`;
      return;
    }
  }

  const ocurrencias = jerarquia.configuracion.occurrences;
  $("#jer-material").innerHTML =
    `<b>${jerarquia.etiqueta}</b> · ${ocurrencias.length} ocurrencia(s) basales · ` +
    `p_ton ${jerarquia.configuracion.auxiliary_data.p_ton} · relación ${jerarquia.configuracion.relations.type}`;

  $("#jer-descriptor").innerHTML = jerarquia.motivo.events.map((e, i) =>
    `<option value="${i}">${i + 1} · h=${e[0]} · u=${e[1]} · v=${e[2]}</option>`).join("");

  ["#jer-constituir-res", "#jer-preimagen-res", "#jer-elevacion-res"].forEach((s) => { $(s).innerHTML = ""; });
}

$("#jer-fixtures").addEventListener("click", async () => {
  const caja = $("#jer-fixtures-res");
  caja.innerHTML = `<p class="nota">Ejecutando…</p>`;
  try {
    const datos = await motor("jerarquiaFixtures", {});
    if (!datos.ok) { caja.innerHTML = `<div class="aviso"><b>Error</b>${datos.error}</div>`; return; }
    const r = datos.report;
    caja.innerHTML = `
      <div class="estado-linea">Resultado global ${chapa(r.status)}</div>
      <div class="tabla-caja" style="margin-top:10px"><table>
        <thead><tr><th>Comprobación</th><th>Estado</th></tr></thead>
        <tbody>${r.checks.map((c) =>
          `<tr><td style="white-space:normal">${c.name}</td><td>${chapa(c.status)}</td></tr>`).join("")}</tbody>
      </table></div>
      <p class="nota">${r.checks.length} comprobaciones. Las marcadas
        <span class="mono">NOT_TESTABLE</span> o <span class="mono">NOT_SPECIFIED</span>
        no son fallos: señalan lo que el marco declara fuera de su alcance.</p>`;
  } catch (error) {
    caja.innerHTML = `<div class="aviso"><b>Error del motor</b>${error.message}</div>`;
  }
});

$("#jer-constituir").addEventListener("click", async () => {
  const caja = $("#jer-constituir-res");
  caja.innerHTML = `<p class="nota">Constituyendo…</p>`;
  try {
    const datos = await motor("jerarquiaConstituir", { configuracion: jerarquia.configuracion });
    if (!datos.ok) { caja.innerHTML = `<div class="aviso"><b>Error</b>${datos.error}</div>`; return; }
    const r = datos.result;
    if (r.status === "OUT_OF_DOMAIN") {
      caja.innerHTML = `<div class="aviso suave"><b>Fuera del dominio</b>${r.reason || ""}</div>`;
      return;
    }
    const rec = r.record;
    caja.innerHTML = `
      <div class="estado-linea">${chapa(r.status)} <span class="mono">${rec.constitution_map_id}</span></div>
      <div class="proc" style="margin-top:10px">
        <div><span>Testigo</span><span>${rec.record_id}</span></div>
        <div><span>Nivel</span><span>${rec.source_level} → ${rec.target_level}</span></div>
        <div><span>Eventos del estado</span><span>${(rec.result_state.events || []).length}</span></div>
      </div>
      <details class="atajos"><summary>Estado motívico resultante</summary>
        <div class="tabla-caja" style="padding:12px"><pre id="jer-pre-1">${JSON.stringify(rec.result_state, null, 1)}</pre></div>
      </details>`;
    $("#jer-pre-1").className = "";
    $("#jer-pre-1").style.cssText = "margin:0;font-family:var(--mono);font-size:10.5px;white-space:pre-wrap;word-break:break-word";
  } catch (error) {
    caja.innerHTML = `<div class="aviso"><b>Error del motor</b>${error.message}</div>`;
  }
});

$("#jer-preimagen").addEventListener("click", async () => {
  const caja = $("#jer-preimagen-res");
  caja.innerHTML = `<p class="nota">Construyendo…</p>`;
  try {
    const datos = await motor("jerarquiaPreimagen", { motivo: jerarquia.motivo });
    if (!datos.ok) { caja.innerHTML = `<div class="aviso"><b>Error</b>${datos.error}</div>`; return; }
    const rec = datos.record;
    caja.innerHTML = `
      <div class="estado-linea">${chapa(rec.verification_snapshot.status)} <span class="mono">${rec.record_id}</span></div>
      <p class="nota">${(rec.provenance_metadata || {}).note || ""}</p>
      <div class="proc" style="margin-top:6px">
        <div><span>Ocurrencias de Ξ_X</span><span>${(rec.configuration.occurrences || []).length}</span></div>
        <div><span>Nivel</span><span>${rec.source_level} → ${rec.target_level}</span></div>
      </div>`;
  } catch (error) {
    caja.innerHTML = `<div class="aviso"><b>Error del motor</b>${error.message}</div>`;
  }
});

$("#jer-elevacion").addEventListener("click", async () => {
  const caja = $("#jer-elevacion-res");
  const operador = $("#jer-operador").value;
  const indice = Number($("#jer-descriptor").value) || 0;
  const descriptor = jerarquia.motivo.events[indice];
  const bruto = $("#jer-delta").value.trim();
  // El motor espera entero para altura y fracción textual para los tiempos.
  let delta = null;
  if (operador === "pitch") delta = parseInt(bruto, 10);
  else if (operador === "onset" || operador === "offset") delta = bruto;

  caja.innerHTML = `<p class="nota">Verificando…</p>`;
  try {
    const datos = await motor("jerarquiaElevacion", {
      configuracion: jerarquia.configuracion, operador, descriptor, delta,
    });
    if (!datos.ok) { caja.innerHTML = `<div class="aviso"><b>Error</b>${datos.error}</div>`; return; }
    const c = datos.result.compatibility;
    caja.innerHTML = `
      <div class="estado-linea">Conmutatividad ${chapa(c.overall)}</div>
      <div class="proc" style="margin-top:10px">
        <div><span>Dominios</span><span>${chapa(c.domain_equality_status)}</span></div>
        <div><span>Valores</span><span>${chapa(c.value_equality_status)}</span></div>
        <div><span>Dominio no vacío</span><span>${chapa(c.nonempty_domain_status)}</span></div>
        <div><span>Rama motivo</span><span>${c.motif_branch_state_id || "—"}</span></div>
        <div><span>Rama basal</span><span>${c.lifted_branch_state_id || "—"}</span></div>
      </div>`;
  } catch (error) {
    caja.innerHTML = `<div class="aviso"><b>Error del motor</b>${error.message}</div>`;
  }
});

/* ══════════════════ Corpus extendido ══════════════════ */

// Los identificadores del motor son los del §3.6; aquí se nombran en claro.
const NOMBRE_LECTURA = {
  structural: "Estructural",
  rhythm: "Rítmica",
  melodic_in: "Melódica interna",
  melodic_out: "Melódica externa",
  harmonic_root: "Armónica · fundamental",
  harmonic_inversion: "Armónica · inversión",
  harmonic_bass_motion: "Armónica · movimiento del bajo",
  harmonic_interval_constitution: "Armónica · constitución interválica",
  rhythmic_phase: "Rítmico-métrica · fase",
  rhythmic_start: "Rítmico-métrica · inicio",
};

let informeExtendido = null;
let texturaElegida = null;

async function pintarExtendido() {
  if (!informeExtendido) {
    try {
      const respuesta = await fetch("corpus/extendido.json");
      if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
      informeExtendido = await respuesta.json();
    } catch (error) {
      $("#ext-lecturas").innerHTML = `<div class="aviso"><b>No se pudo cargar</b>${error.message}</div>`;
      return;
    }
  }

  const texturas = informeExtendido.texturas;
  if (!texturaElegida) texturaElegida = texturas[0].textura;

  $("#ext-texturas").innerHTML = texturas.map((t) =>
    `<button type="button" class="filtro" data-textura="${t.textura}" aria-pressed="${t.textura === texturaElegida}">
       ${t.textura} · ${t.lecturas.length} lecturas</button>`).join("");
  $$("#ext-texturas .filtro").forEach((boton) => {
    boton.addEventListener("click", () => { texturaElegida = boton.dataset.textura; pintarExtendido(); });
  });

  const bloque = texturas.find((t) => t.textura === texturaElegida);
  const obras = bloque.obras;
  const sectores = bloque.sectores;

  $("#ext-lecturas").innerHTML = bloque.lecturas.map((l) => {
    const sil = l.silueta;
    const tamanos = l.familias.map((f) => f.miembros.length);
    // Una sola familia con todo dentro significa que esa lectura no separa nada.
    const plana = l.familias.length < 2;
    return `
      <details class="lectura">
        <summary>
          <div class="lectura-cab">
            <b>${NOMBRE_LECTURA[l.id] || l.id}</b>
            <span class="sil">${sil === null || sil === undefined ? "—" : sil.toFixed(3)}</span>
          </div>
          <div class="lectura-meta">
            <span class="pastilla${plana ? " plana" : ""}">${l.familias.length} familia(s)${tamanos.length ? " · " + tamanos.join("+") : ""}</span>
            <span class="pastilla">pureza ${l.pureza === null ? "—" : (l.pureza * 100).toFixed(1) + " %"}</span>
            <span class="pastilla">H0 ${l.H0} · H1 ${l.H1}</span>
          </div>
          <div class="barra-sil"><i style="width:${Math.max(0, Math.min(1, sil || 0)) * 100}%"></i></div>
        </summary>
        <div class="lectura-cuerpo">
          ${plana
            ? `<p class="nota">Esta lectura no separa el corpus: los ${tamanos[0] || 0} registros
                 caen en una sola familia y la silueta es cero. El componente no
                 discrimina en este material.</p>`
            : ""}
          <div class="familia-lista">
            ${l.familias.map((f) => `
              <div class="familia-bloque">
                <b>${f.id || "familia"} · ${f.miembros.length} registro(s)</b>
                <p>${f.miembros.map((m) => `${obras[m] || m}<span class="nota"> (${sectores[m] || "sin sector"})</span>`).join(" · ")}</p>
              </div>`).join("")}
          </div>
          ${l.medoide && l.medoide.obra
            ? `<p class="nota"><b>Forma central</b> (medoide): ${l.medoide.obra}${l.medoide.compositor ? ` — ${l.medoide.compositor}` : ""}.</p>`
            : ""}
        </div>
      </details>`;
  }).join("") + `
    <div class="aviso suave">
      <b>Homología persistente vacía</b>
      Las diecisiete lecturas devuelven H0 y H1 sin rasgos con los parámetros de
      selección por defecto. Es un resultado, no un fallo: conviene poder
      explicarlo.
    </div>
    <p class="nota">
      La pureza mide cuánto coincide cada familia con la etiqueta publicitaria,
      medida <b>después</b> de agrupar. La etiqueta no interviene en ninguna
      distancia. Con «automoción» siendo el 24 % del corpus, una pureza cercana
      a esa cifra equivale a no separar nada.
    </p>`;
}

/* ══════════════════ Validación E3–E6 ══════════════════ */

let informeValidacion = null;

async function pintarValidacion() {
  if (!informeValidacion) {
    try {
      const respuesta = await fetch("validacion/informe.json");
      if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
      informeValidacion = await respuesta.json();
    } catch (error) {
      $("#val-cabecera").innerHTML = `<div class="aviso"><b>No se pudo cargar el informe</b>${error.message}</div>`;
      return;
    }
  }

  const v = informeValidacion;
  const pct = (x) => (x === null || x === undefined ? "—" : (x * 100).toFixed(1) + " %");
  const num = (x) => (x === null || x === undefined ? "—" : Number(x).toFixed(4));

  $("#val-cabecera").innerHTML = `
    <div class="sello">
      <span class="sello-punto"></span>
      <div>
        <b>${v.estatus === "empirical_frozen" ? "Corrida congelada · afirmaciones empíricas permitidas" : v.estatus}</b>
        <small>${v.run_id}</small>
      </div>
    </div>
    <div class="proc">
      <div><span>Ocurrencias</span><span>${v.corpus.occurrences}</span></div>
      <div><span>Familias</span><span>${v.corpus.families}</span></div>
      <div><span>Grupos de procedencia</span><span>${v.corpus.groups}</span></div>
      <div><span>Ámbitos de anotación</span><span>${v.corpus.scopes}</span></div>
      <div><span>Consultas elegibles</span><span>${v.corpus.eligible_queries}</span></div>
      <div><span>Consultas excluidas</span><span>${v.corpus.excluded_queries}</span></div>
      <div><span>Partición</span><span>${v.particion.type}</span></div>
      <div><span>Rejilla de parámetros</span><span>${v.configuracion.tamano_rejilla} candidatos</span></div>
    </div>`;

  const g = v.metricas_globales;
  $("#val-metricas").innerHTML = [
    [num(g.mAP), "mAP"],
    [num(g.MRR), "MRR"],
    [pct(g["Recall@1"]), "Recall@1"],
    [pct(g["Recall@10"]), "Recall@10"],
  ].map(([x, e]) => `<div class="cifra"><b>${x}</b><span>${e}</span></div>`).join("");

  const m = v.metricas_macro;
  $("#val-nota-metricas").innerHTML =
    `Agregadas sobre las ${g.eligible_queries} consultas. Promediando por pliegue en vez de por consulta: ` +
    `mAP ${num(m.mAP)}, MRR ${num(m.MRR)}. Intervalos por <i>${v.incertidumbre.method}</i> ` +
    `sobre ${v.incertidumbre.replicates.toLocaleString("es")} réplicas, semilla ${v.incertidumbre.seed}.`;

  $("#val-pliegues").innerHTML = `
    <thead><tr><th>Grupo excluido</th><th>n</th><th>mAP</th><th>MRR</th><th>γ</th><th>ω pc/lin/on/off</th></tr></thead>
    <tbody>${v.pliegues.map((p) => {
      const q = p.parametros || {};
      return `<tr>
        <td>${p.grupo_test}</td>
        <td>${p.consultas}</td>
        <td>${num(p.metricas.mAP)}</td>
        <td>${num(p.metricas.MRR)}</td>
        <td>${q.gamma ?? "—"}</td>
        <td>${[q.omega_pc, q.omega_lin, q.omega_on, q.omega_off].filter(Boolean).join(" / ") || "—"}</td>
      </tr>`;
    }).join("")}</tbody>`;

  $("#val-ablaciones").innerHTML = `
    <thead><tr><th>Id</th><th>Ablación</th><th>mAP</th><th>Δ mAP</th><th>Estatus</th></tr></thead>
    <tbody>${v.ablaciones.map((a) => {
      const d = a.delta_mAP;
      const clase = d > 0.001 ? "pos" : d < -0.001 ? "neg" : "";
      return `<tr>
        <td>${a.id}</td>
        <td style="white-space:normal;min-width:180px">${a.etiqueta}</td>
        <td>${num(a.mAP)}</td>
        <td class="${clase}">${d >= 0 ? "+" : ""}${num(d)}</td>
        <td style="white-space:normal">${a.estatus}</td>
      </tr>`;
    }).join("")}</tbody>`;

  const completo = v.ablaciones.find((a) => a.estatus === "metric_profile" && Math.abs(a.delta_mAP) < 1e-9);
  $("#val-nota-ablaciones").innerHTML =
    `Δ mAP es la diferencia frente al perfil MTI completo${completo ? ` (<b>${completo.id}</b>)` : ""}. ` +
    `Solo las marcadas <span class="mono">metric_profile</span> son métricas; las demás se declaran ` +
    `pseudométricas o experimentales y no sostienen afirmaciones de distancia.`;

  const t = v.trazabilidad;
  $("#val-traza").innerHTML = [
    ["Software", `${t.software.name} ${t.software.version}`],
    ["Python", `${t.python.version} (${t.python.implementation})`],
    ["Plataforma", t.plataforma],
    ["Commit", (t.commit || "").slice(0, 12)],
    ["Rama", t.rama],
    ["Árbol de trabajo", t.arbol_limpio ? "limpio" : "con cambios sin confirmar"],
    ["SHA-256 del árbol", (t.sha256_arbol || "").slice(0, 16) + "…"],
    ["SHA-256 del manifiesto", (t.sha256_manifiesto || "").slice(0, 16) + "…"],
    ["Duración", `${Math.round((v.duracion_segundos || 0) / 60)} min`],
  ].map(([k, x]) => `<div><span>${k}</span><span>${x ?? "—"}</span></div>`).join("");

  const avisos = [];
  if (!t.arbol_limpio) {
    avisos.push(`<div class="aviso suave"><b>Árbol de trabajo con cambios sin confirmar</b>
      La corrida se ejecutó con modificaciones no registradas en el commit
      ${(t.commit || "").slice(0, 12)}. El hash del árbol fuente queda anotado, pero
      reproducir la corrida exige ese estado exacto, no solo el commit.</div>`);
  }
  if (v.avisos.length) {
    avisos.push(`<div class="aviso suave"><b>${v.avisos.length} aviso(s) del ejecutor</b>
      ${v.avisos.map((a) => a.mensaje).join("<br>")}</div>`);
  }
  if (v.errores.length) {
    avisos.push(`<div class="aviso"><b>${v.errores.length} error(es)</b>${v.errores.join("<br>")}</div>`);
  }
  $("#val-avisos").innerHTML = avisos.join("");

  if (!pintarValidacion.resumenCargado) {
    pintarValidacion.resumenCargado = true;
    try {
      const respuesta = await fetch("validacion/resumen.md");
      $("#val-resumen").textContent = respuesta.ok
        ? await respuesta.text()
        : "No disponible.";
    } catch {
      $("#val-resumen").textContent = "No disponible.";
    }
  }
}

/* ══════════════════ Modo sin conexión ══════════════════ */

let cacheDisponible = false;

if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
  navigator.serviceWorker.register("sw.js")
    .then(() => { cacheDisponible = true; })
    .catch((error) => {
      // Sin service worker la app sigue funcionando —Pyodide viaja en la
      // carpeta— pero deja de poder abrirse ya cerrada y sin red.
      console.warn("service worker no disponible:", error.message);
      $("#btn-offline").hidden = true;
      $("#offline-estado").textContent =
        "Este navegador no permite guardar la app para uso sin conexión. El análisis " +
        "funciona igual: el intérprete de Python está dentro de la carpeta, no se " +
        "descarga de ningún sitio.";
    });
} else {
  $("#btn-offline").hidden = true;
  $("#offline-estado").textContent =
    "Para instalarla y usarla sin conexión hay que servirla por https (por ejemplo, GitHub Pages).";
}

$("#btn-offline").addEventListener("click", async () => {
  const boton = $("#btn-offline");
  const info = $("#offline-estado");
  boton.disabled = true;
  boton.textContent = "Preparando…";
  info.textContent = "Descargando el motor Python y guardándolo en caché. Puede tardar un minuto la primera vez.";
  try {
    await motor("preparar", {});
    await Promise.all(
      $$("#ejemplos button[data-src]").map((b) => fetch(b.dataset.src).catch(() => {}))
    );
    if (!cacheDisponible) throw new Error("el navegador no permitió guardar la app");
    boton.textContent = "Listo para funcionar sin conexión";
    info.textContent = "Ya puedes cerrar, activar el modo avión y volver a abrir: la app calcula igual.";
  } catch (error) {
    boton.disabled = false;
    boton.textContent = "Reintentar la preparación";
    info.textContent = `No se pudo completar: ${error.message}`;
  }
});

/* ══════════════════ Modo de lectura ══════════════════ */

/* Dos registros para el mismo contenido. «En claro» es el de por defecto porque
   la app está pensada para enseñarse a músicos, no a topólogos: retira la letra
   pequeña y deja las glosas. «Técnico» devuelve la notación completa, que es la
   que hace falta si alguien del tribunal quiere el detalle. */

const CLAVE_MODO = "mti-movil-modo";

function fijarModo(modo) {
  document.body.dataset.modo = modo;
  const boton = $("#btn-modo");
  boton.setAttribute("aria-pressed", String(modo === "claro"));
  boton.textContent = modo === "claro" ? "En claro" : "Técnico";
  try { localStorage.setItem(CLAVE_MODO, modo); } catch { /* modo privado */ }
}

$("#btn-modo").addEventListener("click", () => {
  const actual = document.body.dataset.modo === "claro" ? "tecnico" : "claro";
  fijarModo(actual);
  brindis(actual === "claro"
    ? "Explicación llana: se oculta la letra pequeña"
    : "Notación técnica completa");
});

/* ══════════════════ Arranque ══════════════════ */

let modoGuardado = "claro";
try { modoGuardado = localStorage.getItem(CLAVE_MODO) || "claro"; } catch { /* modo privado */ }
fijarModo(modoGuardado);

pintarTeclas();
fijarTonica(60);
if (leerBiblioteca().length) habilitarPaso("p-biblioteca");

motor("preparar", {})
  .then((datos) => { $("#version-nucleo").textContent = datos.software_version; })
  .catch(() => pintarEstadoMotor("error", "Motor no disponible"));

$("#btn-motor").addEventListener("click", () => {
  motor("preparar", {}).then(() => brindis("El motor MTI está cargado y listo"));
});
