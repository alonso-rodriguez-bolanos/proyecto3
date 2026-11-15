"""Scraper de Metacritic. Abre url_metacritic del REPO y lee el Metascore. El score está en el bloque JSON-LD (aggregateRating.ratingValue) que la página trae dentro de un <script>; si ese bloque cambia se usa el círculo visible del score como respaldo."""

import json
import re

from bs4 import BeautifulSoup

from .red import fuente_segura, obtener_html

PATRON_SCORE_VISIBLE = re.compile(r'c-siteReviewScore[^>]*>\s*<span[^>]*>\s*(\d{1,3})\s*<')


def _score_json_ld(html: str) -> int | None:
    """Busca aggregateRating.ratingValue en los bloques application/ld+json."""
    for bloque in BeautifulSoup(html, "html.parser").find_all("script", type="application/ld+json"):
        try:
            datos = json.loads(bloque.string or "")
        except ValueError:
            continue
        for dato in datos if isinstance(datos, list) else [datos]:
            valor = (dato.get("aggregateRating") or {}).get("ratingValue") if isinstance(dato, dict) else None
            if str(valor).isdigit():
                return int(valor)
    return None


def leer_score(html: str) -> int | None:
    """Devuelve el Metascore de la página como entero de 0 a 100, o None si todavía no tiene (tbd)."""
    score = _score_json_ld(html)
    if score is None:
        encontrados = PATRON_SCORE_VISIBLE.findall(html)
        score = int(encontrados[0]) if encontrados else None
    return score if score is not None and 0 <= score <= 100 else None


@fuente_segura("metacritic")
def scrape_metacritic(juego: dict) -> dict:
    """Devuelve {"score": 93}. Si el juego no tiene enlace o la página no muestra score devuelve ok False sin lanzar excepciones."""
    url = juego.get("url_metacritic")
    if not url:
        return {"ok": False, "error": "sin enlace de Metacritic en el REPO"}
    score = leer_score(obtener_html("metacritic", url))
    if score is None:
        return {"ok": False, "error": "Metacritic no muestra score"}
    return {"score": score}


if __name__ == "__main__":
    import csv
    import sys
    from pathlib import Path

    csv_juegos = Path(__file__).resolve().parent.parent / "datos" / "juegos.csv"
    for fila in list(csv.DictReader(open(csv_juegos, encoding="utf-8")))[: int(sys.argv[1]) if len(sys.argv) > 1 else 5]:
        print(fila["nombre"], scrape_metacritic(fila))
