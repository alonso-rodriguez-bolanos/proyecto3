"""Pruebas de los scrapers de tiendas sin internet. El HTML de ejemplo copia la estructura real de cada página, recortada. Se corren con: python -m unittest discover -s pruebas -v"""

import json
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import tiendas  # noqa: E402
from scraper.red import ErrorDescarga  # noqa: E402

JUEGO = {"id": 1, "nombre": "Juego", "precio_sugerido": 59.99, "plataformas": ["PC", "PS5"],
         "url_steam": "https://store.steampowered.com/app/1/", "url_psstore": "https://store.playstation.com/en-us/concept/1"}


# ---------- HTML de ejemplo ----------

def steam(*bloques: str, título: str = "Juego") -> str:
    return f'<div id="appHubAppName">{título}</div><div id="game_area_purchase">{"".join(bloques)}</div>'


STEAM_NORMAL = ('<div class="game_area_purchase_game_wrapper"><div class="game_area_purchase_game"><h1>Buy Juego</h1>'
                '<div class="game_purchase_price price" data-price-final="2499">$24.99</div></div></div>')
STEAM_OFERTA = ('<div class="game_area_purchase_game"><h1>Buy Juego</h1>'
                '<div class="discount_block game_purchase_discount" data-price-final="599" data-discount="90">'
                '<div class="discount_pct">-90%</div><div class="discount_prices">'
                '<div class="discount_original_price">$59.99</div><div class="discount_final_price">$5.99</div></div></div></div>')
STEAM_BUNDLE = ('<div class="game_area_purchase_game_wrapper dynamic_bundle_description"><div class="game_area_purchase_game">'
                '<h1>Buy Juego + DLC BUNDLE</h1><div class="discount_block" data-price-final="6746">'
                '<div class="discount_original_price">$74.96</div><div class="discount_final_price">$67.46</div></div></div></div>')
STEAM_DEMO = '<div class="game_area_purchase_game"><h1>Download Juego Demo</h1><a class="btn_green_steamui">Download</a></div>'
STEAM_GRATIS = ('<div class="game_area_purchase_game"><h1>Play Juego</h1>'
                '<div class="game_purchase_price price" data-price-final="0">Free To Play</div></div>')
STEAM_RETIRADO = ('<div id="appHubAppName">Juego</div><div id="game_area_purchase" class="game_area_purchase">'
                  '<div id="purchase_note"><div class="notice_box_content">Juego is unlisted on the Steam store</div></div></div>')


def ps_oferta(n: int, final: str, original: str | None = None, plus: bool = False, info: str | None = None) -> str:
    partes = [f'<span data-qa="mfeCtaMain#offer{n}#finalPrice">{final}</span>']
    if original:
        partes.append(f'<span data-qa="mfeCtaMain#offer{n}#originalPrice">{original}</span>')
    if plus:
        partes.append(f'<span data-qa="mfeCtaMain#offer{n}#serviceIcon#ps-plus"></span>')
    if info:
        partes.append(f'<span data-qa="mfeCtaMain#offer{n}#discountInfo">{info}</span>')
    return f'<label data-qa="mfeCtaMain#offer{n}">{"".join(partes)}</label>'


def ps(*ofertas: str, plataformas: str = "PS4, PS5", script: dict | None = None) -> str:
    datos = f'<script id="env:abc" type="application/json">{json.dumps(script)}</script>' if script else ""
    return (f'<h1 data-qa="mfe-game-title#name">Juego</h1>'
            f'<div data-mfe-name="ctaWithPrice" data-initial="env:abc"><div data-qa="mfeCtaMain">{"".join(ofertas)}</div></div>'
            f'<dd data-qa="gameInfo#releaseInformation#platform-value">{plataformas}</dd>{datos}')


def precio_script(base: int, final: int, plus: bool = False) -> dict:
    return {"price": {"basePriceValue": base, "discountedValue": final, "isTiedToSubscription": plus,
                      "serviceBranding": ["PS_PLUS"] if plus else ["NONE"]}}


# ---------- pruebas ----------

class PruebasUtilidades(unittest.TestCase):

    def test_leer_precio(self):
        self.assertEqual(tiendas.leer_precio("$1,299.99"), 1299.99)
        self.assertEqual(tiendas.leer_precio(" $5 "), 5.0)
        self.assertEqual(tiendas.leer_precio("Free To Play"), 0.0)
        self.assertIsNone(tiendas.leer_precio("Included"))
        self.assertIsNone(tiendas.leer_precio(None))

    def test_oferta_con_regular_de_la_tienda(self):
        self.assertEqual(tiendas.calcular_oferta(9.99, 24.99, 59.99), {"precio_regular": 24.99, "en_oferta": True, "descuento_pct": 60})

    def test_sin_descuento(self):
        self.assertEqual(tiendas.calcular_oferta(24.99, 24.99, 59.99), {"precio_regular": 24.99, "en_oferta": False, "descuento_pct": 0})

    def test_sin_regular_usa_precio_sugerido(self):
        self.assertEqual(tiendas.calcular_oferta(30.0, None, 60.0), {"precio_regular": 60.0, "en_oferta": True, "descuento_pct": 50})
        self.assertFalse(tiendas.calcular_oferta(70.0, None, 60.0)["en_oferta"])  # más caro que el sugerido no es oferta


class PruebasSteam(unittest.TestCase):

    def test_precio_normal(self):
        self.assertEqual(tiendas.leer_steam(steam(STEAM_NORMAL)), (24.99, 24.99))

    def test_precio_con_descuento(self):
        self.assertEqual(tiendas.leer_steam(steam(STEAM_OFERTA)), (5.99, 59.99))

    def test_salta_demo_y_bundle(self):
        self.assertEqual(tiendas.leer_steam(steam(STEAM_DEMO, STEAM_BUNDLE, STEAM_NORMAL)), (24.99, 24.99))

    def test_gratis(self):
        self.assertEqual(tiendas.leer_steam(steam(STEAM_GRATIS)), (0.0, 0.0))

    def test_retirado_de_la_tienda(self):
        with self.assertRaisesRegex(tiendas.SinPrecio, "no está a la venta"):
            tiendas.leer_steam(STEAM_RETIRADO)

    def test_pantalla_de_edad(self):
        with self.assertRaisesRegex(tiendas.SinPrecio, "edad"):
            tiendas.leer_steam('<div id="app_agegate">Please enter your birth date</div>')

    def test_scrape_steam_manda_cookies_de_edad_y_formato_del_contrato(self):
        with mock.patch.object(tiendas, "obtener_html", return_value=steam(STEAM_OFERTA)) as descarga:
            resultado = tiendas.scrape_steam(JUEGO)
        self.assertEqual(descarga.call_args.kwargs["cookies"], tiendas.COOKIES_EDAD)
        self.assertEqual(descarga.call_args.kwargs["params"]["cc"], "us")
        self.assertEqual(resultado, {"tienda": "Steam", "ok": True, "precio_actual": 5.99, "precio_regular": 59.99,
                                     "formato": "Digital", "plataforma": "PC", "url": JUEGO["url_steam"],
                                     "en_oferta": True, "descuento_pct": 90})


class PruebasPSStore(unittest.TestCase):

    def test_precio_normal_y_plataforma(self):
        self.assertEqual(tiendas.leer_psstore(ps(ps_oferta(0, "$24.99"))), (24.99, 24.99, "PS5"))

    def test_solo_ps4(self):
        self.assertEqual(tiendas.leer_psstore(ps(ps_oferta(0, "$19.99"), plataformas="PS4"))[2], "PS4")

    def test_oferta_normal(self):
        self.assertEqual(tiendas.leer_psstore(ps(ps_oferta(0, "$29.99", "$59.99")))[:2], (29.99, 59.99))

    def test_salta_ps_plus_incluido(self):
        html = ps(ps_oferta(0, "Included", "$59.99", plus=True), ps_oferta(1, "$59.99"))
        self.assertEqual(tiendas.leer_psstore(html)[:2], (59.99, 59.99))

    def test_salta_descuento_solo_para_ps_plus(self):
        html = ps(ps_oferta(0, "$19.99", "$39.99", info="Subscribe to PlayStation Plus to get this discount"), ps_oferta(1, "$39.99"))
        self.assertEqual(tiendas.leer_psstore(html)[:2], (39.99, 39.99))

    def test_respaldo_en_el_script(self):
        script = {"cache": {"A": precio_script(5999, 0, plus=True), "B": precio_script(5999, 1499)}}
        self.assertEqual(tiendas.leer_psstore(ps(script=script))[:2], (14.99, 59.99))

    def test_anunciado_sin_precio(self):
        with self.assertRaisesRegex(tiendas.SinPrecio, "Announced"):
            tiendas.leer_psstore(ps(ps_oferta(0, "Announced")))

    def test_pagina_incompleta_se_pide_otra_vez(self):
        with mock.patch.object(tiendas, "obtener_html", side_effect=["<html></html>", ps(ps_oferta(0, "$9.99"))]) as descarga:
            resultado = tiendas.scrape_psstore(JUEGO)
        self.assertEqual(descarga.call_count, 2)
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["precio_actual"], 9.99)


class PruebasXbox(unittest.TestCase):

    def test_lee_el_estado_inicial_y_salta_game_pass(self):
        estado = {"core2": {"products": {"productSummaries": {"9ABC": {
            "availableOn": ["XboxOne", "XboxSeriesX", "PC"],
            "specificPrices": {"purchaseable": [
                {"listPrice": 19.99, "msrp": 24.99, "eligibilityInfo": {"eligibility": "Remediation", "type": "GamePass"}},
                {"listPrice": 12.49, "msrp": 24.99, "eligibilityInfo": {"eligibility": "None"}}]}}}}}}
        html = f"<script>window.__PRELOADED_STATE__ = {json.dumps(estado)};</script>"
        self.assertEqual(tiendas.leer_xbox(html, "9ABC"), (12.49, 24.99, "Xbox Series X|S"))

    def test_respaldo_en_el_html(self):
        html = '<div class="ProductDetailsHeader-module__price___x"><span>$59.99</span><span>$29.99</span></div>'
        self.assertEqual(tiendas.leer_xbox(html, "9ABC")[:2], (29.99, 59.99))


class PruebasNivel3(unittest.TestCase):

    def test_nunca_lanza_excepciones(self):
        with mock.patch.object(tiendas, "obtener_html", side_effect=ErrorDescarga("timeout")):
            resultado = tiendas.procesar_tiendas(JUEGO)
        self.assertEqual(resultado, [{"tienda": "Steam", "ok": False, "error": "timeout", "url": JUEGO["url_steam"]},
                                     {"tienda": "PlayStation Store", "ok": False, "error": "timeout", "url": JUEGO["url_psstore"]}])

    def test_una_tienda_que_falla_no_afecta_a_la_otra(self):
        def descarga(sitio, url, **_):
            if sitio == "steam":
                raise ErrorDescarga("HTTP 503")
            return ps(ps_oferta(0, "$9.99", "$19.99"))
        with mock.patch.object(tiendas, "obtener_html", side_effect=descarga):
            steam_r, ps_r = tiendas.procesar_tiendas(JUEGO)
        self.assertFalse(steam_r["ok"])
        self.assertTrue(ps_r["ok"])
        self.assertEqual(ps_r["descuento_pct"], 50)

    def test_solo_consulta_tiendas_con_enlace(self):
        juego = dict(JUEGO, url_xbox="https://www.xbox.com/en-US/games/store/juego/9ABC")
        with mock.patch.object(tiendas, "obtener_html", side_effect=ErrorDescarga("x")):
            self.assertEqual([t["tienda"] for t in tiendas.procesar_tiendas(juego, 3)], ["Steam", "PlayStation Store", "Xbox Store"])
            self.assertEqual(tiendas.procesar_tiendas({"nombre": "sin enlaces"}), [])

    def test_las_tiendas_corren_al_mismo_tiempo(self):
        def lenta(sitio, url, **_):
            time.sleep(0.3)
            return steam(STEAM_NORMAL) if sitio == "steam" else ps(ps_oferta(0, "$24.99"))
        with mock.patch.object(tiendas, "obtener_html", side_effect=lenta):
            inicio = time.perf_counter()
            tiendas.procesar_tiendas(JUEGO, max_workers=2)
            con_hilos = time.perf_counter() - inicio
            inicio = time.perf_counter()
            tiendas.procesar_tiendas(JUEGO, max_workers=1)
            sin_hilos = time.perf_counter() - inicio
        self.assertLess(con_hilos, 0.5)
        self.assertGreater(sin_hilos, 0.55)

    def test_el_motor_encuentra_procesar_tiendas(self):
        from scraper import nivel2
        with mock.patch("importlib.import_module", side_effect=lambda nombre: tiendas if nombre == "scraper.tiendas" else mock.Mock()):
            fuentes = nivel2.obtener_fuentes(usar_falsos=False)
        self.assertIs(fuentes["procesar_tiendas"], tiendas.procesar_tiendas)


if __name__ == "__main__":
    unittest.main()
