# NUEVAS IDEAS (índice vivo; se añade, no se borra)

Regla acordada con el usuario (25/10/2026): **ningún cambio nuevo toca lo que ya funciona.** Cada propuesta vive en su
carpeta `nuevas_ideas/ideas/NN_nombre/`, genera combinadas **de papel** con los mismos datos que producción y se
compara tras **5-7 días** de resultados reales. Lo que se aplique a producción se decide después, con los números.

## Cómo se usa
| Qué | Comando (desde la raíz del repo) |
|---|---|
| Generar las combinadas de papel de todas las ideas (tras cada tanda de producción) | `python nuevas_ideas/run_ideas.py` (o `... 03 04` para algunas) |
| Liquidar con ESPN y regenerar el informe | `python nuevas_ideas/settle_ideas.py` -> `nuevas_ideas/RESULTADOS.md` |
| Refrescar minutos/registros de ESPN (cada tanto, ~4 min) | `python nuevas_ideas/espn_minutes.py` |
| Probar la idea 02 sin guardar nada (incluye partidos empezados) | `IDEAS_TEST=1 python nuevas_ideas/ideas/02_sgm_mismo_partido/run.py` |

Tareas programadas **nuevas** (las de producción no se han tocado): `nuevas-ideas-tanda` (19:35 y 22:35, después de
las tandas NBA) y `nuevas-ideas-resultados` (10:40 aprox., después de `nba-resultados`). La idea 02 necesita el Chrome de
depuración con una pestaña de stake.com (igual que las tandas). Los historiales (`ideas/*/history`, `candidates`, `data`)
son locales y no se suben al repo.

## Tabla de ideas
| ID | Idea | Origen | Estado | Cómo se mide |
|---|---|---|---|---|
| 01 | `prudente`: probabilidad justa − 1,5 puntos por pierna | propuesta del asistente, aprobada por el usuario | **en marcha desde 25/10** (dentro del seguimiento de producción) | familia `prudente` en `RESULTADOS.md` |
| 02 | Combinadas del **mismo partido** con el precio del constructor de Stake (una sola comisión en vez de una por pierna) | prueba propia del 25/10 (ver hallazgos) | **código listo**, empieza con la tanda de la tarde del 25/10 | `02_sgm_mismo_partido`: acierto real vs esperado (independencia) y ROI; grupos EV>0 / EV<=0 |
| 03 | Solo **unders** | vídeo VCPvDRj2NVQ (playoffs: ~53,7 % unders en PrizePicks) | código listo | `03_unders` vs familias de producción |
| 04 | Filtro de **minutos** (mediana ≥ 28 min el año pasado) | vídeo qFL8T_BU6DA (snaps ≥ 40 % subían de 58 % a 65 % en NFL) | código listo | `04_minutos` |
| 05 | Sinergias entre compañeros | vídeo s6bkSm7X2Zc | **DESCARTADA con datos** | `ideas/05_sinergias_descartada/RESULTADO.md` |
| 06 | Win% mínimo **56 %** por pierna (hoy 54 %) | propuesta del asistente (más colchón) | código listo | `06_win56` |
| 07 | Combinadas de **2 piernas** | propuesta del asistente (menos margen y varianza) | código listo | `07_dos_piernas` |
| 08 | Apuestas **simples** (top EV y top probabilidad) | propuesta del asistente | código listo | `08_simples` |
| 09 | Quitar el margen con el método de la **potencia** (en vez del proporcional) | análisis del 25/10 de los unders | código listo | `09_devig_potencia` |

Cada combinada vale 1 unidad plana en el informe (la apuesta real de producción sigue siendo 0,25 u). El informe también
repite las familias de producción como referencia.

## Hallazgos medidos el 24-25/10/2026 (hechos, con el dato)
1. **API de precios de Stake** (`/_api/v1/graphql`, consulta `calculateSwishCustomBet(lines:[{outcomeId,lineType}])`,
   la misma que usa la web al montar un SGM; sin sesión): con una sola línea devuelve la cuota **sin margen** de Stake
   (p. ej. Booker puntos 23,5: 1,96 / 2,03, suma de probabilidades 100,3 %; la web muestra 1,80 / 1,87). Con varias líneas
   devuelve el precio de la múltiple del mismo partido y `invalidCombinations` (códigos 100/102/103 cuando no se puede
   combinar; ~1/3 de las parejas de jugadores distintos, sobre todo asistencias con puntos/rebotes). Los precios
   van en múltiplos de 0,05. **Usar un precio solo si `invalidCombinations` está vacío.**
2. **Margen del SGM** (precio / producto de cuotas sin margen, solo combinaciones válidas): 2 selecciones ≈ 0,90-0,96
   (margen 4-10 %; mismo equipo over/over 0,96, over/under 0,88; equipos distintos 0,93 / 0,90 / 0,88). Una múltiple normal
   de cuotas de la web acumula el margen de cada pierna (cada mercado de la web suma ~109 % en probabilidades).
3. **Pantalla vs API:** el constructor del lado web dio 2,95 para Booker puntos S + rebotes S (producto de cuotas web 2,90),
   3,50 para puntos S + asistencias S (API: 3,40 minutos después) y **3,95 para dos compañeros puntos S + puntos S (producto
   3,20), que NO he podido reproducir por API (0,96 del producto sin margen)**. Pendiente: repetir con partido sin empezar
   comparando pantalla y API con exactamente las mismas líneas (las cuotas se mueven y mi comparación pudo cruzar líneas distintas).
4. **"Combinación no soportada"** en la pantalla: Phoenix gana + Phoenix −8,5; puntos S + puntos+asist+rebotes S del mismo
   jugador. Stake bloquea las combinaciones muy correlacionadas.
5. **Sinergias**: ver idea 05 (phi ~ +0,05 asistencia->puntos, ~0 puntos->puntos; las mejores parejas de una mitad no se repiten).
6. **Minutos (día 23/10, 99 piernas)**: mediana ≥ 28 min acertó 29,4 % y < 28 min 41,9 %; es ruido de un solo día y se usa
   solo como motivo para el seguimiento de 7 días de la idea 04.
7. **Unders (día 23/10)**: Over 40,0 % (75 piernas), Under 34,1 % (44), esperado 51-52 % en ambos: un día no dice nada.
8. **Stake Shield** (seguro tipo flex de PrizePicks) existe pero las reglas de Stake **excluyen los player props**.
9. Los props de jugador incluyen la prórroga; si el jugador no pisa la pista la selección se anula (en SGM se anula toda la apuesta).
10. Entorno: el Chrome de depuración está oculto y no repinta; para automatizar hay que `Page.bringToFront` + `Emulation.setFocusEmulationEnabled`,
    y los clics CDP necesitan un `mouseMoved` antes de `mousePressed`.
11. **Simulación de 30 días con las 10 combinadas actuales** (probabilidad media 19,1 %, cuota media 6,2, EV calculado +17,7 %; 10 combinadas al día a 0,25 u, 4.000 simulaciones):

    | Si nuestra probabilidad por pierna está inflada en... | Beneficio medio 30 d | Rango (p10 a p90) | Prob. de acabar en pérdidas | Caída máx. típica | Racha típica sin acertar |
    |---|---|---|---|---|---|
    | 0 puntos (como la calculamos) | +13,1 u | −0,6 a +27,2 | 11 % | 5,9 u | 20 combinadas seguidas |
    | 1,5 puntos | +6,6 u | −6,4 a +19,8 | 26 % | 7,3 u | 22 |
    | 3 puntos | 0,0 u | −12,5 a +12,8 | 51 % | 9,5 u | 23 |

    Lectura: el EV de +17,7 % es muy sensible a la calidad de la probabilidad (cada 1,5 puntos de error por pierna recorta el beneficio a la mitad)
    y, aun siendo correcta, lo normal es pasar ~20 combinadas seguidas sin acertar (≈2 días). Por eso la idea 01 (`prudente`) y la medición de calibración
    importan más que añadir reglas nuevas. Script: simulación en este informe (reproducible con los `prob`/`odds` de `data/nba_picks.json`).
12. **Por qué fallan unders y rebotes (análisis del 25/10 con 324 piernas liquidadas, 23 y 24/10):**
    - El fallo no es "unders" ni "rebotes" en general. Las piernas **con probabilidad ≥ 54 %** (la regla de las combinadas) están **calibradas**:
      Over 52,0 % vs 56,0 % esperado (EV>1 %) y 70,6 % vs 57,6 % (EV≤1 %); Under 57,9 % vs 57,7 % y 54,3 % vs 57,9 %.
    - El grupo que falla es **Under, prob < 54 %, EV > 1 %: 60 piernas, 23,3 % de acierto vs 49,9 % esperado (−4,1 SE, ROI −52 %)**.
      Over con prob < 54 % y EV > 1 %: 95 piernas, 48,4 % vs 50,1 %: bien.
    - Por día: el 23/10 las piernas "de valor" acertaron 31,9 % (n=94) vs 51,6 % esperado (pipeline con los fallos de datos de ese día: cuotas
      de casas desactualizadas, marcadores -99900, alias de equipo); el 24/10, ya corregido, 51,4 % vs 51,4 % (calibradas, ROI +3,7 %), pero Under de valor
      35,7 % (n=42) vs Over de valor 61,9 % (n=63): el sesgo de lado persiste.
    - Mecanismo **no identificado**. No se ve movimiento de línea (cambio medio de cuota Stake −0,25 % y de prob. de referencia +0,08 pts en las Under de valor
      entre tandas). Hipótesis a probar: el quitar-margen proporcional sesga el lado "underdog"; se prueba en la idea 09.
    - Reservas: miré muchos cortes (lado, mercado, EV, casas, día), así que parte puede ser azar; por eso el informe diario repite la tabla
      de calibración (`RESULTADOS.md`, "Calibración de piernas") y no se cambia producción todavía.
    - Consecuencia práctica ya medible: las combinadas de producción NO usan piernas de prob < 54 %, así que no sufren este grupo; la tabla de
      apuestas simples del panel sí lo muestra (se podría ocultar `Under` con prob < 54 % en la tabla: candidato a probar como idea aparte).
13. **Objetivo del usuario (25/10): "65-70 %" y "salir con beneficios todos los días".** Se mide de tres formas en `RESULTADOS.md` (sección Objetivo):
    acierto por pierna, acierto de combinadas y días con beneficio. Cuentas de referencia (simulación, suponiendo que nuestras probabilidades fueran correctas):

    | Estrategia | Días en positivo | ROI esperado |
    |---|---|---|
    | Combinadas de 3 (como ahora), 10/día, pierna 57 % a 1,80 | 57 % | +6,9 % |
    | Combinadas de 2, 10/día | 42 % | +5,4 % |
    | Simples, 10 / 30 / 100 al día | 56 % / 59 % / 62 % | +2,4 % / +2,6 % / +2,5 % |
    | Simples de alta probabilidad (68 % a 1,42, margen incluido), 30/día | 34 % | −3,4 % |

    Con la probabilidad 3 puntos peor de lo calculado, todas bajan a 32-48 % de días en positivo y ROI negativo. Conclusiones: (a) ni siquiera con todo bien
    se gana todos los días (lo máximo realista es ~60 % de días en positivo); (b) más apuestas pequeñas suben algo la frecuencia de días en positivo;
    (c) un acierto del 65-70 % por pierna solo se consigue con piernas de cuota baja (prob. >= 62 %), y ahí el ROI sale negativo; (d) una combinada de 3 al 65 %
    exigiría piernas al 86,6 % (70 % -> 88,8 %). El camino es mejorar la calibración y medir cada día, no subir el acierto a costa de la cuota.
14. **Archivo permanente** (`archive.py`, `universe.py`, desde el 25/10): cada tanda guarda en `nuevas_ideas/archive/batches/<hora>/` (gzip, ~300 KB) las líneas completas
    de Stake y de las casas de referencia, que producción sobrescribe; `universe.py` baja los box scores de TODOS los jugadores y construye `archive/universe.jsonl.gz`
    (cada línea con su probabilidad de casas, cuota de Stake y resultado). Así cualquier regla nueva se prueba con miles de líneas en lugar de unas pocas jugadas.
    Una tanda típica tiene 446 líneas con casas de referencia (288 con 1 casa, 158 con 2; con BettingPros más). El informe `RESULTADOS.md` incluye la calibración del universo.

15. **NFL añadido (25/10):** misma metodología en `nfl/` (ver `CLAUDE.md`). Primera tanda: 13 partidos, 9.180 líneas de Stake, 510 de Pinnacle (477 con línea idéntica), 122 jugadas con EV >= 0,3 % y 3 combinadas apostables. Hay que calibrarlo igual que NBA antes de fiarse del EV (ver hallazgo 12).

16. **NFL replicado en el seguimiento (25/10):** ideas 03/06/07/08/09 corren también con NFL (`history_nfl`), `nfl_universe.py` y calibración NFL y de las combinadas mezcladas en `RESULTADOS.md`. Hay una familia nueva a vigilar: la pestaña **Combinadas** (mezcla NBA+NFL) con su propia liquidación (`scripts/mix_settle.py`).

## Los seis vídeos (resumen y utilidad para nosotros)
Todos son del mismo autor (vende un Discord de picks; sus cifras de beneficio no están verificadas). Transcripciones automáticas en inglés.
| Vídeo | Contenido | Se traslada a Stake |
|---|---|---|
| Eh4rzFEiYQ4 | Ranking de estrategias de PrizePicks | Valida lo que ya hacemos (prob. justa ≥ 54 %, volumen, apuesta pequeña, no mirar los últimos 5). Resto depende del pago fijo de PrizePicks |
| qFL8T_BU6DA | NFL: overs de WR3/WR4 con snaps ≥ 40 % y línea ≥ 1 yarda mejor que el consenso (BettingPros) | Idea 04 (minutos). La comparación con el consenso ya la hacemos con las casas de referencia |
| m16DQfGfAp0 | 8 mitos: boleto de 2 es el peor (break-even 57,7 %, 6 flex 54,2 %), tacos, últimos 5 (51,1 % over), 14,3 % se pierde/gana por 0,5 | Aclara que PrizePicks tiene pago fijo (en Stake cada cuota lleva margen) |
| q8zM0LJlJkA | Reto de 30 días con boletos de 6 flex en MLB: 185 boletos, 27 por un acierto, ROI 28 %, rachas de 10 días perdiendo | Muestra la varianza: con 3,5 % de acierto, 20 boletos seguidos sin acertar ocurre ~49 % de las veces. En nuestras combinadas de 3 (~18 % de acierto) las rachas son menores pero existen |
| VCPvDRj2NVQ | NBA playoffs: unders (55 % de 24.486 props de puntos), blowouts, ritmo | Idea 03 (en liga regular el propio autor cita ~51 % de unders) |
| s6bkSm7X2Zc | Sinergias NBA (asistencia -> puntos del mismo sentido, reparto de puntos en sentido opuesto) | Idea 05: descartada con datos |

## Ideas anotadas y NO implementadas todavía
- Pasar a Stake algún tipo de "revivals" (reutilizar piernas de combinadas muertas): no aplica, una apuesta de Stake no se puede reescribir.
- Aviso al móvil al publicar tanda y 30 min antes del primer partido; registro de apuestas pegando la ficha de "Mis Apuestas";
  chequeo de cuotas justo antes de apostar (están en `CLAUDE.md` > Pendiente).
- Si la idea 02 funciona: usar el precio del constructor también para elegir piernas (hoy se elige con cuota web vs casas).
- Medir CLV por familia (el log `quotes` ya lo permite) para ver qué idea compra mejor que el cierre.

## Idea 10 - Reembolso al descanso NBA (promo de Stake, 19/10/2026 - 30/06/2027)
Promo: apuesta SIMPLE previa al partido al ganador (incl. prórroga); si tu equipo va +16 al descanso y no gana, te devuelven la apuesta. Solo la primera apuesta por partido, usuario y hogar; no vale para combinadas; apostar a ambos equipos puede descalificar.
Medición (`ideas/10_reembolso_descanso/halftime_backtest.py`, ESPN, temporada 2025-26, 1.235 partidos): un equipo iba +16 al descanso en el 20,4 % de los partidos y perdió 12 veces (0,97 % de los partidos; 4,8 % de los líderes).
Apostando a un equipo al azar el reembolso ocurre ~0,5 % de las veces; apostando siempre al favorito sería algo más (~0,8 %, estimado, sin cuotas). Valor extra ~0,5-1 % de la apuesta: pequeño frente al margen del moneyline (~4 %). No convierte una apuesta sin valor en valor; solo suma a una que ya lo tenga.
Pendiente: comprobar si Stake expone el moneyline NBA en su API y compararlo con Pinnacle (liga 487, ya leída) para detectar valor real; entonces prueba en papel 5-7 días. Estado: medido, sin pruebas en papel todavía.

## Registro
- 2026-10-25 (noche): NFL en la web + pestaña Combinadas (NBA+NFL), consenso BettingPros visible, extensión 1.2.0 (NBA/NFL/Total), seguimiento NFL replicado.
- 2026-10-25 (tarde, 2): archivo permanente por tanda + universo con box scores (14); objetivo 65-70 % medido de 3 formas (13); ideas 03/04/06/09 arregladas; stake-guide 1.1.0.
- 2026-10-25 (tarde): liquidado el 24/10 a mano (las tareas de la mañana no se ejecutaron: la app estaba cerrada); análisis de unders/rebotes (hallazgo 12); idea 09 añadida; tabla de calibración de piernas en `RESULTADOS.md`.
- 2026-10-25: creada la carpeta; ideas 02-08 con código; 01 en producción como familia de papel; 05 descartada con datos;
  tareas programadas nuevas; primer análisis de 6 vídeos.
- 2026-10-25 (noche, 2): copia de seguridad fechada (`scripts/backup_data.py`), combinadas fijas se retiran si Stake quita una pierna, idea 10 (reembolso al descanso) medida.

## Idea 11 - Registro automático de las apuestas reales (2026-10-27)
Herramienta, no cambio de reglas. La extensión 1.3.0 (`nuevas_ideas/stake-guide-registro/`) lee el cupón de Stake (solo lectura) y, al confirmar Stake
la apuesta, la guarda en el repo privado `elouelyt/the-model-bets`. `scripts/real_bets.py` la descarga cada mañana (tarea `TheModel-Resultados`), la liquida
con ESPN (piernas anuladas fuera, cuota recalculada) y entra en «Mis apuestas reales» de la pestaña Resultados. Pendiente: crear el repo y el token
(`LEEME_REGISTRO.md`) y probar con la primera apuesta real. Probado: lectura del cupón en vivo y liquidación con un registro de prueba.

## Idea 12 - Del vídeo "betting explained" (youtube EPwzirlb2rI, 2026-10-27): qué se puede aprovechar
Vídeo de iniciación (programa deportivo patrocinado por DraftKings): momios, moneyline, spread, totales, parlays, unidades. No habla de valor esperado ni de ventaja.
Lo único aplicable, anotado como posible prueba (NO implementado):
- **Tamaño de la apuesta (unidad)**: 1-5 % del banco por apuesta, constante. Para el modelo (cuotas 5-7, acierto ~19 %) 1 % es lo prudente; hoy se apuesta ~0,25 $ sin banco definido.
- **Mercados de partido** (total de puntos, spread, moneyline) Stake vs Pinnacle sin margen, con el mismo método de valor que las piernas de jugador. Sería una prueba en papel de 5-7 días
  con combinadas de 2-3 patas de partidos distintos; ya lo cubre en parte la idea 10 (moneyline).
- Lo demás ya lo hace el modelo: anuladas/empates se quitan de la combinada y la cuota se recalcula; líneas con .5 (sin empate).
