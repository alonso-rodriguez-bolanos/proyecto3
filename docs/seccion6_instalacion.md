# 6. Instalación, uso y URL pública

**Página publicada:** https://alonso-rodriguez-bolanos.github.io/proyecto3/ (se activa al configurar Pages, ver 4.4)

**Repositorio:** https://github.com/alonso-rodriguez-bolanos/proyecto3

## 6.1 Requisitos

- Python 3.11 o más nuevo.
- Las llaves de Supabase (se piden por privado).

## 6.2 Instalar

Windows (PowerShell):

```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.ejemplo .env
```

macOS o Linux:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.ejemplo .env
```

Después se llenan `SUPABASE_URL` y `SUPABASE_KEY` en el `.env`. Para agregar o editar juegos con el gestor también hace falta `SUPABASE_SECRET_KEY`.

## 6.3 Correr

| Comando | Qué hace |
|---|---|
| `python ejecutar.py` | Scraper completo con los procesos de la computadora; escribe `web/data.json` |
| `python ejecutar.py --workers 8` | Con 8 procesos en el nivel 1 |
| `python ejecutar.py --secuencial` | Versión secuencial (todo en 1 proceso y 1 hilo) |
| `python ejecutar.py --falsos --repo-falso 50` | Prueba sin internet ni Supabase |
| `python -m scraper.metacritic 5` / `python -m scraper.hltb 5` | Prueba cada fuente con los primeros 5 juegos del CSV |
| `python herramientas/benchmark.py` | Mide 1, 2, 4, 8 y 16 procesos y dibuja los gráficos |
| `python gestor.py` | Ventana para ver y editar los juegos del REPO |
| `python -m unittest discover -s pruebas` | Pruebas automáticas |

## 6.4 Ver la página en la computadora

La página lee `data.json` con `fetch`, así que no funciona abriendo el archivo con doble clic. Hay que servir la carpeta:

```
python -m http.server -d web 8000
```

y abrir http://localhost:8000. Con http://localhost:8000/?mock=1 se ve con los 10 juegos inventados de `web/mock.json`.

## 6.5 La página

Diseño oscuro inspirado en Razer Synapse. Todo está en `web/index.html` (HTML, CSS y JavaScript sin bibliotecas; los gráficos son SVG dibujados por la misma página).

- **Pestañas:** Todos, En oferta, Mejor valorados (Metacritic ≥ 85), Menos de $10, PC vs PlayStation y Rendimiento. La pestaña queda en la URL (`?vista=comparar`), así un enlace abre directo esa vista.
- **Indicadores:** juegos rastreados, juegos en oferta, mayor descuento y ahorro promedio.
- **Tarjetas** con portada, plataformas, el precio más barato entre las tiendas (tachado el regular si está en oferta), el porcentaje de descuento, el Metascore con color (verde ≥ 75, amarillo ≥ 50, rojo < 50), las horas de How Long To Beat y la marca **▼ Mínimo histórico** cuando el precio de hoy es el más bajo registrado.
- **Filtros:** nombre, plataformas, tienda, precio máximo, Metacritic mínimo, descuento mínimo y "solo en oferta". Si se elige una tienda, el precio y la oferta se miran solo en esa tienda.
- **Orden:** mayor descuento, precio, Metacritic, más horas por dólar (horas de HLTB ÷ precio), horas, fecha de lanzamiento o nombre.
- **Detalle:** todas las tiendas con la más barata resaltada y enlace a cada una, el **gráfico del historial de precios** por tienda (de `historial.json`) con el mínimo histórico y desde cuándo se sigue el juego, Metacritic, HLTB y la fecha de la última actualización. Una fuente que falló se muestra como "No disponible" y un dato conservado de una corrida anterior lleva "⚠ dato anterior".
- **PC vs PlayStation:** para cada juego con precio en Steam y en PS Store, cuál es más barato y por cuánto, ordenado por la diferencia, con el total de juegos que ganan en cada tienda y el ahorro promedio. Respeta los filtros del panel.
- **Rendimiento:** tiempo, speedup y eficiencia del benchmark (de `rendimiento.json`, que escribe `herramientas/benchmark.py`), los 3 niveles de paralelismo y la Ley de Amdahl calculada con los números medidos.

Con `?mock=1` la página usa `mock.json`, `mock_historial.json` y `mock_rendimiento.json`, que son datos inventados y la página los marca como de prueba.
