"""Scrapers de prueba. Hacen lo mismo que los reales pero en vez de descargar esperan un segundo e inventan datos con el formato correcto. Sirven para probar el motor sin internet y como ejemplo para escribir los reales."""

import os
import random
import time
from concurrent.futures import ThreadPoolExecutor

from .limitador import turno
from .red import fuente_segura

DURACION_S = float(os.environ.get("DURACION_FALSO_S", 1.0))  # lo que tarda una página falsa
PROB_FALLO = float(os.environ.get("PROB_FALLO_FALSO", 0.0))  # 0.1 hace fallar el 10 por ciento


def _descarga_falsa(sitio: str) -> None:
    """Espera su turno y simula una descarga. A veces falla a propósito si PROB_FALLO es mayor que cero."""
    with turno(sitio):
        time.sleep(DURACION_S)
    if random.random() < PROB_FALLO:
        raise TimeoutError("falla simulada")


def _tienda(juego: dict, sitio: str, nombre: str, plataforma: str) -> dict:
    """Arma el resultado de una tienda con un precio inventado."""
    _descarga_falsa(sitio)
    regular = float(juego.get("precio_sugerido") or 59.99)
    actual = round(regular * (1 - random.choice([0, 0, 0.25, 0.5, 0.75])), 2)
    return {"tienda": nombre, "precio_actual": actual, "precio_regular": regular, "formato": "Digital",
            "plataforma": plataforma, "url": juego.get(f"url_{sitio}"), "en_oferta": actual < regular,
            "descuento_pct": round((regular - actual) / regular * 100)}


@fuente_segura("steam")
def scrape_steam(juego: dict) -> dict:
    """Steam de prueba."""
    return _tienda(juego, "steam", "Steam", "PC")


@fuente_segura("psstore")
def scrape_psstore(juego: dict) -> dict:
    """PlayStation Store de prueba."""
    return _tienda(juego, "psstore", "PlayStation Store", "PS5")


def procesar_tiendas(juego: dict, max_workers: int = 2) -> list[dict]:
    """Nivel 3: consulta las tiendas al mismo tiempo con un hilo por tienda."""
    with ThreadPoolExecutor(max_workers=max_workers) as hilos:
        futuros = [("Steam", hilos.submit(scrape_steam, juego)), ("PlayStation Store", hilos.submit(scrape_psstore, juego))]
    resultados = []
    for nombre, futuro in futuros:
        dato = futuro.result()
        dato.setdefault("tienda", nombre)  # si falló igual se sabe qué tienda era
        resultados.append(dato)
    return resultados


@fuente_segura("metacritic")
def scrape_metacritic(juego: dict) -> dict:
    """Metacritic de prueba."""
    _descarga_falsa("metacritic")
    return {"score": random.randint(60, 97)}


@fuente_segura("hltb")
def scrape_hltb(juego: dict) -> dict:
    """How Long To Beat de prueba."""
    _descarga_falsa("hltb")
    horas = round(random.uniform(5, 60), 1)
    return {"horas_main": horas, "horas_completo": round(horas * 2.5, 1)}


def juegos_falsos(cantidad: int) -> list[dict]:
    """Inventa una lista de juegos para probar sin Supabase."""
    return [{"id": n, "nombre": f"Juego de prueba {n}", "plataformas": ["PC", "PS5"], "fecha_lanzamiento": "2024-01-01",
             "precio_sugerido": 59.99, "imagen_url": None, "url_steam": f"https://store.steampowered.com/app/{n}/",
             "url_psstore": f"https://store.playstation.com/en-us/concept/{n}", "activo": True}
            for n in range(1, cantidad + 1)]
