"""Benchmark: corre el programa completo con la versión secuencial y con 1, 2, 4, 8 y 16 procesos, 3 repeticiones cada uno, y guarda los tiempos en docs/benchmark/tiempos.csv. Después dibuja los gráficos de tiempo, speedup y eficiencia.

Cada corrida es un `python ejecutar.py ...` aparte, así ninguna aprovecha conexiones o cachés de la anterior. El JSON de cada corrida va a logs/benchmark_data.json para no tocar web/data.json.

Uso:
    python herramientas/benchmark.py                      # scrapers reales, todos los juegos
    python herramientas/benchmark.py --falsos --repo-falso 200   # prueba rápida sin internet
    python herramientas/benchmark.py --solo-graficos      # vuelve a dibujar con el CSV existente
"""

import argparse
import csv
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "docs" / "benchmark"
RUTA_CSV = CARPETA / "tiempos.csv"
METRICAS = RAIZ / "logs" / "metricas.jsonl"
SALIDA_JSON = RAIZ / "logs" / "benchmark_data.json"


def leer_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mide el tiempo con distintos números de procesos")
    parser.add_argument("--workers", default="1,2,4,8,16", help="lista de procesos a medir")
    parser.add_argument("--repeticiones", type=int, default=3)
    parser.add_argument("--falsos", action="store_true", help="usa los scrapers de prueba")
    parser.add_argument("--repo-falso", type=int, default=0, metavar="N", help="N juegos inventados sin Supabase")
    parser.add_argument("--limite", type=int, default=0, metavar="N", help="solo los primeros N juegos")
    parser.add_argument("--sin-limites", action="store_true", help="quita las pausas por sitio")
    parser.add_argument("--solo-graficos", action="store_true", help="no mide, solo dibuja con el CSV")
    return parser.parse_args()


def _ultima_metrica() -> dict:
    """Última línea de logs/metricas.jsonl, que escribe ejecutar.py al terminar."""
    return json.loads(METRICAS.read_text(encoding="utf-8").strip().splitlines()[-1])


def correr(args: argparse.Namespace, workers: int | None) -> dict:
    """Corre ejecutar.py una vez. workers None es la versión secuencial."""
    comando = [sys.executable, str(RAIZ / "ejecutar.py"), "--salida", str(SALIDA_JSON)]
    comando += ["--secuencial"] if workers is None else ["--workers", str(workers)]
    for bandera in ("falsos", "sin_limites"):
        if getattr(args, bandera):
            comando.append("--" + bandera.replace("_", "-"))
    for opción in ("repo_falso", "limite"):
        if getattr(args, opción):
            comando += ["--" + opción.replace("_", "-"), str(getattr(args, opción))]

    inicio = time.perf_counter()
    subprocess.run(comando, cwd=RAIZ, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    total = time.perf_counter() - inicio  # incluye arrancar Python y leer el REPO
    métrica = _ultima_metrica()
    return {"duracion_s": métrica["duracion_s"], "total_s": round(total, 2), "juegos": métrica["juegos"],
            "fallas": sum(métrica["fallas"].values())}


def medir(args: argparse.Namespace) -> None:
    """Corre todas las configuraciones y escribe el CSV."""
    configuraciones = [("secuencial", None)] + [(str(n), int(n)) for n in args.workers.split(",")]
    CARPETA.mkdir(parents=True, exist_ok=True)
    with open(RUTA_CSV, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, ["config", "workers", "repeticion", "duracion_s", "total_s", "juegos", "fallas"])
        escritor.writeheader()
        for repetición in range(1, args.repeticiones + 1):  # se intercalan para repartir el ruido de la red
            for nombre, workers in configuraciones:
                fila = correr(args, workers)
                fila.update(config=nombre, workers=workers or 1, repeticion=repetición)
                escritor.writerow(fila)
                archivo.flush()
                print(f"rep {repetición} {nombre:>10}: {fila['duracion_s']:8.1f} s  ({fila['juegos']} juegos, {fila['fallas']} fallas)")
    (CARPETA / "maquina.json").write_text(json.dumps({
        "procesador": platform.processor(), "nucleos_logicos": os.cpu_count(), "sistema": platform.platform(),
        "python": platform.python_version(), "falsos": args.falsos, "sin_limites": args.sin_limites,
        "fecha": time.strftime("%Y-%m-%d %H:%M")}, indent=1, ensure_ascii=False), encoding="utf-8")


def resumir() -> list[dict]:
    """Promedio y desviación por configuración, más speedup = T secuencial / T paralelo y eficiencia = speedup / procesos."""
    filas = list(csv.DictReader(open(RUTA_CSV, encoding="utf-8")))
    grupos: dict[str, list[float]] = {}
    for fila in filas:
        grupos.setdefault(fila["config"], []).append(float(fila["duracion_s"]))
    base = statistics.mean(grupos["secuencial"])
    resumen = []
    for nombre, tiempos in grupos.items():
        workers = 1 if nombre == "secuencial" else int(nombre)
        promedio = statistics.mean(tiempos)
        speedup = base / promedio
        resumen.append({"config": nombre, "workers": workers, "promedio_s": round(promedio, 2),
                        "desviacion_s": round(statistics.stdev(tiempos), 2) if len(tiempos) > 1 else 0.0,
                        "speedup": round(speedup, 2), "eficiencia": round(speedup / workers, 2)})
    with open(CARPETA / "resumen.csv", "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, list(resumen[0]))
        escritor.writeheader()
        escritor.writerows(resumen)
    return resumen


def graficar(resumen: list[dict]) -> None:
    """Dibuja tiempo.png, speedup.png y eficiencia.png en docs/benchmark."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paralelos = [r for r in resumen if r["config"] != "secuencial"]
    secuencial = next(r for r in resumen if r["config"] == "secuencial")
    x = [r["workers"] for r in paralelos]

    def preparar(título, eje_y):
        figura, ejes = plt.subplots(figsize=(7, 4.2), dpi=130)
        ejes.set_title(título)
        ejes.set_xlabel("Procesos del nivel 1")
        ejes.set_ylabel(eje_y)
        ejes.set_xscale("log", base=2)
        ejes.set_xticks(x, [str(v) for v in x])
        ejes.grid(alpha=0.3)
        return figura, ejes

    figura, ejes = preparar("Tiempo total", "Segundos (promedio de 3)")
    ejes.errorbar(x, [r["promedio_s"] for r in paralelos], yerr=[r["desviacion_s"] for r in paralelos], marker="o", capsize=4, label="Paralelo")
    ejes.axhline(secuencial["promedio_s"], color="gray", linestyle="--", label=f"Secuencial ({secuencial['promedio_s']:.0f} s)")
    ejes.legend()
    figura.tight_layout(); figura.savefig(CARPETA / "tiempo.png"); plt.close(figura)

    figura, ejes = preparar("Speedup = T secuencial / T paralelo", "Speedup")
    ejes.plot(x, [r["speedup"] for r in paralelos], marker="o", label="Medido")
    ejes.plot(x, x, color="gray", linestyle="--", label="Ideal (lineal)")
    ejes.legend()
    figura.tight_layout(); figura.savefig(CARPETA / "speedup.png"); plt.close(figura)

    figura, ejes = preparar("Eficiencia = speedup / procesos", "Eficiencia")
    ejes.plot(x, [r["eficiencia"] for r in paralelos], marker="o", label="Medida")
    ejes.axhline(1, color="gray", linestyle="--", label="Ideal (1)")
    ejes.legend()
    figura.tight_layout(); figura.savefig(CARPETA / "eficiencia.png"); plt.close(figura)


def exportar_web(resumen: list[dict]) -> None:
    """Deja web/rendimiento.json para la pestaña Rendimiento de la página (GitHub Pages solo publica la carpeta web)."""
    filas = list(csv.DictReader(open(RUTA_CSV, encoding="utf-8")))
    ruta_maquina = CARPETA / "maquina.json"
    datos = {
        "maquina": json.loads(ruta_maquina.read_text(encoding="utf-8")) if ruta_maquina.exists() else {},
        "juegos": int(filas[0]["juegos"]) if filas else None,
        "repeticiones": max(int(f["repeticion"]) for f in filas) if filas else 0,
        "resumen": resumen,
        "prueba": False,
    }
    (RAIZ / "web" / "rendimiento.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:
    args = leer_argumentos()
    if not args.solo_graficos:
        medir(args)
    resumen = resumir()
    graficar(resumen)
    exportar_web(resumen)
    print(f"\n{'config':>10} {'promedio':>9} {'speedup':>8} {'eficiencia':>10}")
    for r in resumen:
        print(f"{r['config']:>10} {r['promedio_s']:>8.1f}s {r['speedup']:>8.2f} {r['eficiencia']:>10.2f}")
    print(f"\nGráficos en {CARPETA}")


if __name__ == "__main__":
    main()
