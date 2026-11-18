# Idea 32 — Edge del pick de tenis contra la cuota de Stake

Solo papel. 42 picks individuales liquidados con cuota de Stake (de 2026-08-26 a 2026-11-04).
Filtro actual: edge = prob. del modelo − media de casas ≥ 3%. Alternativa: prob. del modelo − 1/cuota de Stake ≥ 3%.
ROI a 1 u plana a la cuota de Stake; IC 95 % por bootstrap (con tan pocos picks el intervalo es muy ancho).

| Grupo | Picks | Aciertos | ROI | IC 95 % del ROI |
|---|---|---|---|---|
| Todos (regla actual) | 42 | 27 (64%) | +16,1 % | -11,2 % a +41,4 % |
| Se quedarían con la regla Stake | 39 | 25 (64%) | +17,2 % | -10,9 % a +44,5 % |
| Se caerían con la regla Stake | 3 | 2 (67%) | +2,7 % | — |

Stake pagó por debajo de la media de casas en 32 de 42 picks; edge medio: +14,1 % contra la media, +13,3 % contra Stake.

## ¿Qué probabilidad acertó mejor en estos mismos picks? (Brier, más bajo = mejor)

| Probabilidad | Brier |
|---|---|
| Modelo (la que se publica, ya mezclada con el mercado) | 0.2364 |
| Media de casas (con margen) | 0.2341 |
| Stake (1/cuota, con margen) | 0.2288 |

## Picks que se caerían

| Día | Jugador | Cuota Stake | Prob. modelo | Edge media | Edge Stake | Resultado |
|---|---|---|---|---|---|---|
| 2026-09-07 | Frances Tiafoe | 1.62 | 63% | +3,6 % | +1,6 % | ganó |
| 2026-10-29 | Taylor Fritz | 1.46 | 70% | +3,0 % | +1,2 % | ganó |
| 2026-11-01 | Brandon Nakashima | 1.61 | 65% | +3,1 % | +2,7 % | perdió |
