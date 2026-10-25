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

## Registro
- 2026-10-25: creada la carpeta; ideas 02-08 con código; 01 en producción como familia de papel; 05 descartada con datos;
  tareas programadas nuevas; primer análisis de 6 vídeos.
