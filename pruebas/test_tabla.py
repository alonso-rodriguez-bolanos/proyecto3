"""Pruebas de las reglas para guardar juegos y del respaldo CSV."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from herramientas import tabla  # noqa: E402

BUENO = {"nombre": "Hades", "plataformas": ["PC", "PS5"], "precio_sugerido": "24.99", "fecha_lanzamiento": "2020-09-17",
         "url_steam": "https://store.steampowered.com/app/1145360/",
         "url_psstore": "https://store.playstation.com/en-us/concept/10002648", "activo": True}


class PruebasTabla(unittest.TestCase):

    def test_juego_correcto_no_tiene_problemas(self):
        self.assertEqual(tabla.problemas(BUENO), [])

    def test_detecta_cada_problema(self):
        malo = {"nombre": "", "plataformas": [], "precio_sugerido": "abc", "fecha_lanzamiento": "08/11/2026",
                "url_steam": "x", "url_psstore": "ENLACE_NUEVO"}
        self.assertEqual(len(tabla.problemas(malo)), 6)

    def test_corrige_region_de_ps_store_y_espacios(self):
        juego = tabla.corregir(dict(BUENO, nombre="  Hades ", url_psstore="https://store.playstation.com/es-cr/concept/1", fecha_lanzamiento=""))
        self.assertEqual(juego["nombre"], "Hades")
        self.assertEqual(juego["url_psstore"], "https://store.playstation.com/en-us/concept/1")
        self.assertIsNone(juego["fecha_lanzamiento"])

    def test_csv_ida_y_vuelta(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "juegos.csv"
            tabla.escribir_csv([BUENO, dict(BUENO, nombre="Otro", activo=False)], ruta)
            leídos = tabla.leer_csv(ruta)
        self.assertEqual(leídos[0]["plataformas"], ["PC", "PS5"])
        self.assertTrue(leídos[0]["activo"])
        self.assertFalse(leídos[1]["activo"])


if __name__ == "__main__":
    unittest.main()
