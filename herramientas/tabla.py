"""Lectura y escritura de la tabla juegos en Supabase y del respaldo datos/juegos.csv. Escribir necesita SUPABASE_SECRET_KEY en el .env."""

import csv
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scraper import config  # noqa: E402  carga el .env

RUTA_CSV = config.RAIZ / "datos" / "juegos.csv"
COLUMNAS = ["nombre", "plataformas", "fecha_lanzamiento", "precio_sugerido", "url_steam", "url_psstore", "url_xbox",
            "url_eshop", "url_metacritic", "url_hltb", "imagen_url", "activo"]
PLATAFORMAS = ["PC", "PS4", "PS5", "Xbox", "Switch"]


def _conexion(escribir: bool) -> tuple[str, dict]:
    """URL de la tabla y encabezados. Para escribir usa la llave secreta y para leer la que haya."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    llave = os.environ.get("SUPABASE_SECRET_KEY", "") or ("" if escribir else os.environ.get("SUPABASE_KEY", ""))
    if not url or not llave:
        raise RuntimeError("falta SUPABASE_URL o la llave " + ("secreta" if escribir else "") + " en el .env")
    encabezados = {"apikey": llave, "Content-Type": "application/json"}
    if llave.startswith("eyJ"):
        encabezados["Authorization"] = f"Bearer {llave}"
    return f"{url}/rest/v1/juegos", encabezados


def _revisar(respuesta: requests.Response) -> requests.Response:
    """Lanza un error claro si Supabase no respondió bien."""
    if "23505" in respuesta.text:
        raise RuntimeError("ya existe un juego con ese nombre")
    if respuesta.status_code >= 300:
        raise RuntimeError(f"Supabase respondió {respuesta.status_code}: {respuesta.text[:300]}")
    return respuesta


def leer_todos() -> list[dict]:
    """Todos los juegos de Supabase, activos e inactivos, ordenados por id."""
    url, encabezados = _conexion(escribir=False)
    respuesta = requests.get(url, headers=encabezados, params={"select": "*", "order": "id"}, timeout=30)
    return _revisar(respuesta).json()


def corregir(juego: dict) -> dict:
    """Arregla lo que se puede arreglar solo: quita espacios, deja vacío como None y pasa PS Store a la tienda de EE. UU."""
    juego = {clave: (valor.strip() or None) if isinstance(valor, str) else valor for clave, valor in juego.items()}
    if juego.get("url_psstore"):
        juego["url_psstore"] = re.sub(r"store\.playstation\.com/[a-z]{2}-[a-z]{2}/", "store.playstation.com/en-us/", juego["url_psstore"])
    return juego


def problemas(juego: dict) -> list[str]:
    """Lista de cosas que impiden guardar el juego. Vacía si todo está bien."""
    errores = []
    if not juego.get("nombre"):
        errores.append("falta el nombre")
    if not juego.get("plataformas"):
        errores.append("falta al menos una plataforma")
    try:
        if float(juego.get("precio_sugerido") or 0) <= 0:
            errores.append("el precio debe ser mayor que 0")
    except (TypeError, ValueError):
        errores.append("el precio debe ser un número como 59.99")
    if juego.get("fecha_lanzamiento"):
        try:
            date.fromisoformat(str(juego["fecha_lanzamiento"]))
        except ValueError:
            errores.append("la fecha debe ser AAAA-MM-DD")
    if not str(juego.get("url_steam") or "").startswith("https://store.steampowered.com/"):
        errores.append("el enlace de Steam debe empezar con https://store.steampowered.com/")
    if not str(juego.get("url_psstore") or "").startswith("https://store.playstation.com/en-us/"):
        errores.append("el enlace de PS Store debe empezar con https://store.playstation.com/en-us/")
    return errores


def guardar_juego(juego: dict) -> dict:
    """Guarda un juego. Si tiene id lo actualiza y si no lo crea. Devuelve el juego como quedó en Supabase."""
    url, encabezados = _conexion(escribir=True)
    encabezados["Prefer"] = "return=representation"
    datos = {clave: juego.get(clave) for clave in COLUMNAS}
    datos["precio_sugerido"] = float(datos["precio_sugerido"])
    datos["activo"] = bool(juego.get("activo", True))
    if juego.get("id"):
        respuesta = requests.patch(url, headers=encabezados, params={"id": f"eq.{juego['id']}"}, data=json.dumps(datos), timeout=30)
    else:
        respuesta = requests.post(url, headers=encabezados, data=json.dumps(datos), timeout=30)
    return _revisar(respuesta).json()[0]


def subir_varios(juegos: list[dict]) -> int:
    """Sube muchos juegos de 50 en 50. Si un nombre ya existe lo actualiza en vez de repetirlo. Devuelve cuántos subió."""
    url, encabezados = _conexion(escribir=True)
    encabezados["Prefer"] = "resolution=merge-duplicates,return=minimal"
    lista = [{clave: juego.get(clave) for clave in COLUMNAS} for juego in juegos]
    for inicio in range(0, len(lista), 50):
        _revisar(requests.post(url, headers=encabezados, params={"on_conflict": "nombre"},
                               data=json.dumps(lista[inicio:inicio + 50]), timeout=30))
    return len(lista)


def leer_csv(ruta: Path = RUTA_CSV) -> list[dict]:
    """Lee un CSV de juegos. Plataformas separadas por coma pasan a lista y activo pasa a True o False."""
    with open(ruta, encoding="utf-8", newline="") as archivo:
        juegos = []
        for fila in csv.DictReader(archivo):
            juego = corregir(fila)
            juego["plataformas"] = [p.strip() for p in (juego.get("plataformas") or "").split(",") if p.strip()]
            juego["activo"] = str(juego.get("activo") or "true").lower() == "true"
            juegos.append(juego)
    return juegos


def escribir_csv(juegos: list[dict], ruta: Path = RUTA_CSV) -> None:
    """Guarda los juegos como respaldo en CSV con las mismas columnas de la tabla."""
    with open(ruta, "w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS)
        escritor.writeheader()
        for juego in juegos:
            fila = {clave: juego.get(clave) for clave in COLUMNAS}
            fila["plataformas"] = ",".join(juego.get("plataformas") or [])
            fila["activo"] = "true" if juego.get("activo", True) else "false"
            escritor.writerow({clave: "" if valor is None else valor for clave, valor in fila.items()})
