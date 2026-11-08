"""Descargas seguras. Todo scraper debe descargar con obtener_html y poner @fuente_segura encima de su función. Así respeta el límite por sitio, tiene timeout, reintenta y nunca lanza excepciones."""

import functools
import logging
import random
import threading
import time

import requests

from . import config
from .limitador import turno

log = logging.getLogger("scraper.red")
_hilo = threading.local()  # una sesión por hilo


class ErrorDescarga(Exception):
    """La página no se pudo descargar."""


def _sesion() -> requests.Session:
    """Devuelve la sesión HTTP de este hilo. Una sesión reutiliza conexiones pero no se puede compartir entre hilos."""
    if not hasattr(_hilo, "sesion"):
        _hilo.sesion = requests.Session()
        _hilo.sesion.headers.update(config.ENCABEZADOS)
    return _hilo.sesion


def obtener_html(sitio: str, url: str, *, params: dict | None = None, cookies: dict | None = None,
                 encabezados: dict | None = None, intentos: int | None = None) -> str:
    """Descarga una página con el límite del sitio y timeout. Reintenta timeouts y errores pasajeros con espera de 1 2 y 4 s. Un 404 o 403 no se reintenta. Devuelve el HTML o lanza ErrorDescarga."""
    intentos = intentos or config.INTENTOS
    error = "desconocido"
    for intento in range(1, intentos + 1):
        respuesta = None
        try:
            with turno(sitio):
                respuesta = _sesion().get(url, params=params, cookies=cookies, headers=encabezados,
                                          timeout=(config.TIMEOUT_CONEXION_S, config.TIMEOUT_LECTURA_S))
            if respuesta.status_code == 200:
                return respuesta.text
            error = f"HTTP {respuesta.status_code}"
            if respuesta.status_code not in config.CODIGOS_REINTENTABLES:
                raise ErrorDescarga(error)  # reintentar no ayuda
        except requests.Timeout:
            error = "timeout"
        except requests.ConnectionError:
            error = "conexion"
        except requests.RequestException as e:
            error = f"red: {type(e).__name__}"
        if intento < intentos:
            espera = config.ESPERA_BASE_S * 2 ** (intento - 1) + random.uniform(0, config.ESPERA_BASE_S)
            pedida = respuesta.headers.get("Retry-After", "") if respuesta is not None else ""
            if pedida.isdigit():
                espera = max(espera, float(pedida))  # el sitio pidió esperar
            espera = min(espera, config.ESPERA_MAXIMA_S)
            log.warning("%s intento %d/%d falló %s, reintento en %.1fs: %s", sitio, intento, intentos, error, espera, url)
            time.sleep(espera)
    log.error("%s sin respuesta después de %d intentos %s: %s", sitio, intentos, error, url)
    raise ErrorDescarga(error)


def describir_error(error: Exception) -> str:
    """Convierte una excepción en un texto corto como timeout o HTTP 404."""
    if isinstance(error, ErrorDescarga):
        return str(error)
    if isinstance(error, requests.Timeout):
        return "timeout"
    if isinstance(error, requests.ConnectionError):
        return "conexion"
    return f"{type(error).__name__}: {error}"[:200]


def fuente_segura(nombre: str):
    """Decorador para los scrapers. Si la función termina bien agrega ok True. Si falla registra el error y devuelve ok False con el error en vez de lanzar la excepción."""
    def decorador(funcion):
        @functools.wraps(funcion)
        def envoltura(juego: dict, *args, **kwargs):
            try:
                resultado = funcion(juego, *args, **kwargs)
                if isinstance(resultado, dict):
                    resultado.setdefault("ok", True)
                return resultado
            except Exception as e:  # nunca propagar
                texto = describir_error(e)
                log.warning("%s falló para %r: %s", nombre, juego.get("nombre"), texto)
                return {"ok": False, "error": texto}
        return envoltura
    return decorador
