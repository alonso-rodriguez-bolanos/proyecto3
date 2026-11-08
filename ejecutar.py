"""Programa principal. Lee los juegos de Supabase, los procesa en paralelo y guarda web/data.json. Cada corrida anota su tiempo en logs/metricas.jsonl."""

import argparse
import json
import logging
import os
import time
from collections import Counter
from datetime import datetime

from scraper import config
from scraper.falsos import juegos_falsos
from scraper.limitador import crear_limitador
from scraper.nivel1 import CONTEXTO, procesar_repo, procesar_repo_secuencial
from scraper.nivel2 import opciones_por_defecto
from scraper.repo import leer_repo

log = logging.getLogger("scraper")
RUTA_DATA = config.RAIZ / "web" / "data.json"


def leer_argumentos() -> argparse.Namespace:
    """Opciones de la línea de comandos."""
    parser = argparse.ArgumentParser(description="Web scraping multinúcleo de videojuegos")
    parser.add_argument("--workers", type=int, default=config.WORKERS_JUEGOS, help="procesos del nivel 1")
    parser.add_argument("--secuencial", action="store_true", help="todo en 1 proceso y 1 hilo")
    parser.add_argument("--falsos", action="store_true", help="usa los scrapers de prueba")
    parser.add_argument("--repo-falso", type=int, default=0, metavar="N", help="N juegos inventados sin Supabase")
    parser.add_argument("--limite", type=int, default=0, metavar="N", help="solo los primeros N juegos")
    parser.add_argument("--sin-limites", action="store_true", help="quita las pausas por sitio")
    return parser.parse_args()


def configurar_log() -> None:
    """Muestra el log en consola y lo guarda en logs/scraper_AAAAMMDD.log."""
    config.CARPETA_LOGS.mkdir(exist_ok=True)
    formato = logging.Formatter("%(asctime)s | %(levelname)-7s | %(processName)s | %(message)s", "%H:%M:%S")

    consola = logging.StreamHandler()
    archivo = logging.FileHandler(config.CARPETA_LOGS / f"scraper_{datetime.now():%Y%m%d}.log", encoding="utf-8")

    raíz = logging.getLogger()
    for manejador in (consola, archivo):
        manejador.setFormatter(formato)
        raíz.addHandler(manejador)
    raíz.setLevel(logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.WARNING)  # menos ruido


def guardar(resultado: list[dict]) -> None:
    """Usa guardar_json de scraper/guardar.py si existe. Si no, escribe a un temporal y lo renombra para que la web nunca lea un JSON a medias."""
    try:
        from scraper.guardar import guardar_json
    except ImportError:
        guardar_json = None

    if guardar_json:
        guardar_json(resultado, RUTA_DATA)
        return

    RUTA_DATA.parent.mkdir(exist_ok=True)
    temporal = RUTA_DATA.with_suffix(".tmp")
    temporal.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temporal, RUTA_DATA)  # reemplazo atómico


def contar_fallas(resultado: list[dict]) -> dict:
    """Cuenta cuántas veces falló cada fuente."""
    fallas = Counter()
    for registro in resultado:
        for tienda in registro["tiendas"]:
            if not tienda.get("ok", True):
                fallas[tienda.get("tienda")] += 1
        for fuente in ("metacritic", "hltb"):
            if not registro[fuente].get("ok", True):
                fallas[fuente] += 1
    return dict(fallas)


def anotar_metricas(args: argparse.Namespace, resultado: list[dict], duración: float, fallas: dict) -> None:
    """Agrega una línea a logs/metricas.jsonl con el tiempo y las fallas de esta corrida."""
    métricas = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "secuencial": args.secuencial,
        "workers": 1 if args.secuencial else args.workers,
        "falsos": args.falsos,
        "sin_limites": args.sin_limites,
        "juegos": len(resultado),
        "duracion_s": duración,
        "nucleos": os.cpu_count(),
        "fallas": fallas,
    }
    with open(config.CARPETA_LOGS / "metricas.jsonl", "a", encoding="utf-8") as archivo:
        archivo.write(json.dumps(métricas, ensure_ascii=False) + "\n")


def main() -> None:
    """Lee los juegos, los procesa, guarda el data.json y anota las métricas."""
    args = leer_argumentos()
    configurar_log()

    # 1. Juegos
    juegos = juegos_falsos(args.repo_falso) if args.repo_falso else leer_repo()
    if args.limite:
        juegos = juegos[: args.limite]

    # 2. Procesamiento
    opciones = opciones_por_defecto(usar_falsos=args.falsos)
    límites = {sitio: (1000, 0.0) for sitio in config.LIMITES_SITIO} if args.sin_limites else None

    inicio = time.perf_counter()
    if args.secuencial:
        resultado = procesar_repo_secuencial(juegos, opciones)
    else:
        resultado = procesar_repo(juegos, args.workers, opciones, crear_limitador(CONTEXTO, límites))
    duración = round(time.perf_counter() - inicio, 2)

    # 3. Resultado
    guardar(resultado)
    fallas = contar_fallas(resultado)
    anotar_metricas(args, resultado, duración, fallas)
    log.info("listo: %d juegos en %.1fs, fallas %s", len(resultado), duración, fallas or "ninguna")


if __name__ == "__main__":
    main()
