"""Guardado del data.json. Dos garantías: (1) si una fuente falló en esta corrida se conserva el último dato bueno del data.json anterior y se marca el error, y (2) el archivo se escribe a un temporal y se renombra, así la web nunca lee un JSON a medias."""

import json
import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger("scraper.guardar")


def _leer_anterior(ruta: Path) -> dict[int, dict]:
    """Registros del data.json anterior por id. Si no existe o está dañado devuelve {} (no hay nada que conservar)."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        return {r["id"]: r for r in datos}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def _conservar(nuevo: dict, anterior: dict | None, fecha_anterior: str | None) -> dict:
    """Si la fuente nueva falló y la anterior estaba bien, devuelve el dato anterior marcado como desactualizado con el error de hoy. En cualquier otro caso devuelve el dato nuevo."""
    if nuevo.get("ok", True) or not anterior or not anterior.get("ok", True):
        return nuevo
    conservado = dict(anterior)
    conservado["ok"] = True
    conservado["desactualizado"] = True  # la web lo muestra como dato viejo
    conservado["error"] = nuevo.get("error", "error")
    conservado.setdefault("dato_de", fecha_anterior)  # de cuándo es realmente el dato
    return conservado


def combinar(resultado: list[dict], anterior: dict[int, dict]) -> tuple[list[dict], int]:
    """Devuelve los registros nuevos con los datos buenos anteriores en las fuentes que fallaron, y cuántas fuentes se conservaron."""
    conservadas = 0
    salida = []
    for registro in resultado:
        viejo = anterior.get(registro["id"])
        if viejo:
            fecha = viejo.get("ultima_actualizacion")
            registro = dict(registro)
            for fuente in ("metacritic", "hltb"):
                nuevo = _conservar(registro[fuente], viejo.get(fuente), fecha)
                conservadas += nuevo is not registro[fuente]
                registro[fuente] = nuevo
            viejas = {t.get("tienda"): t for t in viejo.get("tiendas", [])}
            tiendas = []
            for tienda in registro["tiendas"]:
                nuevo = _conservar(tienda, viejas.get(tienda.get("tienda")), fecha)
                conservadas += nuevo is not tienda
                tiendas.append(nuevo)
            registro["tiendas"] = tiendas
        salida.append(registro)
    return salida, conservadas


def guardar_json(resultado: list[dict], ruta) -> None:
    """Guarda la lista de registros en ruta. Conserva el último dato bueno de cada fuente que falló y escribe de forma atómica (temporal en la misma carpeta + os.replace)."""
    ruta = Path(ruta)
    if not resultado:
        raise ValueError("no se guarda un resultado vacío: se conserva el data.json anterior")
    final, conservadas = combinar(resultado, _leer_anterior(ruta))
    if conservadas:
        log.warning("%d fuentes fallaron y se conservó su último dato bueno", conservadas)
    escribir_atomico(final, ruta)
    try:  # el historial es un extra: si falla, el data.json ya quedó bien guardado
        actualizar_historial(resultado, ruta.with_name("historial.json"))
    except Exception as error:
        log.error("no se pudo actualizar el historial de precios: %s", error)


def escribir_atomico(datos, ruta: Path, indent: int | None = 1) -> None:
    """Escribe datos como JSON en un temporal de la misma carpeta, lo fuerza a disco y lo renombra encima de ruta (os.replace es atómico)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporal = tempfile.mkstemp(dir=ruta.parent, prefix=ruta.name + ".", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":"))
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, ruta)
    except BaseException:
        if os.path.exists(temporal):
            os.remove(temporal)
        raise


def actualizar_historial(resultado: list[dict], ruta: Path, maximo_puntos: int = 500) -> dict:
    """Agrega los precios de esta corrida a historial.json: {"id": {"Steam": [[fecha, precio], ...], ...}}. Solo guarda un punto cuando el precio cambia, así el archivo crece poco aunque el cron corra dos veces al día. Ignora tiendas que fallaron o datos conservados de una corrida anterior."""
    try:
        historial = json.loads(ruta.read_text(encoding="utf-8"))
        if not isinstance(historial, dict):
            historial = {}
    except (OSError, ValueError):
        historial = {}

    for registro in resultado:
        fecha = registro.get("ultima_actualizacion")
        juego = historial.setdefault(str(registro["id"]), {})
        for tienda in registro.get("tiendas", []):
            precio = tienda.get("precio_actual")
            if not tienda.get("ok") or tienda.get("desactualizado") or not isinstance(precio, (int, float)):
                continue
            puntos = juego.setdefault(tienda["tienda"], [])
            if puntos and puntos[-1][1] == precio:
                continue  # mismo precio que la última vez
            puntos.append([fecha, precio])
            del puntos[:-maximo_puntos]
    escribir_atomico(historial, ruta, indent=None)
    return historial
