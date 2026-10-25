# Idea 05 - Sinergias entre compañeros (DESCARTADA con datos, 25/10/2026)

**Origen:** vídeo "Team Synergies" (s6bkSm7X2Zc). Dice que dos compañeros se mueven en la misma dirección el
60-70 % de las veces (asistencias del base -> puntos del anotador) o en direcciones opuestas (reparto de puntos
entre dos estrellas), con muestras de 40-70 partidos por pareja.

**Qué se midió** (`pairs_analysis.py`, datos de ESPN de toda la temporada regular 2025-26, 30 equipos, 382 jugadores,
`espn_minutes.py` los descarga): para cada pareja de compañeros (top-8 en minutos por equipo), dirección de cada uno
respecto a su mediana de temporada (línea = mediana redondeada a x.5), partidos con >= 10 min los dos, y la
correlación phi entre los dos "over".

| Tipo de pareja | Pares | Partidos | phi medio |
|---|---|---|---|
| asistencias del base de cada equipo -> puntos de compañero | 111 | 6.018 | **+0,057** |
| asistencias de cualquiera -> puntos de otro | 804 | 41.628 | +0,043 |
| puntos de dos compañeros (todos los pares) | 402 | 20.814 | **-0,010** |
| puntos de los dos máximos anotadores de cada equipo | 16 | 837 | +0,005 |

**Selección a posteriori (lo que hace el vídeo):** elegir las mejores parejas de la primera mitad y mirarlas en la segunda.

| Tipo | Mejores de la 1a mitad (phi 1a) | Esas mismas en la 2a mitad |
|---|---|---|
| asistencias -> puntos (62 mejores de 628) | +0,386 | **+0,087** |
| puntos -> puntos (31 mejores de 314) | +0,326 | **+0,001** |

Por puro azar (111 pares sin relación, simulados) el mejor par ya sale con phi ~ +0,35 (rango +0,23 a +0,53).

**Conclusión:** casi todo el "efecto sinergia" del vídeo es ruido de elegir las mejores parejas después de verlas. Queda un
efecto real pequeño en asistencia -> puntos (phi ~ +0,05, que equivale a +5 % relativo en la probabilidad conjunta de dos
overs) y NINGUNO en el reparto de puntos entre compañeros. Parejas que sí repiten en las dos mitades (candidatas, no
probadas fuera de muestra): Mitchell->Tyson (CLE), Rollins->Kuzma (MIL), Hart->Bridges (NY), Miller->Dunn (LAC),
Hartenstein->J. Williams (OKC).

**Qué implica para Stake:** el constructor de múltiples del mismo partido de Stake ya descuenta/bloquea combinaciones y
aplica un margen de ~9 % a 2 selecciones válidas (ver idea 02); con una correlación real de +0,05 no alcanza para ganar
ese margen. No se crea familia de seguimiento. Se reabre si en la idea 02 el acierto real supera claramente el esperado
bajo independencia.
