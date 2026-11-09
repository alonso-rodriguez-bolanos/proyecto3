# 3. Estrategia de web scraping: tiendas e indicador de oferta

Código: `scraper/tiendas.py`. Pruebas: `pruebas/test_tiendas.py`.

## 3.1 Qué devuelve cada tienda

Hay una función por tienda: `scrape_steam(juego)`, `scrape_psstore(juego)` y `scrape_xbox(juego)`. Cada una recibe una fila del REPO, abre el enlace directo que el REPO guarda para esa tienda y devuelve un diccionario con este formato:

| Campo | Significado |
|---|---|
| `tienda` | Steam, PlayStation Store o Xbox Store |
| `precio_actual` | Lo que cuesta hoy en dólares |
| `precio_regular` | El precio sin descuento |
| `en_oferta`, `descuento_pct` | Indicador de oferta (ver 3.5) |
| `formato` | `Digital`, porque las tres tiendas venden descargas |
| `plataforma` | `PC`, `PS4`/`PS5` o `Xbox Series X\|S`/`Xbox One` |
| `url` | Enlace de la página consultada |
| `ok` | `true` si se leyó el precio; si no, `false` y un campo `error` |

No se busca el juego por nombre. Se usa el enlace guardado en el REPO, así un cambio de nombre entre sitios no afecta. Todas las tiendas se piden en la región de EE. UU. para que los precios estén en dólares y se puedan comparar.

Las funciones nunca lanzan excepciones. Descargan con `obtener_html` y llevan el decorador `@fuente_segura`, los dos de `scraper/red.py`. Así cada solicitud respeta el límite por sitio, tiene timeout y reintentos, y si algo falla devuelve `{"ok": false, "error": "..."}` sin detener los demás juegos.

## 3.2 Steam

Página: `store.steampowered.com/app/<appid>/?cc=us&l=english`.

- **Verificación de edad.** Algunos juegos, por ejemplo GTA V, redirigen primero a `/agecheck/`. Se resuelve enviando con la solicitud las cookies que Steam guarda después de esa pantalla (`birthtime`, `lastagecheckage`, `mature_content`, `wants_mature_content`). Si aun así aparece el formulario de edad, se reporta el error `Steam pidió verificación de edad`.
- **Dónde está el precio.** Dentro de `#game_area_purchase`, cada opción de compra es un bloque `.game_area_purchase_game`:
  - Sin descuento: `.game_purchase_price` muestra un solo precio y ese precio es a la vez el actual y el regular.
  - Con descuento: `.discount_original_price` es el regular, `.discount_final_price` el actual y `.discount_pct` el porcentaje.
  - El atributo `data-price-final` trae el precio en centavos y se usa si el texto no se puede leer.
- **Qué bloque se toma.** Se toma el primer bloque que tenga precio. Se saltan los *bundles* (bloques dentro de `.dynamic_bundle_description`), que venden varios juegos juntos, y las demos, que no tienen precio. El primer bloque que queda es la edición estándar del juego.
- **Gratis.** El texto `Free` o `Free To Play` se lee como precio 0.
- **Retirado de la tienda.** Si la página solo muestra un aviso en `#purchase_note`, por ejemplo "unlisted on the Steam store", se reporta `no está a la venta en Steam`.

## 3.3 PlayStation Store

Página: `store.playstation.com/en-us/concept/<id>` o `/en-us/product/<id>`.

Con las DevTools se confirmó que la página llega con el precio ya puesto en el HTML, así que no hace falta ejecutar JavaScript.

- **Dónde está el precio.** El botón de compra principal tiene `data-qa="mfeCtaMain"`. Cada opción de precio es un elemento `mfeCtaMain#offerN` (N = 0, 1, …) con `#finalPrice` (precio actual) y, si hay descuento, `#originalPrice` (precio regular).
- **Ofertas de suscripción.** Muchas veces `offer0` no es un precio de compra sino el de PS Plus: su precio es "Included" o trae un descuento solo para suscriptores. Esas ofertas se reconocen porque llevan un `#serviceIcon#ps-plus` o un `#discountInfo` que menciona PlayStation Plus, EA Play o Ubisoft+, y se saltan. Se toma la primera oferta normal. En Red Dead Redemption 2, por ejemplo, `offer0` dice "Included" (PS Plus Extra) y el precio de compra real está en `offer1`.
- **Respaldo en el `<script>`.** El botón tiene un atributo `data-initial` con el id de un `<script type="application/json">` de la misma página. Ese script trae cada precio con `basePriceValue` y `discountedValue` en centavos, junto con `isTiedToSubscription`. Si el HTML visible no trae una oferta que se pueda leer, se usan esos datos, descartando los que dependen de una suscripción. Leer ese script cuenta como scraping porque es parte del HTML de la página.
- **Plataforma.** Sale de `gameInfo#releaseInformation#platform-value` ("PS4, PS5"). Se reporta `PS5` si el juego está para PS5 y si no `PS4`.
- **Sin precio.** Si la oferta dice "Announced" o "Unavailable", se reporta `PS Store no lo vende: Announced`. Si la página llega sin el bloque de compra, cosa que pasó una vez en las pruebas, se pide otra vez antes de marcar el error.

## 3.4 Xbox Store (tercera tienda, opcional)

Página: `xbox.com/en-US/games/store/<nombre>/<id>`.

- La página trae el estado inicial en `window.__PRELOADED_STATE__`. El precio está en `core2.products.productSummaries[<id>].specificPrices.purchaseable`, donde `listPrice` es el actual y `msrp` el regular.
- Hay varias entradas: una normal y otras con descuento solo para Game Pass. Se toma la que tiene `eligibility = "None"`, que es el precio para cualquier comprador.
- Respaldo: el precio visible del encabezado (`ProductDetailsHeader-module__price`).
- Plataforma: `Xbox Series X|S` si `availableOn` incluye `XboxSeriesX`, si no `Xbox One`.

## 3.5 Indicador de oferta

Función `calcular_oferta(actual, regular, precio_sugerido)`:

1. **Regular de referencia.** Se usa el precio regular que muestra la tienda: el precio tachado si hay descuento, o el único precio si no lo hay. Solo si la tienda no muestra un regular se usa el `precio_sugerido` del REPO.
2. **En oferta** si `precio_actual < regular`.
3. **Descuento** = (regular − actual) / regular × 100, redondeado a entero. Es 0 si no hay oferta.

Ejemplo (Dark Souls III, PS Store, 9 nov 2026): actual $29.99 y regular $59.99, así que está en oferta con un descuento de (59.99 − 29.99) / 59.99 × 100 = 50 %.

Si la tienda está más cara que el precio sugerido, no se considera oferta: no hay descuento y el dato se muestra tal cual.

## 3.6 Nivel 3: tiendas en paralelo

`procesar_tiendas(juego, max_workers)` crea un `ThreadPoolExecutor` y lanza un hilo por cada tienda que el juego tiene en el REPO (Steam y PS Store siempre; Xbox y eShop solo si hay enlace). Se usan hilos porque cada consulta pasa casi todo el tiempo esperando la red, y mientras espera el hilo suelta el GIL. El resultado sale en el mismo orden de tiendas para todos los juegos. Una tienda que falla queda con `ok: false` y no afecta a las demás.

Con `max_workers = 1` las tiendas se consultan una después de otra; así funciona la versión secuencial que se usa para medir el speedup. En la prueba `test_las_tiendas_corren_al_mismo_tiempo`, dos tiendas que tardan 0.3 s cada una terminan en unos 0.3 s con 2 hilos y en unos 0.6 s con 1 hilo.

El límite por sitio (`scraper/limitador.py`) se aplica igual: aunque haya muchos procesos e hilos, nunca hay más de 4 solicitudes a la vez a Steam ni más de 3 a la PS Store, con una pausa mínima entre solicitudes.

## 3.7 Resultado de la prueba con el REPO

Prueba del 9 de noviembre de 2026 con `python -m scraper.tiendas 200`: 115 juegos y 230 consultas a tiendas en 242 s, de forma secuencial y con el límite por sitio. Se leyeron 225 precios, 30 de ellos en oferta. Las 5 fallas fueron:

- 3 enlaces del REPO que apuntan a ediciones que ya no se venden.
- 1 juego que la PS Store muestra como "Announced".
- 1 página de PS Store que llegó incompleta. Esa falla motivó el reintento descrito en 3.3.
