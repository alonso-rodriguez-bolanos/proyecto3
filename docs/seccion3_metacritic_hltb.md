# 3. Estrategia de web scraping: Metacritic y How Long To Beat

Código: `scraper/metacritic.py` y `scraper/hltb.py`. Pruebas: `pruebas/test_fuentes_extra.py`.

Las dos fuentes siguen las mismas reglas que las tiendas: reciben una fila del REPO, nunca lanzan excepciones (llevan `@fuente_segura`) y respetan el límite por sitio de `scraper/limitador.py` (3 solicitudes a la vez y 0.5 s entre solicitudes para cada sitio).

## 3.8 Metacritic

Página: el enlace `url_metacritic` del REPO, por ejemplo `metacritic.com/game/hades/`. No se busca por nombre: el gestor arma el enlace una vez, confirma que existe y queda guardado.

- **Dónde está el score.** Con las DevTools se vio que la página llega con el Metascore en el HTML, sin ejecutar JavaScript, en dos lugares:
  1. Un bloque `<script type="application/ld+json">` con datos estructurados de tipo `VideoGame`. El score está en `aggregateRating.ratingValue` (en Hades, `93`, con `reviewCount: 61`). Es la fuente principal porque es un formato estándar (schema.org) que cambia poco aunque cambie el diseño.
  2. El círculo visible, un elemento con la clase `c-siteReviewScore` que contiene `<span>93</span>`. Se usa como respaldo si el bloque JSON-LD no está.
- **Score pendiente.** Si el juego todavía no tiene suficientes críticas, el círculo dice `tbd` y el JSON-LD no trae `aggregateRating`; se devuelve `{"ok": false, "error": "Metacritic no muestra score"}`.
- **Plataforma.** La página por defecto de Metacritic muestra el Metascore de la plataforma principal del juego. Como el REPO solo tiene juegos de PC y PlayStation, que casi siempre tienen scores parecidos, se reporta ese único score.
- **Resultado:** `{"ok": true, "score": 93}`.

Prueba con los primeros juegos del REPO (`python -m scraper.metacritic 4`): Hades 93, The Witcher 3 92, Red Dead Redemption 2 97, GTA V 97.

## 3.9 How Long To Beat

How Long To Beat no muestra los tiempos en el HTML inicial (los carga con una búsqueda interna), así que se usa la biblioteca `howlongtobeatpy`, que el profesor permitió y cuenta como scraping: hace la misma búsqueda que la página.

- **Búsqueda.** Si `url_hltb` trae el id del juego (`howlongtobeat.com/game/62941`) se consulta directo con `search_from_id`. Si no, se busca por nombre.
- **Elegir el juego correcto.** La búsqueda devuelve varios juegos (buscar "Hades" trae Hades, Hades II y Shades of Black). Se aceptan solo los que tienen similitud de nombre ≥ 0.8 y, entre ellos, se prefiere el que salió el mismo año (± 1) que la `fecha_lanzamiento` del REPO. Así Hades (2020) no se confunde con Hades II (2025).
- **Tiempos.** Se toma `main_story` (historia principal) como `horas_main` y `completionist` (100 %) como `horas_completo`, redondeados a un decimal. HLTB usa 0 cuando no hay dato; eso se guarda como `null`.
- **Robustez.** La biblioteca hace sus propias solicitudes y no pasa por `obtener_html`, así que `hltb.py` le agrega lo mismo que tienen los demás scrapers: cada consulta espera su turno con `turno("hltb")` y se reintenta hasta 3 veces con espera creciente (1, 2 y 4 s más un poco al azar). Si después de los reintentos sigue fallando, `@fuente_segura` lo convierte en `{"ok": false, "error": "..."}`.
- **Resultado:** `{"ok": true, "horas_main": 23.6, "horas_completo": 95.3}`.

Prueba (`python -m scraper.hltb 4`): Hades 23.6 / 95.3 h, The Witcher 3 51.7 / 175.4 h, Red Dead Redemption 2 50.8 / 196.3 h, GTA V 32.1 / 89.5 h.

## 3.10 Consistencia del `data.json`

Código: `scraper/guardar.py`, función `guardar_json(resultado, ruta)`.

1. **Último dato bueno.** Antes de escribir se lee el `data.json` anterior. Para cada juego y cada fuente (cada tienda, Metacritic y HLTB): si la fuente falló en esta corrida pero en la anterior estaba bien, se conserva el dato anterior y se le agregan `"desactualizado": true`, el `"error"` de hoy y `"dato_de"` con la fecha del dato. La web muestra esos datos con un aviso "⚠ dato anterior". Cuando la fuente vuelve a responder, el dato nuevo reemplaza al viejo y la marca desaparece.
2. **Escritura atómica.** El JSON se escribe primero en un archivo temporal en la misma carpeta, se fuerza a disco (`fsync`) y se renombra encima del anterior con `os.replace`, que es atómico. La web siempre ve el archivo viejo completo o el nuevo completo, nunca uno a medias. Si algo falla al escribir, se borra el temporal y el `data.json` anterior queda intacto.
3. **Resultado vacío.** Si una corrida no produce ningún juego (por ejemplo, Supabase y su copia local fallaron), no se sobrescribe el archivo.
4. **Historial de precios.** Después de guardar el `data.json`, `actualizar_historial` agrega los precios de la corrida a `web/historial.json` con el formato `{"id": {"Steam": [[fecha, precio], ...]}}`. Solo se guarda un punto cuando el precio cambia, así el archivo crece poco aunque el cron corra dos veces al día. No se registran tiendas que fallaron ni datos conservados de una corrida anterior, para no inventar precios. También se escribe de forma atómica, y si falla no afecta al `data.json`. Con este historial la web dibuja el gráfico de precios de cada juego y marca los que hoy están en su **mínimo histórico**.
