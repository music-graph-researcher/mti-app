"""Sustituto inerte del módulo de resúmenes con IA.

`backend/ai_summaries.py` llama a la API de DeepSeek por internet. Es lo único
de todo el proyecto que enviaría datos fuera del dispositivo, y esta app se
apoya en no hacerlo: los MIDIs y los análisis no salen del teléfono.

Por eso aquí no se copia aquel módulo, sino que se reemplaza. Este archivo no
contiene ninguna llamada de red —no importa `urllib`, ni `socket`, ni nada
equivalente— y se limita a devolver la misma forma de respuesta que el original
produce cuando la IA está desactivada. `operations.py` y
`operational_topology.py` lo importan sin enterarse del cambio, y el cálculo del
capítulo 5 sigue siendo idéntico: los resúmenes eran una narración añadida
encima, nunca parte del resultado.

Si algún día se quisiera recuperar esa función, sería un cambio deliberado:
copiar el módulo real y asumir que la app deja de ser autónoma.
"""

from __future__ import annotations

from typing import Any

STATUS = "DISABLED_ON_DEVICE"
NOTE = (
    "Los resúmenes con IA están desactivados en la app móvil: exigirían enviar "
    "datos a un servicio externo. El cálculo del marco no depende de ellos."
)


def ai_enabled_from_request(req: Any) -> bool:
    """Siempre desactivado. No hay proveedor configurado ni forma de configurarlo."""

    del req
    return False


def summarize_search(ai_enabled: bool, **_kwargs: Any) -> dict[str, Any]:
    del ai_enabled
    return {"status": STATUS, "note": NOTE, "summary": None}


def summarize_topology_certification(ai_enabled: bool, **_kwargs: Any) -> dict[str, Any]:
    del ai_enabled
    return {"status": STATUS, "note": NOTE, "summary": None}
