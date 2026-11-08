"""Lee la lista de juegos desde Supabase. Si Supabase no responde usa la última copia guardada en datos/repo_cache.json."""

import json
import logging
import os

from . import config
from .red import ErrorDescarga, obtener_html

log = logging.getLogger("scraper.repo")
RUTA_CACHE = config.RAIZ / "datos" / "repo_cache.json"
OBLIGATORIAS = ("id", "nombre", "plataformas", "precio_sugerido", "url_steam", "url_psstore")


def _descargar() -> list[dict]:
    """Pide a Supabase las filas con activo = true, de 1000 en 1000, hasta que llega una página incompleta."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    llave = os.environ.get("SUPABASE_KEY", "")
    if not url or not llave:
        raise RuntimeError("faltan SUPABASE_URL o SUPABASE_KEY en el .env")
    encabezados = {"apikey": llave}
    if llave.startswith("eyJ"):  # las llaves viejas también van aquí
        encabezados["Authorization"] = f"Bearer {llave}"
    filas, desde = [], 0
    while True:
        texto = obtener_html("supabase", f"{url}/rest/v1/juegos", encabezados=encabezados,
                             params={"select": "*", "activo": "eq.true", "order": "id", "limit": 1000, "offset": desde})
        página = json.loads(texto)
        filas.extend(página)
        if len(página) < 1000:
            return filas
        desde += 1000


def leer_repo() -> list[dict]:
    """Devuelve los juegos activos ordenados por id. Guarda una copia local cada vez que lee bien y salta las filas incompletas."""
    try:
        filas = _descargar()
        RUTA_CACHE.parent.mkdir(exist_ok=True)
        RUTA_CACHE.write_text(json.dumps(filas, ensure_ascii=False), encoding="utf-8")
        origen = "Supabase"
    except (ErrorDescarga, RuntimeError, ValueError) as error:
        if not RUTA_CACHE.exists():
            raise RuntimeError(f"no se pudo leer el REPO y no hay copia local: {error}") from error
        log.error("Supabase falló %s, se usa la copia local", error)
        filas = json.loads(RUTA_CACHE.read_text(encoding="utf-8"))
        origen = "copia local"
    juegos = []
    for fila in filas:
        faltan = [c for c in OBLIGATORIAS if fila.get(c) in (None, "", [])]
        if faltan:
            log.warning("se salta %r porque le falta %s", fila.get("nombre"), ", ".join(faltan))
        elif fila.get("activo", True):
            juegos.append(fila)
    log.info("REPO leído de %s: %d juegos", origen, len(juegos))
    return sorted(juegos, key=lambda j: j["id"])
