# Registro automático de apuestas (versión 1.3.0 de la extensión)

La extensión lee el cupón de Stake (solo lectura) y, cuando Stake confirma que has apostado, guarda esa apuesta
(piernas, cuota real y cantidad) como un archivo en el repositorio **privado** `elouelyt/the-model-bets`.
Cada mañana el PC del modelo lo descarga, liquida las apuestas con ESPN y las muestra en la pestaña «Resultados».

## Una sola vez
1. Crear el repositorio privado `the-model-bets` en GitHub (https://github.com/new), marcando «Private» y «Add a README file».
2. Crear un token: GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token.
   - Repository access: *Only select repositories* → `the-model-bets`.
   - Permissions → Repository permissions → **Contents: Read and write** (nada más).
   - Caducidad: la máxima. Copiar el token (`github_pat_...`).
3. En el PC donde apuestas: sustituir la carpeta de la extensión por esta (`nuevas_ideas/stake-guide-registro`) o cargarla de nuevo en
   `chrome://extensions` → «Cargar descomprimida», y recargar Stake (F5).
4. Abrir el panel lateral → «Registro de apuestas» → pegar el token → «Guardar token».

## Cómo comprobar que funciona
Tras la primera apuesta, el panel muestra «Apuesta registrada» y «Enviadas: 1». Si aparece «Pulsaste Apostar pero no vi la confirmación»,
Stake cambió algo: avísame y lo ajusto (las apuestas no confirmadas no se registran).
