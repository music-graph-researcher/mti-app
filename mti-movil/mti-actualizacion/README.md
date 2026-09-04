# MTI · análisis de motivos

Aplicación web instalable que ejecuta el **Marco Topológico Invariante** sobre
cualquier archivo MIDI, íntegramente dentro del dispositivo.

No tiene servidor. El MIDI se lee, se analiza y se muestra en el propio
navegador: ningún archivo ni resultado sale del dispositivo, y no hay analítica
ni telemetría de ningún tipo. El intérprete de Python viaja incluido, de modo
que una vez instalada funciona sin conexión.

El núcleo de cálculo es copia literal de `backend/` del proyecto
[cartontabla/MTI](https://github.com/cartontabla/MTI); esta aplicación no
reimplementa el marco, solo lo invoca.

Instrucciones de uso, límites y detalles técnicos: [LEEME.md](LEEME.md).
