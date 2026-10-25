# Idea 01 - `prudente` (en marcha desde el 25/10/2026, vive dentro del seguimiento de producción)

Misma regla que las combinadas actuales pero restando 1,5 puntos a la probabilidad justa de cada pierna antes de aplicar
los filtros (`SHRINK = 0.015` en `scripts/nba_combos.py`). Solo papel: se guarda como familia `prudente` del seguimiento
en `data/nba_history/<fecha>.json` y no cambia las combinadas apostables.

Hipótesis: nuestra probabilidad (promedio de casas de referencia) puede estar algo inflada; exigir un colchón filtra piernas
con ventaja dudosa. Se mide en `RESULTADOS.md` (sección Idea 01) y en `data/nba_analysis.json` (`combos` con
`prudente` en `families`). Decisión a los 5-7 días: ¿acierta más / mejor ROI que las familias actuales?
