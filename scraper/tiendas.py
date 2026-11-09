"""Tiendas y nivel 3. Una función por tienda que abre la página del juego y devuelve precio actual, precio regular, formato, plataforma y enlace. procesar_tiendas las consulta al mismo tiempo con un hilo por tienda.

Todas leen el HTML de la página (no APIs JSON). Cuando el precio también viene dentro de un <script> de la página se usa como respaldo, que sigue siendo scraping de la misma página.

Para probar contra los sitios reales: python -m scraper.tiendas 5   (los primeros 5 juegos de datos/juegos.csv)
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup

from .red import fuente_segura, obtener_html

# Cookies que Steam guarda después de la pantalla de verificación de edad. Con ellas la página del juego abre directo.
COOKIES_EDAD = {"birthtime": "568022401", "lastagecheckage": "1-0-1988", "mature_content": "1", "wants_mature_content": "1"}
GRATIS = ("free", "free to play", "free-to-play", "gratis")
PRECIO = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)")
SUSCRIPCION = re.compile(r"PlayStation Plus|PS Plus|EA Play|Ubisoft\+|subscri", re.I)  # ofertas que no son precio de compra normal


class SinPrecio(Exception):
    """La página abrió pero no tiene un precio de compra que se pueda leer."""


class PaginaIncompleta(SinPrecio):
    """La página llegó sin el bloque de compra. A veces pasa de forma pasajera y vale la pena pedirla otra vez."""


# ---------- utilidades comunes ----------

def leer_precio(texto: str | None) -> float | None:
    """Convierte "$1,299.99" en 1299.99 y "Free" en 0.0. Devuelve None si el texto no es un precio en dólares, por ejemplo "Included"."""
    if not texto:
        return None
    texto = texto.strip()
    if texto.lower() in GRATIS:
        return 0.0
    encontrado = PRECIO.search(texto)
    return float(encontrado.group(1).replace(",", "")) if encontrado else None


def calcular_oferta(actual: float, regular: float | None, precio_sugerido) -> dict:
    """Indicador de oferta. Un juego está en oferta si el precio actual es menor que el regular que muestra la tienda. Si la tienda no muestra el regular se compara con el precio sugerido del REPO. Descuento = (regular - actual) / regular * 100."""
    if regular is None or regular <= 0:
        regular = float(precio_sugerido) if precio_sugerido not in (None, "") else actual
    en_oferta = actual < regular
    descuento = round((regular - actual) / regular * 100) if en_oferta and regular > 0 else 0
    return {"precio_regular": round(regular, 2), "en_oferta": en_oferta, "descuento_pct": descuento}


def armar_tienda(juego: dict, tienda: str, plataforma: str, url: str, actual: float, regular: float | None) -> dict:
    """Arma el resultado de una tienda con el formato del contrato común. ok lo agrega @fuente_segura."""
    return {"tienda": tienda, "precio_actual": round(actual, 2),
            **calcular_oferta(actual, regular, juego.get("precio_sugerido")),
            "formato": "Digital", "plataforma": plataforma, "url": url}


# ---------- Steam ----------

def _es_bundle(bloque) -> bool:
    """Los bloques de bundle venden varios juegos juntos y no sirven como precio del juego."""
    if bloque.find_parent(class_="dynamic_bundle_description") or "dynamic_bundle_description" in (bloque.get("class") or []):
        return True
    return bool(bloque.select_one('input[name="bundleid"]')) or "bundle" in (bloque.get("id") or "")


def leer_steam(html: str) -> tuple[float, float | None]:
    """Busca el primer bloque de compra que no es bundle ni demo y devuelve (actual, regular). Con descuento el regular es discount_original_price; sin descuento la tienda muestra un solo precio y el regular es el mismo."""
    página = BeautifulSoup(html, "html.parser")
    if página.select_one("#app_agegate, .agegate_birthday_selector"):
        raise SinPrecio("Steam pidió verificación de edad")
    if not página.select_one("#appHubAppName"):
        raise SinPrecio("Steam no mostró la página del juego")

    for bloque in página.select("#game_area_purchase .game_area_purchase_game"):
        if _es_bundle(bloque):
            continue
        final = bloque.select_one(".discount_final_price, .game_purchase_price")
        if not final:
            continue  # demo o bloque sin precio
        actual = leer_precio(final.get_text(strip=True))
        if actual is None:  # texto raro, se usa el atributo en centavos
            con_dato = bloque.select_one("[data-price-final]")
            if not con_dato or not con_dato["data-price-final"].isdigit():
                continue
            actual = int(con_dato["data-price-final"]) / 100
        original = bloque.select_one(".discount_original_price")
        regular = leer_precio(original.get_text(strip=True)) if original else actual
        return actual, regular

    aviso = página.select_one("#purchase_note .notice_box_content")
    raise SinPrecio("no está a la venta en Steam" if aviso else "Steam no muestra precio de compra")


@fuente_segura("steam")
def scrape_steam(juego: dict) -> dict:
    """Lee store.steampowered.com/app/<appid>/ en dólares. Manda las cookies de edad para saltar la verificación."""
    url = juego["url_steam"]
    html = obtener_html("steam", url, params={"cc": "us", "l": "english"}, cookies=COOKIES_EDAD)
    actual, regular = leer_steam(html)
    return armar_tienda(juego, "Steam", "PC", url, actual, regular)


# ---------- PlayStation Store ----------

def _plataforma_ps(página, juego: dict) -> str:
    """PS5 si el juego está para PS5, si no PS4. Primero mira la página y si no la trae usa las plataformas del REPO."""
    campo = página.select_one('[data-qa="gameInfo#releaseInformation#platform-value"]')
    lista = [p.strip() for p in campo.get_text().split(",")] if campo else list(juego.get("plataformas") or [])
    return "PS5" if "PS5" in lista else "PS4" if "PS4" in lista else "PS5"


def _ofertas_html(página) -> list[tuple[float, float | None]]:
    """Lee las ofertas visibles del botón de compra principal (mfeCtaMain#offer0, offer1...). Salta las de suscripción como PS Plus, que llevan un serviceIcon."""
    ofertas = []
    for oferta in página.select('[data-qa^="mfeCtaMain#offer"]'):
        if not re.fullmatch(r"mfeCtaMain#offer\d+", oferta["data-qa"]):
            continue
        info = oferta.select_one('[data-qa$="#discountInfo"]')
        if oferta.select_one('[data-qa*="#serviceIcon#"]') or (info and SUSCRIPCION.search(info.get_text())):
            continue  # precio solo para miembros de PS Plus u otra suscripción
        final = oferta.select_one('[data-qa$="#finalPrice"]')
        actual = leer_precio(final.get_text(strip=True)) if final else None
        if actual is None:
            continue  # "Included", "Unavailable" y parecidos
        original = oferta.select_one('[data-qa$="#originalPrice"]')
        regular = leer_precio(original.get_text(strip=True)) if original else None
        ofertas.append((actual, regular if regular is not None else actual))
    return ofertas


def _ofertas_script(página) -> list[tuple[float, float | None]]:
    """Respaldo: el botón de compra trae sus datos en un <script type="application/json"> cuyo id está en data-initial. Ahí cada precio tiene basePriceValue y discountedValue en centavos."""
    botón = página.select_one('[data-mfe-name="ctaWithPrice"][data-initial]')
    script = página.find("script", id=botón["data-initial"]) if botón else None
    if not script or not script.string:
        return []
    ofertas = []

    def recorrer(nodo):
        if isinstance(nodo, dict):
            precio = nodo.get("price")
            if (isinstance(precio, dict) and precio.get("discountedValue") is not None
                    and not precio.get("isTiedToSubscription") and precio.get("serviceBranding") in (None, ["NONE"])):
                ofertas.append((precio["discountedValue"] / 100, (precio.get("basePriceValue") or 0) / 100 or None))
            for valor in nodo.values():
                recorrer(valor)
        elif isinstance(nodo, list):
            for valor in nodo:
                recorrer(valor)

    recorrer(json.loads(script.string))
    return ofertas


def leer_psstore(html: str, juego: dict | None = None) -> tuple[float, float | None, str]:
    """Devuelve (actual, regular, plataforma) de una página de concepto o de producto de la PS Store."""
    página = BeautifulSoup(html, "html.parser")
    ofertas = _ofertas_html(página) or _ofertas_script(página)
    if not ofertas:
        estado = página.select_one('[data-qa="mfeCtaMain#offer0#finalPrice"]')
        if estado:  # por ejemplo "Announced" o "Unavailable"
            raise SinPrecio(f"PS Store no lo vende: {estado.get_text(strip=True)}")
        raise PaginaIncompleta("PS Store no muestra precio de compra")
    actual, regular = ofertas[0]  # la primera oferta normal es la del juego principal
    return actual, regular, _plataforma_ps(página, juego or {})


@fuente_segura("psstore")
def scrape_psstore(juego: dict) -> dict:
    """Lee la página del juego en store.playstation.com/en-us (concept o product)."""
    url = juego["url_psstore"]
    try:
        actual, regular, plataforma = leer_psstore(obtener_html("psstore", url), juego)
    except PaginaIncompleta:  # un segundo intento, el limitador ya pone la pausa
        actual, regular, plataforma = leer_psstore(obtener_html("psstore", url), juego)
    return armar_tienda(juego, "PlayStation Store", plataforma, url, actual, regular)


# ---------- Xbox Store (opcional, tercera tienda) ----------

def leer_xbox(html: str, id_producto: str) -> tuple[float, float | None, str]:
    """La página de xbox.com trae el estado inicial en window.__PRELOADED_STATE__. Se busca el producto y su precio de compra normal, sin Game Pass. Respaldo: el precio visible del encabezado."""
    marca = re.search(r"window\.__PRELOADED_STATE__\s*=\s*", html)
    if marca:
        estado, _ = json.JSONDecoder().raw_decode(html, marca.end())
        resúmenes = estado.get("core2", {}).get("products", {}).get("productSummaries", {})
        producto = resúmenes.get(id_producto) or resúmenes.get(id_producto.upper())
        if producto:
            plataforma = "Xbox Series X|S" if "XboxSeriesX" in (producto.get("availableOn") or []) else "Xbox One"
            for precio in (producto.get("specificPrices") or {}).get("purchaseable", []):
                if (precio.get("eligibilityInfo") or {}).get("eligibility", "None") == "None" and precio.get("listPrice") is not None:
                    return float(precio["listPrice"]), float(precio.get("msrp") or 0) or None, plataforma

    página = BeautifulSoup(html, "html.parser")
    visible = página.select_one('[class*="ProductDetailsHeader-module__price"]')
    if visible:
        precios = [leer_precio(t) for t in visible.stripped_strings]
        precios = [p for p in precios if p is not None]
        if precios:  # con descuento aparecen el original y el final
            return min(precios), max(precios), "Xbox"
    raise SinPrecio("Xbox Store no muestra precio de compra")


@fuente_segura("xbox")
def scrape_xbox(juego: dict) -> dict:
    """Lee xbox.com/en-US/games/store/<nombre>/<id>. El id es la última parte del enlace."""
    url = juego["url_xbox"]
    id_producto = url.rstrip("/").split("/")[-1].split("?")[0]
    actual, regular, plataforma = leer_xbox(obtener_html("xbox", url), id_producto)
    return armar_tienda(juego, "Xbox Store", plataforma, url, actual, regular)


# ---------- Nivel 3 ----------

def _scrape_eshop(juego: dict) -> dict:
    """Cuarta tienda opcional (Persona 3). Si scraper/eshop.py todavía no existe se marca como error sin detener nada."""
    try:
        from .eshop import scrape_eshop
    except ImportError:
        return {"ok": False, "error": "scraper de eShop no disponible"}
    return scrape_eshop(juego)


# nombre de la tienda, columna del REPO y función. El orden es el mismo en el data.json.
TIENDAS = [
    ("Steam", "url_steam", scrape_steam),
    ("PlayStation Store", "url_psstore", scrape_psstore),
    ("Xbox Store", "url_xbox", scrape_xbox),
    ("Nintendo eShop", "url_eshop", _scrape_eshop),
]


def procesar_tiendas(juego: dict, max_workers: int = 2) -> list[dict]:
    """Nivel 3: consulta al mismo tiempo, con un hilo por tienda, cada tienda que el juego tiene en el REPO. Devuelve un dict por tienda en el orden de TIENDAS. Una tienda que falla queda con ok False y no afecta a las otras."""
    tareas = [(nombre, columna, función) for nombre, columna, función in TIENDAS if juego.get(columna)]
    if not tareas:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(tareas)))) as hilos:
        futuros = [(nombre, columna, hilos.submit(función, juego)) for nombre, columna, función in tareas]
    resultados = []
    for nombre, columna, futuro in futuros:
        try:
            dato = futuro.result()
        except Exception as error:  # no debería pasar porque cada scraper tiene @fuente_segura
            dato = {"ok": False, "error": f"{type(error).__name__}: {error}"[:200]}
        dato.setdefault("tienda", nombre)  # si falló igual se sabe qué tienda era
        dato.setdefault("url", juego.get(columna))  # la web puede enlazar aunque no haya precio
        resultados.append(dato)
    return resultados


# ---------- prueba manual contra los sitios reales ----------

if __name__ == "__main__":
    import csv
    import sys
    import time

    from . import config

    cantidad = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    with open(config.RAIZ / "datos" / "juegos.csv", encoding="utf-8", newline="") as archivo:
        juegos = list(csv.DictReader(archivo))[:cantidad]
    inicio, fallas = time.perf_counter(), 0
    for juego in juegos:
        juego["plataformas"] = (juego.get("plataformas") or "").split(",")
        print(juego["nombre"])
        for tienda in procesar_tiendas(juego, max_workers=4):
            if tienda.get("ok"):
                oferta = f"  -{tienda['descuento_pct']}%" if tienda["en_oferta"] else ""
                print(f"   {tienda['tienda']:<18} {tienda['plataforma']:<6} ${tienda['precio_actual']:>7.2f}  regular ${tienda['precio_regular']:.2f}{oferta}")
            else:
                fallas += 1
                print(f"   {tienda['tienda']:<18} ERROR {tienda['error']}  {tienda.get('url')}")
    print(f"\n{len(juegos)} juegos en {time.perf_counter() - inicio:.1f}s, {fallas} tiendas con error")
