# 4. Actualización recurrente

Código: `.github/workflows/actualizar.yml`.

## 4.1 Cuándo corre

GitHub Actions corre el scraper con un cron **cada 12 horas** (`0 6,18 * * *`, o sea 00:00 y 12:00 en Costa Rica). Los precios de las tiendas cambian a lo sumo una vez al día, así que dos corridas diarias bastan para ver una oferta el mismo día que empieza sin cargar de más a los sitios.

También se puede correr a mano desde la pestaña **Actions → Actualizar precios → Run workflow**, y la página se vuelve a publicar sola (sin scrapear) cada vez que alguien cambia algo en `web/`.

## 4.2 Qué hace cada corrida

| Paso | Qué hace |
|---|---|
| 1. Preparar | Descarga el repo, instala Python 3.12 y `requirements.txt` |
| 2. Scraper | `python ejecutar.py` con `SUPABASE_URL` y `SUPABASE_KEY` tomados de los **Secrets** del repositorio, nunca del código |
| 3. Log | Sube la carpeta `logs/` como artefacto de la corrida (se guarda 14 días) para revisar fallas |
| 4. Guardar | Si el scraper terminó bien y el `data.json` cambió, lo sube al repo con un commit automático |
| 5. Publicar | Publica la carpeta `web/` en GitHub Pages |

## 4.3 Qué pasa si algo falla

- **Una fuente falla:** `guardar_json` conserva el último dato bueno y lo marca (sección 3.10). La corrida sigue normal.
- **Supabase no responde:** `leer_repo` usa la copia local del REPO.
- **El scraper falla completo:** el paso 2 tiene `continue-on-error`, así que no se sube nada y el paso 5 vuelve a publicar el último `data.json` bueno. La web nunca queda vacía.
- **Dos corridas al mismo tiempo:** `concurrency` hace que una espere a la otra, para que no escriban el `data.json` a la vez.
- **Las tiendas bloquean las IP de GitHub:** se ve en el log como muchas fallas `HTTP 403`. El plan B es correr `python ejecutar.py` en una computadora del equipo con el Programador de tareas de Windows y subir el `data.json` con git; el paso 5 lo publica igual.

## 4.4 Configuración (una sola vez)

1. **Settings → Secrets and variables → Actions → New repository secret:** `SUPABASE_URL` y `SUPABASE_KEY` (la llave pública de lectura; la secreta no hace falta).
2. **Settings → Pages → Source: GitHub Actions.**
3. **Actions → Actualizar precios → Run workflow** para la primera corrida.
