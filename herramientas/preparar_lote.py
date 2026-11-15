"""Prepara un lote de juegos nuevos para el REPO a partir de una lista con solo nombre y plataformas.

Para cada juego busca los enlaces con enlaces.completar (Steam, PS Store, Metacritic), el enlace de HLTB, la imagen,
el precio sugerido (precio regular de Steam, o el de PS Store si Steam no lo muestra) y la fecha de lanzamiento de Steam.
No escribe en Supabase: deja un CSV listo para el botón "Importar CSV" del gestor y otro con los que hay que revisar a mano.

Uso:
    python herramientas/preparar_lote.py datos/candidatos_persona3.csv
Salida:
    datos/lote_listo.csv     juegos que pasan tabla.problemas y cuyo Steam y PS Store salieron OK
    datos/lote_revisar.csv   el resto, con el motivo en la columna "revisar"
"""

import csv
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from herramientas import enlaces, tabla  # noqa: E402
from scraper import hltb, tiendas  # noqa: E402
from scraper.red import ErrorDescarga, obtener_html  # noqa: E402

CARPETA = tabla.RUTA_CSV.parent
FORMATOS_FECHA = ("%b %d, %Y", "%d %b, %Y", "%B %d, %Y", "%d %B, %Y")


def fecha_steam(url: str) -> str | None:
    """Fecha de lanzamiento de la página de Steam en formato AAAA-MM-DD, o None."""
    html = obtener_html("steam", url, params={"l": "english", "cc": "us"}, cookies=enlaces.COOKIES_EDAD)
    nodo = BeautifulSoup(html, "html.parser").select_one(".release_date .date")
    texto = nodo.get_text(strip=True) if nodo else ""
    for formato in FORMATOS_FECHA:
        try:
            return datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            pass
    return None


def preparar(fila: dict) -> dict:
    """Completa un juego. Agrega la columna revisar con lo que falló (vacía si todo salió bien)."""
    juego = {"nombre": fila["nombre"].strip(), "plataformas": [p.strip() for p in fila["plataformas"].split(",")], "activo": True}
    revisar = []
    for sitio, estado, detalle in enlaces.completar(juego):
        if estado != "OK" and sitio != "Metacritic":
            revisar.append(f"{sitio}: {detalle}")
        elif estado != "OK":
            juego["url_metacritic"] = None  # opcional

    try:
        if juego.get("url_steam"):
            juego["fecha_lanzamiento"] = fecha_steam(juego["url_steam"])
    except ErrorDescarga as error:
        revisar.append(f"fecha: {error}")

    for función in (tiendas.scrape_steam, tiendas.scrape_psstore):
        if juego.get("url_steam") and juego.get("url_psstore") and not juego.get("precio_sugerido"):
            dato = función(juego)
            if dato.get("ok") and dato.get("precio_regular"):
                juego["precio_sugerido"] = dato["precio_regular"]

    try:  # el enlace de HLTB es opcional: si falta, el scraper busca por nombre
        elegido = hltb.buscar(juego)
        if elegido:
            juego["url_hltb"] = elegido.game_web_link
    except Exception:
        pass

    revisar += tabla.problemas(juego)
    juego["revisar"] = "; ".join(dict.fromkeys(revisar))
    print(("OK      " if not juego["revisar"] else "REVISAR ") + juego["nombre"] + ("" if not juego["revisar"] else "  → " + juego["revisar"]), flush=True)
    return juego


def escribir(juegos: list[dict], ruta: Path, con_motivo: bool) -> None:
    columnas = tabla.COLUMNAS + (["revisar"] if con_motivo else [])
    with open(ruta, "w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas, extrasaction="ignore")
        escritor.writeheader()
        for juego in juegos:
            fila = {c: juego.get(c) for c in columnas}
            fila["plataformas"] = ",".join(juego.get("plataformas") or [])
            fila["activo"] = "true"
            escritor.writerow({c: "" if v is None else v for c, v in fila.items()})


def main() -> None:
    entrada = Path(sys.argv[1] if len(sys.argv) > 1 else CARPETA / "candidatos_persona3.csv")
    existentes = {enlaces.normalizar(j["nombre"]) for j in tabla.leer_csv()} if tabla.RUTA_CSV.exists() else set()
    filas = [f for f in csv.DictReader(open(entrada, encoding="utf-8")) if enlaces.normalizar(f["nombre"]) not in existentes]
    print(f"{len(filas)} juegos nuevos para preparar\n")

    with ThreadPoolExecutor(max_workers=6) as hilos:  # el límite por sitio de red.py evita saturar a cada sitio
        juegos = list(hilos.map(preparar, filas))

    vistos, listos, revisar = set(), [], []
    for juego in juegos:
        clave = juego.get("url_steam")
        if clave in vistos:
            juego["revisar"] = (juego["revisar"] + "; " if juego["revisar"] else "") + "enlace de Steam repetido en el lote"
        vistos.add(clave)
        (revisar if juego["revisar"] else listos).append(juego)

    escribir(listos, CARPETA / "lote_listo.csv", con_motivo=False)
    escribir(revisar, CARPETA / "lote_revisar.csv", con_motivo=True)
    print(f"\n{len(listos)} listos en datos/lote_listo.csv, {len(revisar)} para revisar en datos/lote_revisar.csv")


if __name__ == "__main__":
    main()
