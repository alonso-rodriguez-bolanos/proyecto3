"""Límite por sitio compartido por todos los procesos. Cada sitio tiene un semáforo que deja pasar pocas solicitudes a la vez y una pausa mínima entre solicitudes. Se usa así: with turno("steam"): descargar."""

import multiprocessing
import time
from contextlib import contextmanager

from . import config

_limitador = None  # el limitador que usa este proceso


def crear_limitador(contexto=None, limites: dict | None = None) -> dict:
    """Crea un semáforo, un candado y un valor compartido por sitio. Se crea una vez en el proceso principal y se reparte a los hijos."""
    contexto = contexto or multiprocessing.get_context("spawn")
    limites = limites or config.LIMITES_SITIO
    limitador = {}
    for sitio, (máximo, pausa) in limites.items():
        limitador[sitio] = {
            "semaforo": contexto.BoundedSemaphore(max(1, máximo)),  # cupos a la vez
            "candado": contexto.Lock(),  # protege proximo
            "proximo": contexto.Value("d", 0.0, lock=False),  # hora del próximo turno libre
            "pausa": float(pausa),
        }
    return limitador


def instalar_limitador(limitador: dict) -> None:
    """Deja el limitador listo para que turno lo use en este proceso."""
    global _limitador
    _limitador = limitador


@contextmanager
def turno(sitio: str):
    """Espera un cupo del sitio y después espera hasta la hora del próximo turno libre. Al salir devuelve el cupo aunque haya error."""
    if _limitador is None:
        instalar_limitador(crear_limitador())  # para probar un scraper suelto
    datos = _limitador.get(sitio) or _limitador["otro"]
    datos["semaforo"].acquire()  # espera un cupo libre
    try:
        with datos["candado"]:  # un proceso a la vez reserva su turno
            ahora = time.time()
            inicio = max(ahora, datos["proximo"].value)
            datos["proximo"].value = inicio + datos["pausa"]
        if inicio > ahora:
            time.sleep(inicio - ahora)  # duerme fuera del candado
        yield
    finally:
        datos["semaforo"].release()
