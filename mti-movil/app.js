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
    worker = new Worker("worker.js", { type: "module" });
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
}

function habilitarPaso(idPanel, habilitado = true) {
  const boton = $$(".paso").find((b) => b.dataset.panel === idPanel);
  if (boton) boton.disabled = !habilitado;
}

$$(".paso").forEach((boton) => {
  boton.addEventListener("click", () => {
    if (boton.disabled) return;
    if (boton.dataset.panel === "p-biblioteca") pintarBiblioteca();
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

/* ══════════════════ Arranque ══════════════════ */

pintarTeclas();
fijarTonica(60);
if (leerBiblioteca().length) habilitarPaso("p-biblioteca");

motor("preparar", {})
  .then((datos) => { $("#version-nucleo").textContent = datos.software_version; })
  .catch(() => pintarEstadoMotor("error", "Motor no disponible"));

$("#btn-motor").addEventListener("click", () => {
  motor("preparar", {}).then(() => brindis("El motor MTI está cargado y listo"));
});
