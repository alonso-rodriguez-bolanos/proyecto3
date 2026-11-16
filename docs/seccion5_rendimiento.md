# 5. Análisis de rendimiento

Medido el 15/11/2026 con `python herramientas/benchmark.py`. Los tiempos de cada corrida están en `docs/benchmark/tiempos.csv`, el resumen en `docs/benchmark/resumen.csv` y los gráficos en `docs/benchmark/*.png`.

## 5.1 Cómo se midió

- **Computadora:** siempre la misma, una laptop con procesador AMD Ryzen (familia 25, modelo 68), con **8 núcleos físicos y 16 lógicos**, Windows 11 y Python 3.14, conectada por Wi‑Fi doméstico. Los datos de la corrida quedan en `docs/benchmark/maquina.json`.
- **Carga:** los **216** juegos activos del REPO, cada uno con Steam, PlayStation Store, Metacritic y HLTB, o sea 4 solicitudes por juego (864 por corrida). El REPO se leyó de la copia local `datos/repo_cache.json` (la misma tabla de Supabase guardada por `repo.py`), así todas las corridas procesan exactamente los mismos juegos.
- **Duración total:** 18 corridas, de las 16:57 a las 20:53 (casi 4 horas).
- **Configuraciones:** versión secuencial y 1, 2, 4, 8 y 16 procesos en el nivel 1. Los niveles 2 y 3 usan siempre 3 y 2 hilos.
- **Versión secuencial:** el mismo código con los tres niveles en 1 worker (`python ejecutar.py --secuencial`): un proceso, y las fuentes y tiendas de cada juego una después de otra.
- **Repeticiones:** 3 por configuración, intercaladas (secuencial, 1, 2, …, 16, y otra vez) para repartir el ruido de la red entre todas. Se reporta el promedio y la desviación estándar.
- **Medida:** `duracion_s` es el tiempo de procesar todos los juegos (sin contar leer Supabase ni escribir el JSON), medido con `time.perf_counter`.
- **Fórmulas:** speedup = T secuencial / T paralelo; eficiencia = speedup / procesos.

## 5.2 Resultados

| Configuración | Rep. 1 (s) | Rep. 2 (s) | Rep. 3 (s) | Promedio (s) | Desv. (s) | Speedup | Eficiencia |
|---|---|---|---|---|---|---|---|
| Secuencial | 1957.9 | 1677.0 | 1988.9 | **1874.6** | 171.8 | 1.00 | 1.00 |
| 1 proceso | 1147.3 | 1019.4 | 1180.5 | **1115.7** | 85.1 | 1.68 | 1.68 |
| 2 procesos | 632.3 | 609.4 | 472.7 | **571.5** | 86.3 | 3.28 | 1.64 |
| 4 procesos | 409.8 | 408.4 | 311.6 | **376.6** | 56.3 | 4.98 | 1.24 |
| 8 procesos | 415.6 | 437.3 | 364.6 | **405.8** | 37.3 | 4.62 | 0.58 |
| 16 procesos | 331.4 | 424.0 | 312.3 | **355.9** | 59.7 | 5.27 | 0.33 |

La versión secuencial tarda **31 minutos** (≈ 8.7 s por juego, ≈ 2.2 s por solicitud); con 16 procesos baja a **6 minutos**. La desviación es alta (hasta 9 % del promedio en la secuencial y 17 % con 16 procesos) porque el tiempo depende casi todo de la red y de cómo respondan los sitios en ese momento; por eso se intercalaron las repeticiones.

**Fallas por corrida.** En todas las corridas fallan los mismos 6 datos (2 juegos sin score en Metacritic y 4 que HLTB no tiene). Con 4 o más procesos aparecen fallas nuevas, solo en HLTB:

| Procesos | 1 | 2 | 4 | 8 | 16 |
|---|---|---|---|---|---|
| Fallas de HLTB (rep. 1 / 2 / 3) | 4 / 4 / 4 | 4 / 4 / 8 | 22 / 26 / 64 | 23 / 17 / 43 | 53 / 20 / 62 |

HLTB no responde con un error cuando recibe muchas búsquedas seguidas: devuelve una lista vacía, y el scraper lo registra como "HLTB no encontró el juego". Ningún dato se pierde: `guardar.py` conserva el último valor bueno y lo marca como desactualizado (sección 3.10).

Los mismos resultados se ven en la pestaña **Rendimiento** de la página publicada: el benchmark escribe `web/rendimiento.json` y la web dibuja los gráficos.

![Tiempo](benchmark/tiempo.png)
![Speedup](benchmark/speedup.png)
![Eficiencia](benchmark/eficiencia.png)

## 5.3 Por qué la eficiencia puede salir mayor que 1

Con **1 proceso** el programa ya es más rápido que la versión secuencial, aunque usa un solo núcleo. La razón es que los niveles 2 y 3 siguen activos: dentro de ese proceso las 4 solicitudes de cada juego salen al mismo tiempo en hilos. Mientras un hilo espera la respuesta de la red suelta el GIL y otro puede trabajar, así que la espera de la red se solapa. En una prueba con scrapers falsos (0.2 s por página, 24 juegos, sin límite por sitio) la versión secuencial tardó 19.3 s y la de 1 proceso 5.5 s: speedup de 3.5 con un solo proceso.

Por eso la eficiencia medida contra la versión secuencial puede ser mayor que 1. No es un error: el speedup no viene solo de usar más núcleos sino de esperar la red en paralelo. En la medición real, **1 proceso tardó 1115.7 s contra 1874.6 s de la secuencial: speedup de 1.68 con un solo núcleo** (eficiencia 1.68), y con 2 y 4 procesos la eficiencia sigue arriba de 1 (1.64 y 1.24). Con sitios reales el aporte de los hilos es menor que en la prueba falsa (1.68 contra 3.5) porque el límite por sitio no deja salir todas las solicitudes a la vez.

## 5.4 Cuellos de botella

1. **La red (domina).** Procesar un juego casi no usa CPU: es descargar 4 páginas y leer unos pocos elementos del HTML. Casi todo el tiempo el programa está esperando respuestas. Por eso los hilos (niveles 2 y 3) aportan tanto como los procesos.
2. **El límite por sitio (el techo).** Para no saturar a ningún sitio, `limitador.py` deja pasar pocas solicitudes a la vez por sitio y obliga a una pausa entre solicitudes. Eso pone un tiempo mínimo que ningún número de procesos puede bajar:

   | Sitio | A la vez | Pausa | Máximo de solicitudes por segundo |
   |---|---|---|---|
   | Steam | 4 | 0.3 s | ≈ 3.3 |
   | PS Store | 3 | 0.5 s | 2 |
   | Metacritic | 3 | 0.5 s | 2 |
   | HLTB | 3 | 0.5 s | 2 |

   El límite no es solo la pausa. Cada sitio deja como máximo 3 solicitudes a la vez, y cada solicitud tarda en promedio ≈ 2.2 s (1874.6 s / 864 solicitudes en la secuencial). Entonces un sitio atiende como mucho ≈ 3 / 2.2 ≈ 1.4 juegos por segundo, y los 216 juegos necesitan por lo menos ≈ 216 × 2.2 / 3 ≈ **160 s por sitio**, más la cola de la pausa y los sitios más lentos que el promedio (Metacritic y HLTB). Lo medido (≈ 310–420 s) queda por encima de ese piso, y la curva **se aplana a partir de 4 procesos**: de 4 a 8 el promedio no mejora (376.6 s → 405.8 s, dentro de la desviación) y de 8 a 16 baja apenas a 355.9 s. Los procesos de más solo hacen fila en el semáforo del sitio.
   
   HLTB muestra el otro lado del límite: con 4 o más procesos el sitio empieza a devolver búsquedas vacías (tabla de fallas en 5.2). Es decir, aun con el límite propio el sitio ya está al borde de lo que tolera; subir los límites bajaría el tiempo pero perdería datos.
3. **La CPU (poca).** Leer el HTML con BeautifulSoup sí usa CPU y ahí es donde varios procesos ayudan de verdad, porque cada proceso tiene su propio GIL. Pero es una parte pequeña del tiempo total.
4. **Arranque de procesos.** En Windows los procesos se crean con `spawn`: cada uno arranca un Python nuevo e importa los módulos (≈ 0.3–1 s cada uno). Con 16 procesos y pocos juegos por proceso ese costo se nota.
5. **Núcleos lógicos.** Como la computadora tiene 8 núcleos físicos con 2 hilos de hardware cada uno (16 lógicos), de 8 a 16 procesos se comparten núcleos físicos. Para un programa que casi no usa CPU eso importa poco, pero conviene decirlo al interpretar el punto de 16.

## 5.5 Efecto de cada nivel

| Nivel | Qué paraleliza | Con qué | Qué aporta |
|---|---|---|---|
| 1 | Juegos | Procesos | Usa varios núcleos (un GIL por proceso). Ayuda en la parte de CPU y multiplica las esperas de red que se solapan |
| 2 | Fuentes de un juego (tiendas, Metacritic, HLTB) | 3 hilos | Un juego tarda lo que su fuente más lenta, no la suma de las tres |
| 3 | Tiendas de un juego | 2 hilos | Steam y PS Store se consultan a la vez |

La diferencia entre "secuencial" y "1 proceso" mide el aporte de los niveles 2 y 3 juntos; la curva de 1 a 16 procesos mide el aporte del nivel 1.

- **Niveles 2 y 3 (hilos):** 1874.6 s → 1115.7 s, speedup **1.68** sin usar más núcleos.
- **Nivel 1 (procesos), tomando 1 proceso como base:** 2 procesos 1.95×, 4 procesos **2.96×**, 8 procesos 2.75×, 16 procesos 3.13×. De 1 a 2 y de 2 a 4 casi se duplica; después ya no.
- **Los tres juntos:** speedup total de **4.98 con 4 procesos** y **5.27 con 16**.

## 5.6 Ley de Amdahl

Si una fracción *p* del trabajo se puede paralelizar y el resto (1 − *p*) no, el speedup máximo con *n* procesos es

S(n) = 1 / ((1 − p) + p / n)

y nunca pasa de 1 / (1 − p) aunque *n* crezca sin límite. En este programa la parte "no paralelizable" no es solo código secuencial (leer el REPO, arrancar procesos, escribir el JSON) sino sobre todo el **límite por sitio**: es un recurso compartido por todos los procesos, así que se comporta como una parte serial.

Despejando *p* del speedup medido con 16 procesos (tomando 1 proceso como base, para aislar el nivel 1):

S(16) = 1115.7 / 355.9 = 3.13, entonces p = (1 − 1/3.13) / (1 − 1/16) = **0.73**

Con ese *p*, el speedup máximo teórico del nivel 1 es 1 / (1 − p) = **3.7**, o sea un tiempo mínimo de 1115.7 / 3.7 ≈ **305 s**. Las mejores corridas medidas (311.6 s y 312.3 s) están prácticamente en ese mínimo. Sumando el aporte de los hilos, el speedup total no puede pasar de ≈ 1.68 × 3.7 ≈ **6.1** contra la secuencial, aunque se usen muchos más procesos. Esto coincide con el piso que pone el límite por sitio (5.4): por más procesos que se agreguen, el tiempo no baja de ahí. Para bajarlo habría que subir los límites por sitio, que es justo lo que no se quiere hacer para no saturar a las tiendas.

## 5.7 Conclusiones

- **El programa está limitado por la red, no por la CPU.** La versión secuencial pasa casi todo el tiempo esperando respuestas (≈ 2.2 s por solicitud).
- **Los hilos (niveles 2 y 3) dan un speedup de 1.68 con un solo proceso**, por eso la eficiencia sale mayor que 1 con 1, 2 y 4 procesos.
- **Los procesos (nivel 1) mejoran hasta 4 procesos** (speedup total 4.98); después la curva se aplana porque el límite por sitio actúa como la parte serial de la Ley de Amdahl (p ≈ 0.73, máximo ≈ 3.7× para el nivel 1).
- **Más procesos también significan más fallas en HLTB:** con 4 o más procesos el sitio empieza a devolver búsquedas vacías.
- **Configuración recomendada para la corrida automática: 4 procesos.** Es donde se obtiene casi todo el speedup (4.98 de 5.27); 16 procesos solo ahorran ≈ 20 s más y generan más fallas. Como la actualización corre cada 12 horas, ahorrar segundos no importa tanto como la calidad de los datos. En GitHub Actions no hay que configurar nada: `WORKERS_JUEGOS` toma por defecto el número de núcleos, y la máquina de Actions (`ubuntu-latest`) tiene 4.
