# Idea 31 — Validación honesta del modelo de tenis

Solo medición (no cambia el modelo ni los picks). Generado por `run.py` con los CSV de Tennismylife/TML-Database (formato Sackmann; Sackmann ya no está en GitHub).
Una fila por partido; Brier y log-loss: cuanto más bajos, mejor probabilidad. Sin cuotas: no compara con el mercado.

## Walk-forward (entrenar con años anteriores, probar en el siguiente)

| Año de prueba | Partidos | Acierto modelo | Acierto mejor clasificado | Brier modelo | Brier fórmula puntos | Log-loss modelo |
|---|---|---|---|---|---|---|
| 2021 | 2622 | 63,9 % | 63,8 % | 0,2183 | 0,2215 | 0,6247 |
| 2022 | 2801 | 64,9 % | 64,9 % | 0,2166 | 0,2188 | 0,6219 |
| 2023 | 2849 | 63,6 % | 63,7 % | 0,2193 | 0,2233 | 0,6278 |
| 2024 | 2909 | 64,2 % | 64,1 % | 0,2194 | 0,2241 | 0,6275 |
| 2025 | 2753 | 64,6 % | 64,5 % | 0,2195 | 0,2249 | 0,6285 |
| 2026 | 130 | 54,6 % | 55,4 % | 0,2503 | 0,2624 | 0,6967 |

## Modelo de producción (lr_model.json, entrenado 2018-2024) en años que nunca vio

| Año | Partidos | Acierto | Brier | Log-loss |
|---|---|---|---|---|
| 2025 | 2753 | 64,6 % | 0,2195 | 0,6286 |
| 2026 | 130 | 54,6 % | 0,2504 | 0,6971 |

## Calibración — walk-forward 2026

| Prob. del favorito | Partidos | Prob. media dada | Ganó de verdad |
|---|---|---|---|
| 50%-55% | 29 | 52,5 % | 41,4 % |
| 55%-60% | 31 | 57,3 % | 48,4 % |
| 60%-65% | 29 | 62,4 % | 69,0 % |
| 65%-70% | 14 | 67,3 % | 64,3 % |
| 70%-75% | 12 | 71,8 % | 50,0 % |
| 75%-80% | 9 | 77,3 % | 55,6 % |
| 80%-100% | 6 | 84,6 % | 66,7 % |

## Calibración — producción 2025

| Prob. del favorito | Partidos | Prob. media dada | Ganó de verdad |
|---|---|---|---|
| 50%-55% | 616 | 52,5 % | 54,5 % |
| 55%-60% | 495 | 57,4 % | 56,2 % |
| 60%-65% | 436 | 62,5 % | 62,6 % |
| 65%-70% | 396 | 67,5 % | 66,9 % |
| 70%-75% | 329 | 72,4 % | 72,0 % |
| 75%-80% | 223 | 77,4 % | 78,0 % |
| 80%-100% | 258 | 84,8 % | 83,3 % |

## Calibración — producción 2026

| Prob. del favorito | Partidos | Prob. media dada | Ganó de verdad |
|---|---|---|---|
| 50%-55% | 29 | 52,5 % | 41,4 % |
| 55%-60% | 31 | 57,3 % | 48,4 % |
| 60%-65% | 29 | 62,3 % | 69,0 % |
| 65%-70% | 14 | 67,3 % | 64,3 % |
| 70%-75% | 12 | 71,7 % | 50,0 % |
| 75%-80% | 9 | 77,4 % | 55,6 % |
| 80%-100% | 6 | 84,7 % | 66,7 % |
