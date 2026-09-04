#!/usr/bin/env bash
# Sirve la app en local. Útil para probarla en el ordenador y, sobre todo, para
# abrirla desde el móvil por la misma wifi: el guion imprime la dirección.
#
#   ./servir.sh          → puerto 8080
#   ./servir.sh 9000     → otro puerto
#
# Nota: el modo sin conexión (service worker) solo se activa en https o en
# localhost. Por wifi verás la app y podrás analizar, pero para instalarla como
# app y que funcione sin red hay que publicarla en https — mira el LEEME.

set -euo pipefail
PUERTO="${1:-8080}"
cd "$(dirname "$0")"

IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "")
echo "MTI móvil"
echo "  en este equipo   http://localhost:${PUERTO}"
[ -n "$IP" ] && echo "  desde el móvil   http://${IP}:${PUERTO}   (misma wifi)"
echo "  Ctrl+C para parar"
echo

exec python3 -m http.server "$PUERTO" --bind 0.0.0.0
