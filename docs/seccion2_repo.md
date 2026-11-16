# 2. Estructura del REPO y cómo se actualiza

El REPO es la tabla `juegos` en Supabase (PostgreSQL). El scraper no tiene ningún juego escrito en el código: en cada corrida lee la tabla, así que agregar, corregir o sacar un juego no requiere tocar el programa. Hoy tiene **216 juegos, 215 activos**.

## 2.1 Tabla `juegos`

Se crea con `sql/crear_tabla.sql`.

| Columna | Tipo | Obligatoria | Uso |
|---|---|---|---|
| `id` | bigint, identidad | sí | Identificador; ordena el `data.json` y une el historial de precios |
| `nombre` | text, **único** | sí | Nombre del juego; no se puede repetir |
| `plataformas` | text[] | sí | PC, PS4, PS5, Xbox, Switch (filtro de plataforma de la web) |
| `fecha_lanzamiento` | date | no | Para elegir el juego correcto en HLTB cuando hay remakes con el mismo nombre |
| `precio_sugerido` | numeric(6,2) | sí | Precio de lanzamiento; respaldo para calcular el descuento si la tienda no muestra el precio regular |
| `imagen_url` | text | no | Portada de la tarjeta |
| `url_steam` | text | sí | Enlace directo a Steam |
| `url_psstore` | text | sí | Enlace directo a PlayStation Store de EE. UU. (`/en-us/`) |
| `url_xbox`, `url_eshop` | text | no | Tiendas opcionales |
| `url_metacritic` | text | no | Página del juego en Metacritic |
| `url_hltb` | text | no | Página en HLTB; si trae el id se busca por id en vez de por nombre |
| `activo` | boolean | sí (`true`) | Para sacar un juego se pone en `false` en vez de borrarlo |

**Por qué se guardan los enlaces directos y no solo el nombre.** Buscar por nombre en cada corrida es lento y se equivoca con ediciones, remakes y paquetes (por ejemplo *Resident Evil 4* de 2005 contra el remake de 2023). Con el enlace directo cada corrida descarga exactamente la página correcta, y el enlace se revisa una sola vez al agregar el juego.

**Seguridad.** La tabla tiene *row level security*: cualquiera puede leer (la llave pública que usa el scraper y GitHub Actions) y solo la llave secreta puede escribir. La llave secreta solo vive en el `.env` de quien administra el REPO y nunca se sube a GitHub.

## 2.2 Cómo se lee

`scraper/repo.py` pide las filas con `activo = true`, de 1000 en 1000, ordenadas por `id`:

1. Si Supabase responde, guarda una copia en `datos/repo_cache.json`.
2. Si Supabase no responde (sin internet, llave vencida, servicio caído), usa esa copia local y lo deja escrito en el log. La corrida no se detiene.
3. Salta las filas a las que les falta un dato obligatorio (`id`, `nombre`, `plataformas`, `precio_sugerido`, `url_steam`, `url_psstore`) y avisa en el log cuál fue.

## 2.3 Cómo se actualiza

El REPO se administra con **`python gestor.py`**, una ventana hecha con tkinter que lee y escribe la tabla con la llave secreta:

| Acción | Qué hace |
|---|---|
| Recargar | Vuelve a leer la tabla y actualiza el respaldo `datos/juegos.csv` |
| Nuevo / Guardar | Agrega o edita un juego; antes de guardar valida los campos (nombre, al menos una plataforma, precio > 0, fecha AAAA-MM-DD, enlaces de Steam y PS Store de EE. UU.) |
| Buscar enlaces | Revisa la página de Steam, busca el juego en PS Store y confirma la página de Metacritic, y llena lo que falte |
| Completar todos | Hace lo mismo con todos los juegos a los que les falta algo |
| Importar CSV | Sube muchos juegos de una vez; si un nombre ya existe lo actualiza en vez de duplicarlo (`on_conflict=nombre`) |
| Activo | Desmarcarlo saca el juego de la próxima corrida sin perder sus datos |

Los cambios se ven en la página en la siguiente corrida automática (máximo 12 horas) o al correr el workflow a mano.

## 2.4 Cómo se cargaron los 200+ juegos

El equipo se repartió la carga en dos mitades. Para la segunda mitad se usaron dos herramientas:

- `herramientas/preparar_lote.py` toma una lista de nombres y para cada uno busca los enlaces de Steam, PS Store, Metacritic y HLTB, el precio y la fecha; separa los que quedaron completos (`datos/lote_listo.csv`, 101 juegos) de los que hay que revisar a mano.
- `herramientas/auditar_enlaces.py` compara el título de cada tienda con el nombre del REPO para detectar enlaces a otra edición o a otro juego. En la revisión de los 216 juegos encontró 4 enlaces equivocados (Resident Evil 4, Death Stranding Director's Cut, Yakuza 0 y The Outer Worlds), que se corrigieron con `datos/correcciones_enlaces.csv`.
