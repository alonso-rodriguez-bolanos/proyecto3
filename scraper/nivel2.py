"""Nivel 2: procesa un juego. Lanza las tiendas, Metacritic y HLTB al mismo tiempo en hilos y junta todo en un registro. Usa hilos porque las tres tareas pasan casi todo el tiempo esperando la red."""

import importlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as TiempoAgotado
from datetime import datetime, timezone

from . import config
from .red import describir_error

log = logging.getLogger("scraper.nivel2")
TIENDAS = [("Steam", "url_steam"), ("PlayStation Store", "url_psstore"), ("Xbox Store", "url_xbox"), ("Nintendo eShop", "url_eshop")]
# archivo dentro de scraper y función que el motor busca para cada fuente
FUENTES_REALES = {"procesar_tiendas": "tiendas", "scrape_metacritic": "metacritic", "scrape_hltb": "hltb"}


def opciones_por_defecto(**cambios) -> dict:
    """Opciones que viajan a cada proceso: si usar los scrapers de prueba, cuántos hilos y el tiempo máximo por juego."""
    opciones = {"usar_falsos": False, "workers_fuentes": config.WORKERS_FUENTES,
                "workers_tiendas": config.WORKERS_TIENDAS, "timeout_fuente_s": config.TIMEOUT_FUENTE_S}
    opciones.update(cambios)
    return opciones


def obtener_fuentes(usar_falsos: bool) -> dict:
    """Devuelve las funciones de cada fuente. Las reales se buscan en scraper/tiendas.py, metacritic.py y hltb.py. Si falta alguna lanza ImportError diciendo cuál."""
    if usar_falsos:
        from . import falsos
        return {nombre: getattr(falsos, nombre) for nombre in FUENTES_REALES}
    fuentes = {}
    for función, archivo in FUENTES_REALES.items():
        try:
            fuentes[función] = getattr(importlib.import_module(f"scraper.{archivo}"), función)
        except (ImportError, AttributeError) as error:
            raise ImportError(f"falta scraper/{archivo}.py con {función}(), mientras tanto usar --falsos") from error
    return fuentes


def _tiendas_con_error(juego: dict, texto: str) -> list[dict]:
    """Una entrada con ok False por cada tienda que el juego tiene en el REPO."""
    return [{"tienda": nombre, "ok": False, "error": texto} for nombre, columna in TIENDAS if juego.get(columna)]


def _llamar(nombre: str, función, *argumentos):
    """Ejecuta una fuente y atrapa cualquier excepción que se haya escapado."""
    try:
        return función(*argumentos)
    except Exception as error:
        texto = describir_error(error)
        log.error("%s falló para %r: %s", nombre, argumentos[0].get("nombre"), texto)
        return {"ok": False, "error": texto}


def armar_registro(juego: dict, tiendas: list, metacritic: dict, hltb: dict) -> dict:
    """Junta los datos de todas las fuentes en el formato del data.json con la fecha y hora de la consulta."""
    precio = juego.get("precio_sugerido")
    return {
        "id": juego["id"],
        "nombre": juego["nombre"],
        "imagen": juego.get("imagen_url"),
        "plataformas": list(juego.get("plataformas") or []),
        "fecha_lanzamiento": str(juego["fecha_lanzamiento"]) if juego.get("fecha_lanzamiento") else None,
        "precio_sugerido": float(precio) if precio is not None else None,
        "tiendas": tiendas,
        "metacritic": metacritic,
        "hltb": hltb,
        "ultima_actualizacion": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def procesar_juego(juego: dict, opciones: dict | None = None) -> dict:
    """Consulta las tres fuentes de un juego en hilos y devuelve su registro. Una fuente que falla o tarda demasiado queda con ok False. Nunca lanza excepciones."""
    opciones = opciones or opciones_por_defecto()
    inicio = time.perf_counter()
    try:
        fuentes = obtener_fuentes(opciones["usar_falsos"])
    except ImportError as error:
        log.error(str(error))
        falla = {"ok": False, "error": "scraper no disponible"}
        return armar_registro(juego, _tiendas_con_error(juego, falla["error"]), dict(falla), dict(falla))

    tareas = {
        "tiendas": (fuentes["procesar_tiendas"], juego, opciones["workers_tiendas"]),
        "metacritic": (fuentes["scrape_metacritic"], juego),
        "hltb": (fuentes["scrape_hltb"], juego),
    }
    hilos = ThreadPoolExecutor(max_workers=opciones["workers_fuentes"])
    resultados = {}
    try:
        futuros = {nombre: hilos.submit(_llamar, nombre, *tarea) for nombre, tarea in tareas.items()}
        límite = inicio + opciones["timeout_fuente_s"]
        for nombre, futuro in futuros.items():
            try:
                resultados[nombre] = futuro.result(timeout=max(0.0, límite - time.perf_counter()))
            except TiempoAgotado:
                log.error("%s no terminó a tiempo para %r", nombre, juego["nombre"])
                resultados[nombre] = {"ok": False, "error": "timeout global"}
    finally:
        hilos.shutdown(wait=False, cancel_futures=True)  # no espera a un hilo colgado

    tiendas = resultados["tiendas"]
    if not isinstance(tiendas, list):  # procesar_tiendas falló completo
        tiendas = _tiendas_con_error(juego, tiendas.get("error", "error"))
    registro = armar_registro(juego, tiendas, resultados["metacritic"], resultados["hltb"])
    fallas = sum(1 for t in tiendas if not t.get("ok", True)) + sum(1 for f in ("metacritic", "hltb") if not registro[f].get("ok", True))
    log.info("juego %s %r listo en %.1fs con %d fuentes fallidas", juego["id"], juego["nombre"], time.perf_counter() - inicio, fallas)
    return registro
