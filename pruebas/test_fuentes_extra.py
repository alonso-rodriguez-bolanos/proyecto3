"""Pruebas de Metacritic, HLTB y guardar_json. No usan internet."""

import contextlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scraper import guardar, hltb, metacritic  # noqa: E402

HTML_LD = '<html><script type="application/ld+json">{"@type":"VideoGame","aggregateRating":{"ratingValue":93,"reviewCount":61}}</script></html>'
HTML_VISIBLE = '<div class="c-siteReviewScore c-siteReviewScore_green"><span>87</span></div>'
HTML_TBD = '<div class="c-siteReviewScore c-siteReviewScore_tbdUser"><span>tbd</span></div>'


class PruebasMetacritic(unittest.TestCase):
    def test_lee_el_score_del_json_ld(self):
        self.assertEqual(metacritic.leer_score(HTML_LD), 93)

    def test_usa_el_circulo_visible_si_no_hay_json_ld(self):
        self.assertEqual(metacritic.leer_score(HTML_VISIBLE), 87)

    def test_tbd_no_es_score(self):
        self.assertIsNone(metacritic.leer_score(HTML_TBD))

    def test_scrape_devuelve_ok(self):
        with mock.patch.object(metacritic, "obtener_html", return_value=HTML_LD):
            self.assertEqual(metacritic.scrape_metacritic({"nombre": "Hades", "url_metacritic": "https://x/"}), {"score": 93, "ok": True})

    def test_sin_enlace_no_lanza(self):
        resultado = metacritic.scrape_metacritic({"nombre": "Hades"})
        self.assertFalse(resultado["ok"])

    def test_error_de_red_no_lanza(self):
        with mock.patch.object(metacritic, "obtener_html", side_effect=TimeoutError("lento")):
            self.assertFalse(metacritic.scrape_metacritic({"nombre": "Hades", "url_metacritic": "https://x/"})["ok"])


def _juego_hltb(nombre, similitud, anio, main=20.0, completo=90.0):
    return SimpleNamespace(game_name=nombre, similarity=similitud, release_world=anio, main_story=main, completionist=completo)


class PruebasHltb(unittest.TestCase):
    def setUp(self):
        parche = mock.patch.object(hltb, "turno", lambda sitio: contextlib.nullcontext())  # sin la pausa del límite por sitio
        parche.start()
        self.addCleanup(parche.stop)

    def test_prefiere_el_anio_del_repo(self):
        hades = _juego_hltb("Hades", 0.9, 2020)
        hades_2 = _juego_hltb("Hades", 0.95, 2025)
        self.assertIs(hltb.elegir([hades_2, hades], 2020), hades)

    def test_descarta_nombres_distintos(self):
        self.assertIsNone(hltb.elegir([_juego_hltb("Shades of Black", 0.4, 2015)], 2020))

    def test_scrape_devuelve_horas(self):
        buscador = mock.Mock()
        buscador.search.return_value = [_juego_hltb("Hades", 1.0, 2020, 23.58, 95.32)]
        with mock.patch("howlongtobeatpy.HowLongToBeat", return_value=buscador):
            resultado = hltb.scrape_hltb({"nombre": "Hades", "fecha_lanzamiento": "2020-09-17"})
        self.assertEqual(resultado, {"horas_main": 23.6, "horas_completo": 95.3, "ok": True})

    def test_juego_no_encontrado(self):
        buscador = mock.Mock()
        buscador.search.return_value = []  # HLTB respondió pero no hay resultados: no se reintenta
        with mock.patch("howlongtobeatpy.HowLongToBeat", return_value=buscador):
            resultado = hltb.scrape_hltb({"nombre": "Nada"})
        self.assertEqual(resultado, {"ok": False, "error": "HLTB no encontró el juego"})
        self.assertEqual(buscador.search.call_count, 1)

    def test_none_se_reintenta_y_luego_funciona(self):
        buscador = mock.Mock()
        buscador.search.side_effect = [None, None, [_juego_hltb("Hades", 1.0, 2020, 23.58, 95.32)]]  # HLTB frenó 2 veces
        with mock.patch("howlongtobeatpy.HowLongToBeat", return_value=buscador), mock.patch.object(hltb, "time") as reloj:
            resultado = hltb.scrape_hltb({"nombre": "Hades", "fecha_lanzamiento": "2020-09-17"})
        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["horas_main"], 23.6)
        self.assertEqual(reloj.sleep.call_count, 2)

    def test_none_siempre_da_error_claro(self):
        buscador = mock.Mock()
        buscador.search.return_value = None
        with mock.patch("howlongtobeatpy.HowLongToBeat", return_value=buscador), mock.patch.object(hltb, "time") as reloj:
            resultado = hltb.scrape_hltb({"nombre": "Hades"})
        self.assertFalse(resultado["ok"])
        self.assertIn("no respondió", resultado["error"])
        self.assertEqual(buscador.search.call_count, hltb.config.INTENTOS_HLTB)
        self.assertEqual(reloj.sleep.call_count, hltb.config.INTENTOS_HLTB - 1)

    def test_reintenta_y_al_final_no_lanza(self):
        buscador = mock.Mock()
        buscador.search.side_effect = ConnectionError("caído")
        with mock.patch("howlongtobeatpy.HowLongToBeat", return_value=buscador), mock.patch.object(hltb, "time") as reloj:
            resultado = hltb.scrape_hltb({"nombre": "Hades"})
        self.assertFalse(resultado["ok"])
        self.assertEqual(buscador.search.call_count, hltb.config.INTENTOS_HLTB)
        self.assertEqual(reloj.sleep.call_count, hltb.config.INTENTOS_HLTB - 1)


STEAM_CON_UPGRADE = """<div id="appHubAppName">DEATH STRANDING DIRECTOR'S CUT</div><div id="game_area_purchase">
<div class="game_area_purchase_game"><h1>Buy DEATH STRANDING DIRECTOR'S CUT UPGRADE</h1><div class="game_purchase_price">$9.99</div></div>
<div class="game_area_purchase_game"><h1>Buy DEATH STRANDING DIRECTOR'S CUT</h1><div class="game_purchase_price">$39.99</div></div></div>"""

PS_CON_TRIAL = """<div data-qa="mfeCtaMain#offer0"><span data-qa="mfeCtaMain#offer0#finalPrice">Free</span><span>Trial</span></div>
<div data-qa="mfeCtaMain#offer1"><span data-qa="mfeCtaMain#offer1#finalPrice">$9.89</span><span data-qa="mfeCtaMain#offer1#originalPrice">$29.99</span></div>"""


class PruebasCorreccionesTiendas(unittest.TestCase):
    """Casos reales que salieron mal en el data.json del 15/11/2026."""

    def test_steam_salta_el_bloque_de_upgrade(self):
        from scraper import tiendas
        self.assertEqual(tiendas.leer_steam(STEAM_CON_UPGRADE), (39.99, 39.99))

    def test_ps_salta_la_prueba_gratis(self):
        from scraper import tiendas
        self.assertEqual(tiendas.leer_psstore(PS_CON_TRIAL)[:2], (9.89, 29.99))

    def test_ps_marca_la_prueba_gratis(self):
        from scraper import tiendas
        self.assertTrue(tiendas.hay_prueba_gratis(PS_CON_TRIAL))
        sin_prueba = PS_CON_TRIAL.split("</div>", 1)[1]
        self.assertFalse(tiendas.hay_prueba_gratis(sin_prueba))
        with mock.patch.object(tiendas, "obtener_html", return_value=PS_CON_TRIAL):
            resultado = tiendas.scrape_psstore({"nombre": "LotF", "url_psstore": "https://x", "precio_sugerido": 59.99})
        self.assertTrue(resultado["prueba_gratis"])
        self.assertEqual(resultado["precio_actual"], 9.89)


def _registro(id_, score=90, mc_ok=True, precio=10.0, tienda_ok=True):
    tienda = {"tienda": "Steam", "ok": True, "precio_actual": precio} if tienda_ok else {"tienda": "Steam", "ok": False, "error": "timeout"}
    return {"id": id_, "nombre": f"J{id_}", "tiendas": [tienda],
            "metacritic": {"ok": True, "score": score} if mc_ok else {"ok": False, "error": "HTTP 503"},
            "hltb": {"ok": True, "horas_main": 10.0}, "ultima_actualizacion": "2026-11-10T14:00:00+00:00"}


class PruebasGuardar(unittest.TestCase):
    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.ruta = Path(self.carpeta.name) / "data.json"

    def tearDown(self):
        self.carpeta.cleanup()

    def leer(self):
        return json.loads(self.ruta.read_text(encoding="utf-8"))

    def test_primera_vez_guarda_todo(self):
        guardar.guardar_json([_registro(1)], self.ruta)
        self.assertEqual(self.leer()[0]["metacritic"]["score"], 90)

    def test_conserva_el_ultimo_dato_bueno_y_marca_el_error(self):
        guardar.guardar_json([_registro(1, score=93)], self.ruta)
        guardar.guardar_json([_registro(1, mc_ok=False, tienda_ok=False)], self.ruta)
        registro = self.leer()[0]
        self.assertEqual(registro["metacritic"]["score"], 93)
        self.assertTrue(registro["metacritic"]["desactualizado"])
        self.assertEqual(registro["metacritic"]["error"], "HTTP 503")
        self.assertEqual(registro["metacritic"]["dato_de"], "2026-11-10T14:00:00+00:00")
        self.assertEqual(registro["tiendas"][0]["precio_actual"], 10.0)
        self.assertTrue(registro["tiendas"][0]["desactualizado"])

    def test_si_la_fuente_vuelve_se_limpia_la_marca(self):
        guardar.guardar_json([_registro(1)], self.ruta)
        guardar.guardar_json([_registro(1, mc_ok=False)], self.ruta)
        guardar.guardar_json([_registro(1, score=88)], self.ruta)
        self.assertEqual(self.leer()[0]["metacritic"], {"ok": True, "score": 88})

    def test_sin_dato_anterior_queda_el_error(self):
        guardar.guardar_json([_registro(1, mc_ok=False)], self.ruta)
        self.assertFalse(self.leer()[0]["metacritic"]["ok"])

    def test_json_anterior_dañado_no_rompe(self):
        self.ruta.write_text("[{\"id\": 1, ", encoding="utf-8")
        guardar.guardar_json([_registro(1)], self.ruta)
        self.assertEqual(len(self.leer()), 1)

    def test_no_deja_temporales(self):
        guardar.guardar_json([_registro(1)], self.ruta)
        self.assertEqual(sorted(p.name for p in Path(self.carpeta.name).iterdir()), ["data.json", "historial.json"])

    def test_si_falla_al_escribir_el_archivo_anterior_queda_intacto(self):
        guardar.guardar_json([_registro(1)], self.ruta)
        antes = self.ruta.read_text(encoding="utf-8")
        with mock.patch.object(guardar.os, "replace", side_effect=OSError("disco lleno")):
            with self.assertRaises(OSError):
                guardar.guardar_json([_registro(1, score=50)], self.ruta)
        self.assertEqual(self.ruta.read_text(encoding="utf-8"), antes)
        self.assertEqual(sorted(p.name for p in Path(self.carpeta.name).iterdir()), ["data.json", "historial.json"])

    def leer_historial(self):
        return json.loads((Path(self.carpeta.name) / "historial.json").read_text(encoding="utf-8"))

    def test_historial_guarda_solo_los_cambios_de_precio(self):
        for precio, fecha in ((10.0, "2026-11-01"), (10.0, "2026-11-02"), (5.0, "2026-11-03")):
            registro = _registro(1, precio=precio)
            registro["ultima_actualizacion"] = fecha
            guardar.guardar_json([registro], self.ruta)
        self.assertEqual(self.leer_historial(), {"1": {"Steam": [["2026-11-01", 10.0], ["2026-11-03", 5.0]]}})

    def test_historial_ignora_fallas_y_datos_conservados(self):
        guardar.guardar_json([_registro(1, precio=10.0)], self.ruta)
        guardar.guardar_json([_registro(1, tienda_ok=False)], self.ruta)  # se conserva el dato viejo marcado como desactualizado
        self.assertEqual(len(self.leer_historial()["1"]["Steam"]), 1)

    def test_historial_dañado_se_reinicia(self):
        (Path(self.carpeta.name) / "historial.json").write_text("{malo", encoding="utf-8")
        guardar.guardar_json([_registro(1)], self.ruta)
        self.assertIn("1", self.leer_historial())

    def test_resultado_vacio_no_pisa_el_archivo(self):
        guardar.guardar_json([_registro(1)], self.ruta)
        with self.assertRaises(ValueError):
            guardar.guardar_json([], self.ruta)
        self.assertEqual(len(self.leer()), 1)


if __name__ == "__main__":
    unittest.main()
