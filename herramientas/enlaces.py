"""Busca y verifica los enlaces de un juego. Steam: confirma el título y toma la imagen. PS Store: saca el conceptId de la página oficial en playstation.com. Metacritic: arma el enlace y confirma que existe. Solo llena lo que está vacío."""

import difflib
import re
import sys
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scraper.red import ErrorDescarga, obtener_html  # noqa: E402

COOKIES_EDAD = {"birthtime": "568022401", "lastagecheckage": "1-0-1988", "mature_content": "1", "wants_mature_content": "1"}
PARECIDO_MINIMO = 0.75  # debajo de esto se marca para revisar
EDICIONES = re.compile(r"\s*(-\s*)?(the final cut|complete edition|ultimate edition|definitive edition|"
                       r"legendary edition|director's cut|remastered|world of assassination)\s*$", re.I)


def normalizar(texto: str) -> str:
    """Pasa un nombre a minúsculas sin tildes ni símbolos para compararlo."""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", texto.replace("'", "").replace("&", " and ")).strip()


def parecido(a: str, b: str) -> float:
    """Qué tanto se parecen dos nombres de 0 a 1."""
    a, b = normalizar(a), normalizar(b)
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.9
    return difflib.SequenceMatcher(None, a, b).ratio()


def revisar_steam(juego: dict) -> tuple[str, str]:
    """Abre url_steam y confirma que el título coincide. Si no hay enlace o no coincide busca el juego en el buscador de Steam."""
    if juego.get("url_steam"):
        página = BeautifulSoup(obtener_html("steam", juego["url_steam"], cookies=COOKIES_EDAD), "html.parser")
        título = página.select_one("#appHubAppName")
        if título and parecido(título.get_text(strip=True), juego["nombre"]) >= PARECIDO_MINIMO:
            imagen = página.select_one('meta[property="og:image"]')
            if imagen and not juego.get("imagen_url"):
                juego["imagen_url"] = imagen["content"]
            return "OK", título.get_text(strip=True)

    html = obtener_html("steam", "https://store.steampowered.com/search/",
                        params={"term": juego["nombre"], "category1": "998", "cc": "us"})
    filas = [f for f in BeautifulSoup(html, "html.parser").select("a.search_result_row")[:5] if f.select_one(".title")]
    if not filas:
        return "REVISAR", "la búsqueda de Steam no dio resultados"

    mejor = max(filas, key=lambda f: parecido(f.select_one(".title").get_text(strip=True), juego["nombre"]))
    título = mejor.select_one(".title").get_text(strip=True)
    juego["url_steam"] = f"https://store.steampowered.com/app/{mejor['data-ds-appid']}/"
    return ("OK" if parecido(título, juego["nombre"]) >= PARECIDO_MINIMO else "REVISAR"), f"encontrado por búsqueda: {título}"


def buscar_psstore(juego: dict) -> tuple[str, str]:
    """Prueba las direcciones probables del juego en playstation.com hasta encontrar su conceptId y arma el enlace directo a la tienda."""
    if juego.get("url_psstore"):
        return "OK", "ya tenía enlace"

    nombre = re.sub(r"\(.*?\)", "", juego["nombre"]).strip()
    variantes = [nombre, nombre.replace("&", "and"), EDICIONES.sub("", nombre), nombre.split(":")[0]]
    slugs = list(dict.fromkeys(normalizar(v).replace(" ", "-") for v in variantes))  # sin repetidos

    for slug in slugs:
        url = f"https://www.playstation.com/en-us/games/{slug}/"
        try:
            página = BeautifulSoup(obtener_html("psstore", url, intentos=2), "html.parser")
        except ErrorDescarga:
            continue  # esa dirección no existe
        concepto = página.select_one('meta[name="conceptId"]')
        título = página.select_one('meta[name="name"]')
        if concepto and concepto.get("content", "").isdigit():
            juego["url_psstore"] = f"https://store.playstation.com/en-us/concept/{concepto['content']}"
            texto = título["content"] if título else slug
            return ("OK" if parecido(texto, juego["nombre"]) >= PARECIDO_MINIMO else "REVISAR"), f"encontrado: {texto}"
    return "REVISAR", "no se encontró, búscalo a mano en la tienda"


def revisar_metacritic(juego: dict) -> tuple[str, str]:
    """Arma el enlace de Metacritic con el nombre y confirma que la página existe."""
    if juego.get("url_metacritic"):
        return "OK", "ya tenía enlace"
    url = f"https://www.metacritic.com/game/{normalizar(juego['nombre'].replace('&', ' ')).replace(' ', '-')}/"
    try:
        obtener_html("metacritic", url, intentos=2)
    except ErrorDescarga as error:
        return "REVISAR", f"no existe {url} ({error})"
    juego["url_metacritic"] = url
    return "OK", url


def completar(juego: dict) -> list[tuple[str, str, str]]:
    """Revisa los tres sitios de un juego y llena lo que falte. Devuelve una lista de sitio, estado y detalle."""
    resultados = []
    for sitio, función in (("Steam", revisar_steam), ("PS Store", buscar_psstore), ("Metacritic", revisar_metacritic)):
        try:
            estado, detalle = función(juego)
        except ErrorDescarga as error:
            estado, detalle = "REVISAR", f"no se pudo descargar: {error}"
        resultados.append((sitio, estado, detalle))
    return resultados
