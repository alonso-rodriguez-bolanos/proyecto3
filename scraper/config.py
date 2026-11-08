"""Valores ajustables del programa. Cualquiera se puede cambiar desde el archivo .env sin tocar el código."""

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent  # carpeta del proyecto
CARPETA_LOGS = RAIZ / "logs"


def cargar_env(ruta: Path = RAIZ / ".env") -> None:
    """Lee el archivo .env y guarda cada NOMBRE=valor como variable de entorno. Ignora líneas vacías y comentarios. No pisa variables que ya existen, así los Secrets de GitHub tienen prioridad."""
    if not ruta.exists():
        return
    for línea in ruta.read_text(encoding="utf-8").splitlines():
        línea = línea.strip()
        if not línea or línea.startswith("#") or "=" not in línea:
            continue
        nombre, valor = línea.split("=", 1)  # corta solo en el primer igual
        os.environ.setdefault(nombre.strip(), valor.strip().strip('"').strip("'"))


cargar_env()  # se lee al importar para que todos los procesos vean lo mismo


def _num(nombre: str, defecto: float) -> float:
    """Lee un número del entorno. Si no existe o no es número devuelve el valor por defecto."""
    try:
        return float(os.environ.get(nombre, defecto))
    except ValueError:
        return defecto


# Red
TIMEOUT_CONEXION_S = _num("TIMEOUT_CONEXION_S", 5)  # tiempo para conectar
TIMEOUT_LECTURA_S = _num("TIMEOUT_LECTURA_S", 20)  # tiempo para recibir la página
INTENTOS = int(_num("INTENTOS", 3))  # intentos por solicitud
ESPERA_BASE_S = _num("ESPERA_BASE_S", 1)  # espera entre intentos 1 2 4 s
ESPERA_MAXIMA_S = 30  # tope de espera entre intentos
CODIGOS_REINTENTABLES = {408, 425, 429, 500, 502, 503, 504}  # errores pasajeros
ENCABEZADOS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# Límite por sitio: (solicitudes a la vez en todo el programa, pausa mínima entre solicitudes en segundos)
LIMITES_SITIO = {
    "steam": (int(_num("LIM_STEAM", 4)), _num("PAUSA_STEAM", 0.3)),
    "psstore": (int(_num("LIM_PSSTORE", 3)), _num("PAUSA_PSSTORE", 0.5)),
    "metacritic": (int(_num("LIM_METACRITIC", 3)), _num("PAUSA_METACRITIC", 0.5)),
    "hltb": (int(_num("LIM_HLTB", 3)), _num("PAUSA_HLTB", 0.5)),
    "supabase": (2, 0.0),
    "otro": (2, 1.0),  # cualquier sitio que no esté en la lista
}

# Paralelismo
WORKERS_JUEGOS = int(_num("WORKERS_JUEGOS", os.cpu_count() or 4))  # nivel 1 procesos
WORKERS_FUENTES = int(_num("WORKERS_FUENTES", 3))  # nivel 2 hilos
WORKERS_TIENDAS = int(_num("WORKERS_TIENDAS", 2))  # nivel 3 hilos
TIMEOUT_FUENTE_S = _num("TIMEOUT_FUENTE_S", 180)  # tope para que un juego termine
