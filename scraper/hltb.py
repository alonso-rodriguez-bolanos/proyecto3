"""Scraper de How Long To Beat con la biblioteca howlongtobeatpy. Busca el juego por nombre (o por id si url_hltb ya trae uno) y toma el tiempo de la historia principal y del 100 %. La biblioteca hace sus propias solicitudes, así que aquí se le agrega el límite por sitio, reintentos con espera creciente y la comprobación de que el resultado sea el juego correcto."""

import logging
import random
import re
import time

from . import config
from .limitador import turno
from .red import ErrorDescarga, fuente_segura

log = logging.getLogger("scraper.hltb")
SIMILITUD_MINIMA = 0.8  # debajo de esto el resultado se considera otro juego
ID_EN_URL = re.compile(r"howlongtobeat\.com/game/(\d+)")


def _consultar(consulta):
    """Corre una consulta a HLTB dentro del límite del sitio y la reintenta con espera de 5, 10 y 20 s. La biblioteca devuelve None cuando HLTB rechaza la búsqueda (por ejemplo, cuando frena por recibir muchas seguidas), así que None también se reintenta. Si el último intento falla se lanza ErrorDescarga y fuente_segura lo convierte en ok False."""
    for intento in range(1, config.INTENTOS_HLTB + 1):
        try:
            with turno("hltb"):
                resultado = consulta()
            if resultado is not None:
                return resultado
            error = "HLTB no respondió la búsqueda"
        except Exception as e:  # la biblioteca no tiene excepciones propias
            error = f"{type(e).__name__}: {e}"
        if intento == config.INTENTOS_HLTB:
            raise ErrorDescarga(f"{error} después de {intento} intentos")
        espera = min(config.ESPERA_HLTB_S * 2 ** (intento - 1) + random.uniform(0, 1), config.ESPERA_MAXIMA_S)
        log.warning("hltb intento %d/%d falló (%s), reintento en %.1fs", intento, config.INTENTOS_HLTB, error, espera)
        time.sleep(espera)


def elegir(candidatos: list, anio: int | None):
    """Elige el resultado correcto. Solo acepta nombres muy parecidos y, si hay varios, prefiere el del año de lanzamiento del REPO (así Hades no se confunde con Hades II)."""
    buenos = [c for c in candidatos or [] if c.similarity >= SIMILITUD_MINIMA]
    if not buenos:
        return None
    if anio:
        del_anio = [c for c in buenos if abs((c.release_world or 0) - anio) <= 1]
        buenos = del_anio or buenos
    return max(buenos, key=lambda c: c.similarity)


def _horas(valor) -> float | None:
    """Convierte las horas de la biblioteca a número, o None si no hay dato (HLTB usa 0 o None)."""
    return round(float(valor), 1) if valor else None


def buscar(juego: dict):
    """Devuelve el resultado de HLTB del juego (por id si url_hltb trae uno, si no por nombre y año) o None. Puede lanzar excepciones."""
    from howlongtobeatpy import HowLongToBeat  # import aquí para que el motor funcione aunque falte la biblioteca

    buscador = HowLongToBeat()
    id_hltb = ID_EN_URL.search(juego.get("url_hltb") or "")
    if id_hltb:
        return _consultar(lambda: buscador.search_from_id(int(id_hltb.group(1))))
    fecha = str(juego.get("fecha_lanzamiento") or "")
    return elegir(_consultar(lambda: buscador.search(juego["nombre"])), int(fecha[:4]) if fecha[:4].isdigit() else None)


@fuente_segura("hltb")
def scrape_hltb(juego: dict) -> dict:
    """Devuelve {"horas_main": 22.5, "horas_completo": 95.0}. Si HLTB no encuentra el juego o no tiene tiempos devuelve ok False."""
    resultado = buscar(juego)
    if resultado is None:
        return {"ok": False, "error": "HLTB no encontró el juego"}

    main, completo = _horas(resultado.main_story), _horas(resultado.completionist)
    if main is None and completo is None:
        return {"ok": False, "error": "HLTB no tiene tiempos para este juego"}
    return {"horas_main": main, "horas_completo": completo}


if __name__ == "__main__":
    import csv
    import sys
    from pathlib import Path

    csv_juegos = Path(__file__).resolve().parent.parent / "datos" / "juegos.csv"
    for fila in list(csv.DictReader(open(csv_juegos, encoding="utf-8")))[: int(sys.argv[1]) if len(sys.argv) > 1 else 5]:
        print(fila["nombre"], scrape_hltb(fila))
