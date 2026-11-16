# 4. Manejo de errores y actualización recurrente

Código: `.github/workflows/actualizar.yml`.

## 4.1 Manejo de errores

La regla es que **un error nunca detiene la corrida ni deja la página vacía**: se atrapa en el nivel más bajo posible, se registra en el log y el resto sigue.

| Dónde | Qué puede fallar | Qué se hace |
|---|---|---|
| Descarga (`red.py`) | Timeout, conexión caída, HTTP 429/5xx | Timeout de 5 s para conectar y 20 s para leer; hasta 3 intentos con espera exponencial (1, 2, 4 s más un poco al azar) y respetando `Retry-After` si el sitio lo manda |
| Descarga (`red.py`) | HTTP 403/404 | No se reintenta (no va a cambiar); se devuelve el error de una vez |
| Límites del sitio (`limitador.py`) | Saturar al sitio y que bloquee | Máximo 3–4 solicitudes a la vez por sitio y una pausa mínima entre solicitudes, compartido por todos los procesos |
| Scraper (`@fuente_segura`) | El HTML cambió, falta un elemento, error inesperado | El decorador atrapa cualquier excepción y devuelve `{"ok": false, "error": "…"}` en vez de lanzarla |
| Scraper | La página no es el juego (upgrade, DLC, prueba gratis, paquete) | Se descartan esos bloques antes de leer el precio (secciones 3.2 y 3.3) |
| Nivel 2 | Una fuente se cuelga | Tope de 180 s por juego; la fuente queda como `timeout global` y el juego se guarda con las demás |
| Nivel 1 | Un proceso muere | Sus juegos se repiten una vez en un pool nuevo; si falla otra vez quedan con error |
| REPO (`repo.py`) | Supabase no responde | Se usa la copia local `datos/repo_cache.json` |
| REPO | Fila incompleta | Se salta ese juego y se avisa en el log |
| Guardado (`guardar.py`) | Una fuente falló en esta corrida | Se conserva el último dato bueno marcado como `desactualizado` (sección 3.10) |
| Guardado | Se corta la luz o el disco se llena a mitad de escribir | Escritura atómica: se escribe un temporal y se reemplaza con `os.replace`; el `data.json` anterior queda intacto |
| Guardado | El resultado viene vacío | No se escribe, para no borrar la página |

Cada corrida deja un log por día en `logs/scraper_AAAAMMDD.log` y una línea en `logs/metricas.jsonl` con la duración y cuántas fallas hubo por fuente.

## 4.2 Cuándo corre

GitHub Actions corre el scraper con un cron **cada 12 horas** (`0 6,18 * * *`, o sea 00:00 y 12:00 en Costa Rica). Los precios de las tiendas cambian a lo sumo una vez al día, así que dos corridas diarias bastan para ver una oferta el mismo día que empieza sin cargar de más a los sitios.

También se puede correr a mano desde la pestaña **Actions → Actualizar precios → Run workflow**, y la página se vuelve a publicar sola (sin scrapear) cada vez que alguien cambia algo en `web/`.

## 4.3 Qué hace cada corrida

| Paso | Qué hace |
|---|---|
| 1. Preparar | Descarga el repo, instala Python 3.12 y `requirements.txt` |
| 2. Scraper | `python ejecutar.py` con `SUPABASE_URL` y `SUPABASE_KEY` tomados de los **Secrets** del repositorio, nunca del código |
| 3. Log | Sube la carpeta `logs/` como artefacto de la corrida (se guarda 14 días) para revisar fallas |
| 4. Guardar | Si el scraper terminó bien y el `data.json` cambió, lo sube al repo con un commit automático |
| 5. Publicar | Publica la carpeta `web/` en GitHub Pages |

## 4.4 Qué pasa si algo falla

- **Una fuente falla:** `guardar_json` conserva el último dato bueno y lo marca (sección 3.10). La corrida sigue normal.
- **Supabase no responde:** `leer_repo` usa la copia local del REPO.
- **El scraper falla completo:** el paso 2 tiene `continue-on-error`, así que no se sube nada y el paso 5 vuelve a publicar el último `data.json` bueno. La web nunca queda vacía.
- **Dos corridas al mismo tiempo:** `concurrency` hace que una espere a la otra, para que no escriban el `data.json` a la vez.
- **Las tiendas bloquean las IP de GitHub:** se ve en el log como muchas fallas `HTTP 403`. El plan B es correr `python ejecutar.py` en una computadora del equipo con el Programador de tareas de Windows y subir el `data.json` con git; el paso 5 lo publica igual.

## 4.5 Configuración (una sola vez)

1. **Settings → Secrets and variables → Actions → New repository secret:** `SUPABASE_URL` y `SUPABASE_KEY` (la llave pública de lectura; la secreta no hace falta).
2. **Settings → Pages → Source: GitHub Actions.**
3. **Actions → Actualizar precios → Run workflow** para la primera corrida.
