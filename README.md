# Web scraping multinúcleo de ofertas de videojuegos

Lee la lista de juegos de Supabase, consulta precios, Metacritic y How Long To Beat en paralelo y genera `web/data.json` para la página web.

## Instalar

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.ejemplo .env
```

Después se llenan las llaves de Supabase en el `.env`. Las llaves se piden por privado y el `.env` nunca se sube a GitHub. Si `python gestor.py` dice que falta tkinter, se instala con `brew install python-tk@3.13` en Mac.

## Correr

```
python gestor.py                       # ventana para ver y editar los juegos
python ejecutar.py                     # con los scrapers reales
python ejecutar.py --falsos            # con los scrapers de prueba
python ejecutar.py --workers 8         # cantidad de procesos
python ejecutar.py --secuencial        # versión de referencia
python -m scraper.tiendas 5            # prueba las tiendas reales con los primeros 5 juegos del CSV
python -m unittest discover -s pruebas # pruebas
```

## Estructura

| Carpeta | Contenido |
|---|---|
| `ejecutar.py` | Programa principal |
| `gestor.py` | Ventana para administrar los juegos de Supabase |
| `scraper/` | Motor paralelo y scrapers |
| `herramientas/` | Lógica que usa el gestor: tabla de Supabase y búsqueda de enlaces |
| `datos/juegos.csv` | Respaldo de los juegos, se actualiza solo al abrir el gestor |
| `sql/` | Creación de la tabla |
| `pruebas/` | Pruebas automáticas |
| `web/` | Página web y el `data.json` que genera `ejecutar.py` |

## Reglas de la tabla de juegos

Cada juego necesita enlace de Steam y de PlayStation Store de la tienda de EE. UU. (`/en-us/`) y su nombre no se puede repetir. Para sacar un juego se desmarca Activo en el gestor en vez de borrarlo.

## Agregar un scraper

El motor busca estas funciones dentro de `scraper/`:

| Archivo | Función |
|---|---|
| `tiendas.py` | `procesar_tiendas(juego, max_workers)` devuelve una lista con un dict por tienda |
| `metacritic.py` | `scrape_metacritic(juego)` devuelve `{"score": 93}` |
| `hltb.py` | `scrape_hltb(juego)` devuelve `{"horas_main": 22.5, "horas_completo": 95.0}` |
| `guardar.py` | `guardar_json(resultado, ruta)` guarda el data.json |

Cada scraper descarga con `obtener_html("steam", url)` y lleva `@fuente_segura("steam")` encima, los dos de `scraper/red.py`. Así respeta el límite por sitio, reintenta y nunca detiene el programa. `scraper/falsos.py` es un ejemplo completo con el formato correcto.
