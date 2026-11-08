"""Pruebas automáticas del motor. Se corren con: python -m unittest discover -s pruebas -v"""

import json
import multiprocessing
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import config, nivel2, repo  # noqa: E402
from scraper.falsos import juegos_falsos  # noqa: E402
from scraper.limitador import crear_limitador, instalar_limitador, turno  # noqa: E402
from scraper.nivel1 import CONTEXTO, procesar_repo, procesar_repo_secuencial  # noqa: E402
from scraper.red import ErrorDescarga, fuente_segura, obtener_html  # noqa: E402

CLAVES_REGISTRO = {"id", "nombre", "imagen", "plataformas", "fecha_lanzamiento", "precio_sugerido",
                   "tiendas", "metacritic", "hltb", "ultima_actualizacion"}


# ---------- utilidades para las pruebas ----------

def _hijo_que_pide_turnos(limitador: dict, cola, veces: int) -> None:
    """Proceso hijo que pide varios turnos y anota a qué hora los obtuvo."""
    instalar_limitador(limitador)
    for _ in range(veces):
        with turno("prueba"):
            cola.put(time.time())


class _Servidor:
    """Servidor HTTP local que responde según una lista de respuestas programadas."""

    def __init__(self, respuestas: list[tuple[int, str]]):
        self.respuestas = list(respuestas)
        self.pedidos = []
        dueño = self

        class Manejador(BaseHTTPRequestHandler):
            def do_GET(self):
                dueño.pedidos.append(self.path)
                código, cuerpo = dueño.respuestas.pop(0) if len(dueño.respuestas) > 1 else dueño.respuestas[0]
                self.send_response(código)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(cuerpo.encode())

            def log_message(self, *args):
                pass

        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        self.url = f"http://127.0.0.1:{self.servidor.server_port}"
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    def cerrar(self):
        self.servidor.shutdown()
        self.servidor.server_close()


# ---------- limitador ----------

class PruebasLimitador(unittest.TestCase):

    def test_pausa_se_respeta_entre_procesos(self):
        """Tres procesos distintos nunca entran al mismo sitio con menos de 0.2 s de diferencia."""
        limitador = crear_limitador(CONTEXTO, {"prueba": (10, 0.2), "otro": (1, 0)})
        cola = CONTEXTO.Queue()
        procesos = [CONTEXTO.Process(target=_hijo_que_pide_turnos, args=(limitador, cola, 3))
                    for _ in range(3)]
        for p in procesos:
            p.start()
        horas = sorted(cola.get(timeout=20) for _ in range(9))
        for p in procesos:
            p.join()
        diferencias = [b - a for a, b in zip(horas, horas[1:])]
        self.assertGreaterEqual(min(diferencias), 0.19, diferencias)

    def test_semaforo_limita_solicitudes_a_la_vez(self):
        """Con límite 2 nunca hay más de 2 hilos dentro del sitio."""
        instalar_limitador(crear_limitador(CONTEXTO, {"prueba": (2, 0.0), "otro": (1, 0)}))
        dentro, máximo, candado = 0, 0, threading.Lock()

        def trabajo():
            nonlocal dentro, máximo
            with turno("prueba"):
                with candado:
                    dentro += 1
                    máximo = max(máximo, dentro)
                time.sleep(0.2)
                with candado:
                    dentro -= 1

        hilos = [threading.Thread(target=trabajo) for _ in range(6)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        self.assertEqual(máximo, 2)


# ---------- red ----------

class PruebasRed(unittest.TestCase):

    def setUp(self):
        instalar_limitador(crear_limitador(CONTEXTO, {"prueba": (10, 0.0), "otro": (10, 0.0)}))
        self.espera_original = config.ESPERA_BASE_S
        config.ESPERA_BASE_S = 0.01  # reintentos rápidos en las pruebas

    def tearDown(self):
        config.ESPERA_BASE_S = self.espera_original

    def test_reintenta_errores_pasajeros(self):
        servidor = _Servidor([(503, "caído"), (503, "caído"), (200, "<html>bien</html>")])
        try:
            texto = obtener_html("prueba", servidor.url + "/juego")
        finally:
            servidor.cerrar()
        self.assertEqual(texto, "<html>bien</html>")
        self.assertEqual(len(servidor.pedidos), 3)

    def test_no_reintenta_404(self):
        servidor = _Servidor([(404, "no existe")])
        try:
            with self.assertRaises(ErrorDescarga) as contexto:
                obtener_html("prueba", servidor.url + "/nada")
        finally:
            servidor.cerrar()
        self.assertEqual(str(contexto.exception), "HTTP 404")
        self.assertEqual(len(servidor.pedidos), 1)

    def test_conexion_rechazada_da_error_y_no_excepcion_en_fuente(self):
        @fuente_segura("prueba")
        def scrape_roto(juego):
            return {"precio": obtener_html("prueba", "http://127.0.0.1:9/")}  # puerto cerrado

        resultado = scrape_roto({"nombre": "X"})
        self.assertEqual(resultado, {"ok": False, "error": "conexion"})


# ---------- nivel 2 ----------

class PruebasNivel2(unittest.TestCase):

    def setUp(self):
        instalar_limitador(crear_limitador(CONTEXTO, {s: (100, 0.0) for s in config.LIMITES_SITIO}))

    def test_una_fuente_que_explota_no_tumba_el_juego(self):
        def explota(juego):
            raise ValueError("cambió el HTML")

        fuentes = {
            "procesar_tiendas": lambda juego, n: [{"tienda": "Steam", "ok": True, "precio_actual": 5.0}],
            "scrape_metacritic": explota,
            "scrape_hltb": lambda juego: {"ok": True, "horas_main": 10.0, "horas_completo": 20.0},
        }
        juego = juegos_falsos(1)[0]
        with mock.patch.object(nivel2, "obtener_fuentes", return_value=fuentes):
            registro = nivel2.procesar_juego(juego, nivel2.opciones_por_defecto())
        self.assertEqual(set(registro), CLAVES_REGISTRO)
        self.assertFalse(registro["metacritic"]["ok"])
        self.assertIn("cambió el HTML", registro["metacritic"]["error"])
        self.assertTrue(registro["hltb"]["ok"])

    def test_timeout_global_de_una_fuente(self):
        fuentes = {
            "procesar_tiendas": lambda juego, n: [],
            "scrape_metacritic": lambda juego: time.sleep(3) or {"score": 1},
            "scrape_hltb": lambda juego: {"horas_main": 1.0},
        }
        juego = juegos_falsos(1)[0]
        inicio = time.perf_counter()
        with mock.patch.object(nivel2, "obtener_fuentes", return_value=fuentes):
            registro = nivel2.procesar_juego(juego, nivel2.opciones_por_defecto(timeout_fuente_s=0.5))
        self.assertLess(time.perf_counter() - inicio, 2)
        self.assertEqual(registro["metacritic"], {"ok": False, "error": "timeout global"})

    def test_si_procesar_tiendas_falla_completo_cada_tienda_queda_en_error(self):
        fuentes = {
            "procesar_tiendas": lambda juego, n: 1 / 0,
            "scrape_metacritic": lambda juego: {"score": 1},
            "scrape_hltb": lambda juego: {"horas_main": 1.0},
        }
        juego = juegos_falsos(1)[0]
        with mock.patch.object(nivel2, "obtener_fuentes", return_value=fuentes):
            registro = nivel2.procesar_juego(juego)
        self.assertEqual([t["tienda"] for t in registro["tiendas"]], ["Steam", "PlayStation Store"])
        self.assertTrue(all(not t["ok"] for t in registro["tiendas"]))


# ---------- nivel 1 ----------

class PruebasNivel1(unittest.TestCase):

    def test_procesar_repo_con_falsos(self):
        juegos = juegos_falsos(8)
        limitador = crear_limitador(CONTEXTO, {s: (100, 0.0) for s in config.LIMITES_SITIO})
        with mock.patch.dict("os.environ", {"DURACION_FALSO_S": "0.2"}):
            resultado = procesar_repo(juegos, 4, nivel2.opciones_por_defecto(usar_falsos=True), limitador)
        self.assertEqual([r["id"] for r in resultado], list(range(1, 9)))
        for registro in resultado:
            self.assertEqual(set(registro), CLAVES_REGISTRO)
            self.assertEqual(len(registro["tiendas"]), 2)
            self.assertTrue(registro["metacritic"]["ok"])

    def test_secuencial_da_el_mismo_formato(self):
        juegos = juegos_falsos(2)
        with mock.patch("scraper.falsos.DURACION_S", 0.05):
            resultado = procesar_repo_secuencial(juegos, nivel2.opciones_por_defecto(usar_falsos=True))
        self.assertEqual(len(resultado), 2)
        self.assertEqual(set(resultado[0]), CLAVES_REGISTRO)


# ---------- REPO ----------

class PruebasRepo(unittest.TestCase):

    def setUp(self):
        instalar_limitador(crear_limitador(CONTEXTO, {s: (10, 0.0) for s in config.LIMITES_SITIO}))
        self.carpeta = tempfile.TemporaryDirectory()
        self.cache_original = repo.RUTA_CACHE
        repo.RUTA_CACHE = Path(self.carpeta.name) / "repo_cache.json"
        config.ESPERA_BASE_S, self.espera_original = 0.01, config.ESPERA_BASE_S

    def tearDown(self):
        repo.RUTA_CACHE = self.cache_original
        config.ESPERA_BASE_S = self.espera_original
        self.carpeta.cleanup()

    def test_lee_filas_validas_y_salta_incompletas(self):
        filas = [
            {"id": 2, "nombre": "B", "plataformas": ["PC"], "precio_sugerido": 10,
             "url_steam": "s", "url_psstore": "p", "activo": True},
            {"id": 1, "nombre": "Sin enlace PS", "plataformas": ["PC"], "precio_sugerido": 10,
             "url_steam": "s", "url_psstore": None, "activo": True},
        ]
        servidor = _Servidor([(200, json.dumps(filas))])
        try:
            with mock.patch.dict("os.environ", {"SUPABASE_URL": servidor.url, "SUPABASE_KEY": "llave"}):
                juegos = repo.leer_repo()
        finally:
            servidor.cerrar()
        self.assertEqual([j["nombre"] for j in juegos], ["B"])
        self.assertIn("activo=eq.true", servidor.pedidos[0])
        self.assertTrue(repo.RUTA_CACHE.exists())

    def test_si_supabase_cae_usa_la_copia_local(self):
        repo.RUTA_CACHE.write_text(json.dumps([
            {"id": 1, "nombre": "Guardado", "plataformas": ["PC"], "precio_sugerido": 5,
             "url_steam": "s", "url_psstore": "p", "activo": True}]), encoding="utf-8")
        with mock.patch.dict("os.environ", {"SUPABASE_URL": "http://127.0.0.1:9", "SUPABASE_KEY": "x"}):
            juegos = repo.leer_repo()
        self.assertEqual(juegos[0]["nombre"], "Guardado")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    unittest.main()
