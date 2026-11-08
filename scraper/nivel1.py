"""Nivel 1: reparte los juegos entre varios procesos. Es el nivel que usa varios núcleos de verdad porque cada proceso tiene su propio GIL. Todos los procesos comparten el mismo limitador y mandan su log a una sola cola."""

import logging
import logging.handlers
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool

from .limitador import crear_limitador, instalar_limitador
from .nivel2 import _tiendas_con_error, armar_registro, opciones_por_defecto, procesar_juego
from .red import describir_error

log = logging.getLogger("scraper.nivel1")
CONTEXTO = multiprocessing.get_context("spawn")  # igual en Windows macOS y Linux


def _iniciar_proceso(limitador: dict, cola_log) -> None:
    """Corre una vez al nacer cada proceso hijo: manda su log a la cola compartida e instala el limitador."""
    raíz = logging.getLogger()
    raíz.handlers.clear()
    raíz.addHandler(logging.handlers.QueueHandler(cola_log))
    raíz.setLevel(logging.INFO)
    instalar_limitador(limitador)


def registro_de_error(juego: dict, error) -> dict:
    """Registro con todas las fuentes en error para un juego cuyo proceso falló."""
    texto = error if isinstance(error, str) else describir_error(error)
    falla = {"ok": False, "error": texto}
    return armar_registro(juego, _tiendas_con_error(juego, texto), dict(falla), dict(falla))


def _una_ronda(juegos: list[dict], num_workers: int, opciones: dict, limitador: dict, cola_log) -> tuple[list, list]:
    """Procesa los juegos en un pool de procesos. Devuelve los registros listos y los juegos que quedaron sin hacer porque un proceso murió."""
    listos, rotos = [], []
    with ProcessPoolExecutor(max_workers=num_workers, mp_context=CONTEXTO,
                             initializer=_iniciar_proceso, initargs=(limitador, cola_log)) as procesos:
        futuros = {procesos.submit(procesar_juego, juego, opciones): juego for juego in juegos}
        for hechos, futuro in enumerate(as_completed(futuros), start=1):
            juego = futuros[futuro]
            try:
                listos.append(futuro.result())
            except BrokenProcessPool:
                rotos.append(juego)  # se reintenta en otra ronda
            except Exception as error:
                log.error("juego %r falló completo: %s", juego.get("nombre"), error)
                listos.append(registro_de_error(juego, error))
            if hechos % max(1, len(juegos) // 10) == 0:
                log.info("avance %d/%d juegos", hechos, len(juegos))
    return listos, rotos


def procesar_repo(juegos: list[dict], num_workers: int, opciones: dict | None = None, limitador: dict | None = None) -> list[dict]:
    """Procesa todos los juegos con num_workers procesos y devuelve un registro por juego ordenado por id. Si un proceso muere, sus juegos se repiten una vez en un pool nuevo."""
    opciones = opciones or opciones_por_defecto()
    limitador = limitador or crear_limitador(CONTEXTO)
    cola_log = CONTEXTO.Queue()
    oyente = logging.handlers.QueueListener(cola_log, *(logging.getLogger().handlers or [logging.StreamHandler()]),
                                            respect_handler_level=True)
    oyente.start()  # un solo hilo escribe lo que mandan los hijos
    inicio = time.perf_counter()
    resultados, pendientes = [], list(juegos)
    try:
        for ronda in (1, 2):
            listos, pendientes = _una_ronda(pendientes, num_workers, opciones, limitador, cola_log)
            resultados.extend(listos)
            if not pendientes:
                break
            log.error("ronda %d: %d juegos sin hacer porque murió un proceso", ronda, len(pendientes))
        resultados.extend(registro_de_error(juego, "proceso caído") for juego in pendientes)
    finally:
        oyente.stop()
    log.info("nivel 1 terminó %d juegos con %d procesos en %.1fs", len(resultados), num_workers, time.perf_counter() - inicio)
    return sorted(resultados, key=lambda r: r["id"])


def procesar_repo_secuencial(juegos: list[dict], opciones: dict | None = None) -> list[dict]:
    """Versión de referencia para medir el speedup. Mismo código pero todo en el proceso principal y con 1 hilo en los niveles 2 y 3."""
    opciones = dict(opciones or opciones_por_defecto())
    opciones.update(workers_fuentes=1, workers_tiendas=1)
    instalar_limitador(crear_limitador(CONTEXTO))
    return sorted((procesar_juego(juego, opciones) for juego in juegos), key=lambda r: r["id"])
