"""Revisa que cada enlace del REPO lleve al juego correcto y no a otra edición u otro juego.

Abre la página de Steam y de PS Store de cada juego, lee el título que muestra la tienda y lo compara con el nombre del REPO.
Marca para revisar a mano: títulos poco parecidos, ediciones distintas (Deluxe, Gold, Upgrade...), un año entre paréntesis
(por ejemplo "resident evil 4 (2005)" en vez del remake) y precios que no se pudieron leer.

Uso:
    python herramientas/auditar_enlaces.py datos/juegos.csv [datos/lote_listo.csv ...]
Salida: datos/auditoria_enlaces.csv con una fila por problema.
"""

import csv
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from herramientas import enlaces, tabla  # noqa: E402
from scraper import tiendas  # noqa: E402
from scraper.red import ErrorDescarga, obtener_html  # noqa: E402

EDICION = re.compile(r"\b(deluxe|gold|ultimate|premium|digital deluxe|complete|collector|bundle|upgrade|season pass|vault|enhanced)\b", re.I)
ANIO = re.compile(r"\((19|20)\d\d\)")


def _sospechas(nombre: str, título: str) -> list[str]:
    """Motivos para revisar un título de tienda frente al nombre del REPO."""
    if not título:
        return ["la página no muestra título"]
    motivos = []
    if enlaces.parecido(nombre, título) < 0.8:
        motivos.append("título distinto")
    extra = set(m.lower() for m in EDICION.findall(título)) - set(m.lower() for m in EDICION.findall(nombre))
    if extra:
        motivos.append("edición " + "/".join(sorted(extra)))
    if ANIO.search(título) and not ANIO.search(nombre):
        motivos.append("título con año (¿otra versión del juego?)")
    return motivos


def revisar(juego: dict) -> list[dict]:
    problemas = []
    for tienda, columna, sitio, selector, leer in (
            ("Steam", "url_steam", "steam", "#appHubAppName", tiendas.leer_steam),
            ("PS Store", "url_psstore", "psstore", '[data-qa="mfe-game-title#name"]', tiendas.leer_psstore)):
        url = juego.get(columna)
        if not url:
            continue
        try:
            extra = {"params": {"cc": "us", "l": "english"}, "cookies": tiendas.COOKIES_EDAD} if sitio == "steam" else {}
            html = obtener_html(sitio, url, **extra)
        except ErrorDescarga as error:
            problemas.append({"nombre": juego["nombre"], "tienda": tienda, "titulo_tienda": "", "precio": "", "motivo": f"no se pudo abrir: {error}", "url": url})
            continue
        nodo = BeautifulSoup(html, "html.parser").select_one(selector)
        título = nodo.get_text(" ", strip=True) if nodo else ""
        motivos = _sospechas(juego["nombre"], título)
        try:
            precio = leer(html)[:2]
        except Exception as error:  # SinPrecio, PaginaIncompleta
            precio = ""
            motivos.append(f"sin precio: {error}")
        if motivos:
            problemas.append({"nombre": juego["nombre"], "tienda": tienda, "titulo_tienda": título, "precio": precio, "motivo": "; ".join(motivos), "url": url})
    for p in problemas:
        print(f"{p['nombre']:<45} {p['tienda']:<9} «{p['titulo_tienda']}» {p['precio']} → {p['motivo']}", flush=True)
    return problemas


def main() -> None:
    rutas = [Path(r) for r in sys.argv[1:]] or [tabla.RUTA_CSV]
    juegos = [j for ruta in rutas for j in tabla.leer_csv(ruta)]
    print(f"Revisando {len(juegos)} juegos…\n")
    with ThreadPoolExecutor(max_workers=6) as hilos:
        problemas = [p for lista in hilos.map(revisar, juegos) for p in lista]
    salida = tabla.RUTA_CSV.parent / "auditoria_enlaces.csv"
    with open(salida, "w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, ["nombre", "tienda", "titulo_tienda", "precio", "motivo", "url"])
        escritor.writeheader()
        escritor.writerows(problemas)
    print(f"\n{len(problemas)} enlaces para revisar de {len(juegos)} juegos → {salida}")


if __name__ == "__main__":
    main()
