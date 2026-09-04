# MTI móvil · prototipo

App instalable en el móvil que ejecuta el **Marco Topológico Invariante** sobre
cualquier archivo MIDI. No hay servidor, no hay terminal y no hace falta
conexión: el intérprete de Python viaja dentro de la propia carpeta.

El núcleo de cálculo es **el mismo código** del repositorio: los módulos de
`py/mticore/` son copia literal de `backend/`. La app no reimplementa nada del
marco, solo lo invoca. Un análisis hecho aquí y otro hecho con
`python3 -m backend.server` dan el mismo resultado.

---

## Probarlo ahora mismo

```bash
./servir.sh
```

Abre <http://localhost:8080>. El guion imprime también la dirección de la wifi
para abrirlo desde el móvil.

## Ponerlo en el móvil de verdad

Para instalarlo como app y que funcione **sin conexión** hace falta servirlo por
`https`. La vía más simple y gratuita es GitHub Pages:

1. Sube el contenido de esta carpeta a un repositorio (por ejemplo `mti-movil`).
2. En el repositorio: **Settings → Pages → Source: Deploy from a branch**,
   rama `main`, carpeta `/ (root)`.
3. Espera un minuto y abre la URL que te da GitHub desde el móvil.
4. En el móvil: **Compartir → Añadir a pantalla de inicio** (iPhone) o
   **⋮ → Instalar aplicación** (Android).
5. Ábrela una vez con conexión. Ya queda todo en caché.

A partir de ahí funciona en modo avión.

> El repositorio puede ser privado si prefieres, pero entonces Pages requiere
> cuenta de pago. Para una defensa, un repositorio público con solo esta carpeta
> suele ser lo más cómodo.

---

## Qué hace

**1 · Archivo.** Carga cualquier `.mid` o `.midi` de tipo 0 o 1, desde Archivos,
Drive, Descargas o lo que tengas en el teléfono. Incluye cuatro ejemplos: dos
motivos y dos obras completas.

**2 · Fragmento.** Un piano-roll de la obra entera. Arrastra para acotar el
fragmento; filtra por pista y canal. La segmentación es una entrada externa del
marco, y aquí es explícita y manipulable. Se avisa si el fragmento es
desproporcionado.

**3 · Tónica.** Selector de `p_ton` con nombre de nota y número MIDI. Los
«atajos» (nota más grave, primera nota, altura más repetida) son conveniencias
estadísticas etiquetadas como tales: **el marco no infiere `p_ton`**, la elige
el analista.

**4 · Análisis.** Grafo MTI, firma canónica, familia normalizada con racionales
exactos y bloque de procedencia con el SHA-256 del MIDI de entrada. Exporta
`.mti.json` portable (formato 1.1), el análisis completo y el grafo en SVG.

**5 · Biblioteca.** Los motivos analizados quedan guardados en el dispositivo.
Elige dos y calcula `Dγ`, el índice relativo `D̄γ` y los bloques contextuales
§3.6 —melódico, armónico y rítmico-métrico— sin agregarlos entre sí.

**6 · Corpus.** Las 25 obras clásicas empleadas en publicidad, en sus dos
texturas, con el análisis de corpus ya calculado: familias, silueta y
composición por sector. Y en cada análisis, la proximidad del motivo a los 50
registros.

La etiqueta de sector **nunca entra en `Dγ`**. Se muestra al lado del resultado
como contexto, igual que hace `backend/corpus_comparison.py`. La app ordena
distancias; no clasifica ni predice sectores, y lo dice en pantalla.

**7 · Extendido.** Las lecturas comparativas del §3.6 sobre el mismo corpus:
nueve en textura armónica y ocho en melódica —no hay movimiento del bajo en una
línea sola—. Cada lectura con su silueta, sus familias, su pureza respecto de la
etiqueta publicitaria, su homología persistente y su medoide o «forma central».

Se muestran separadas y sin agregar, como exige el marco. Y se señala cuando una
lectura no separa nada: fundamental, inversión y movimiento del bajo dejan los
25 registros en una sola familia con silueta cero.

**8 · Operacional.** El capítulo 5, en vivo. Eliges origen `X` y destino `Y`
—el par canónico o dos motivos tuyos de la biblioteca— y calculas la trayectoria
con su contraste §5.9.1, el testigo constructivo de alcanzabilidad, el multigrafo
finito `G_R` dentro de una envolvente que controlas, y la comparación entre la
topología estructural y la operacional. El informe completo se puede descargar.

Sin resúmenes con IA: `backend/ai_summaries.py` llama a un servicio externo y
aquí está sustituido por un módulo inerte. El cálculo es idéntico.

**9 · Jerarquía.** El capítulo 6, en vivo. Las diecinueve comprobaciones
fundacionales de la transición `A₀→₁`, la constitución con su testigo de
procedencia, el constructor de preimagen y la verificación de que el diagrama de
elevación conmuta. En vez de teclear JSON, la configuración basal `Ξ₀` se
construye a partir de un motivo analizado en la propia app.

**10 · Validación.** La corrida `frozen` de E3–E6 sobre JKU-PDD: métricas
globales, los cinco pliegues con sus pesos seleccionados, las doce ablaciones
con su delta frente al perfil completo, y la trazabilidad (commit, hashes,
plataforma). Incluye el informe completo de la corrida.

De solo lectura, y a propósito: la validación necesita los 384 MB del corpus y
multiproceso. Una corrida certificada se exhibe, no se rehace en un móvil. La
app señala además que el árbol de trabajo tenía cambios sin confirmar, porque
eso condiciona qué significa «reproducible».

## Qué no hace todavía

- Del 8001 solo trae el informe ya calculado y la comparación por pares contra
  el corpus. No recalcula matrices, clustering ni homología persistente: eso usa
  multiproceso, que Pyodide no soporta, y el corpus es fijo.
- Del 8004 muestra una corrida ya ejecutada; no lanza corridas nuevas.
- Del 8005 muestra el informe ya calculado; no admite corpus nuevos.
- Del 8002 no trae los paneles de álgebra ni de refinamiento, ni el editor de
  acciones paso a paso del escritorio.
- Del 8003 expone las cuatro operaciones de su interfaz, no los veintiún
  endpoints del servidor.
- No importa `.mti.json` ni `.mti.csv`; de momento solo entra MIDI.
- No exporta PDF. El SVG sirve para llevarlo a la tesis en vectorial.
- No hace homología persistente ni clustering en vivo: es trabajo de corpus.
- No incluye `backend/ai_summaries.py`, que llama a la API de DeepSeek. Es lo
  único del proyecto que enviaría datos fuera del dispositivo, y queda excluido
  deliberadamente.

---

## Rendimiento medido

Tiempos reales de construcción del grafo, en un Mac. En el móvil, multiplica
por tres o cuatro.

| Fragmento | Eventos | Aristas | Python nativo | En el navegador |
|---|---:|---:|---:|---:|
| Motivo de Beethoven | 8 | 25 | 0,00 s | instantáneo |
| Motivo de Rossini (16 notas) | 16 | 63 | — | 0,04 s |
| Motivo de Rossini completo | 39 | 155 | 0,00 s | ~0,1 s |
| Mazurca de Chopin entera | 2.080 | ~5.000 | 2,5 s | más de un minuto |

Y el resto de capítulos, medidos en el navegador:

| Operación | Tiempo |
|---|---:|
| Proximidad al corpus (50 comparaciones) | 0,1 s |
| Comprobaciones fundacionales del cap. 6 | instantáneo |
| Constitución, preimagen, elevación | instantáneo |
| Búsqueda `G_R` (400 nodos, 4 pasos) | ~11 s |
| Comparación topológica | ~4 s |

La búsqueda del capítulo 5 es lo único lento. Bajar «Nodos» de 400 a 150 la
acorta mucho y sigue certificando la topología.

La conclusión práctica está incorporada al diseño: **el marco pide un motivo, no
una partitura**. Por eso la app avisa a partir de 250 eventos y no dibuja el
grafo automáticamente por encima de 200 —dibujarlo produciría una maraña
ilegible—, aunque siempre deja continuar. Las dos obras completas están entre
los ejemplos justamente para poder enseñar ese límite en la defensa.

---

## Estructura

```
mti-movil/
├── index.html              interfaz, siete pasos
├── styles.css              hoja única, claro y oscuro
├── app.js                  interacción: piano-roll, selección, presentación
├── worker.js               arranca Pyodide y expone el núcleo MTI
├── sw.js                   caché: lo que permite funcionar sin red
├── manifest.webmanifest    icono, nombre, pantalla completa
├── servir.sh               servidor local para pruebas
├── py/
│   ├── mti_bridge.py       única capa nueva: traduce peticiones al núcleo
│   └── mticore/            copia literal de backend/ (no editar aquí)
│                           salvo ai_summaries.py, que es un sustituto inerte
├── vendor/pyodide/         CPython 3 en WebAssembly (~13 MB)
├── corpus/                 nice-dataset e informe 8001, ya calculados
├── validacion/             corrida E3–E6 del 8004, de solo lectura
├── herramientas/           guiones que regeneran corpus/ y validacion/
├── ejemplos/               cuatro MIDIs de prueba
└── iconos/
```

## Regenerar los datos del corpus

`corpus/corpus.json` y `corpus/informe.json` se producen desde el proyecto:

```bash
python3 ruta/a/mti-movil/herramientas/generar_corpus.py \
    --proyecto . --salida ruta/a/mti-movil/corpus
```

Hazlo desde la raíz del repositorio MTI. Son 44 KB y 78 KB.

Y el informe de validación, desde una corrida cualquiera:

```bash
python3 ruta/a/mti-movil/herramientas/generar_validacion.py \
    --corrida runs/<run_id> --salida ruta/a/mti-movil/validacion
```

Extrae 6 KB de métricas del `report.json` de 2,1 MB y copia el `summary.md`.

Y las lecturas del corpus extendido:

```bash
python3 ruta/a/mti-movil/herramientas/generar_extendido.py \
    --proyecto . --salida ruta/a/mti-movil/corpus
```

Tarda 7 s y produce 122 KB.

## Al publicar una versión nueva

Un solo comando, antes de subir nada:

```bash
python3 herramientas/versionar.py 7
```

Cambia la versión en los cuatro sitios donde tiene que coincidir: `VERSION` en
`sw.js`, las consultas `?v=` de `styles.css` y `app.js` en `index.html`, la del
worker en `app.js`, y las de `RECURSOS` en `sw.js`.

Hacerlo a mano en uno solo produce un fallo desagradable y difícil de leer: el
navegador se trae el `index.html` nuevo y reutiliza de su caché HTTP el `app.js`
viejo, así que aparecen pestañas que existen y no hacen nada, sin ningún error
en consola. Pasó una vez; el guion existe para que no vuelva a pasar.

## Si cambia el núcleo del proyecto

Los módulos de `py/mticore/` son copias. Cuando toques `backend/` en el
repositorio principal, vuelve a copiarlos:

```bash
for f in midi mti analysis compare context version portable hierarchy \
         operations operational_topology persistent_homology; do
  cp ruta/al/MTI/backend/$f.py py/mticore/$f.py
done
```

Dos archivos de `py/mticore/` son propios de esta carpeta y **no** deben
sobrescribirse: `__init__.py` y `ai_summaries.py`, el sustituto sin red.

Si añades un módulo nuevo, decláralo en dos sitios: `ARCHIVOS_PY` en
`worker.js` y `RECURSOS` en `sw.js`.

## Detalles técnicos

- **Pyodide 314.0.6**, incrustado en `vendor/`. No se contacta con ningún CDN:
  ni el primer arranque depende de la red. Servida desde cualquier servidor
  estático, la app calcula aunque el service worker no esté disponible; este
  solo añade poder **abrirla ya cerrada y sin red**, y requiere `https`.
- El núcleo MTI **no usa una sola dependencia externa** —solo biblioteca
  estándar de Python—, que es lo que hace viable ejecutarlo en el navegador.
- El cálculo vive en un *web worker*: un fragmento pesado no congela la
  pantalla, y el aviso de progreso sigue respondiendo.
- Los archivos nunca salen del dispositivo. No hay analítica ni telemetría.
- La biblioteca usa `localStorage`, así que es por dispositivo y por navegador.
  Exporta lo que quieras conservar.
