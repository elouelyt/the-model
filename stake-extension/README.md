# Stake Combo Loader

Extensión de Chrome que **rellena el talón de Stake** con las selecciones de un enlace del panel
(botones "Abrir en Stake" y "Stake ↗" de la pestaña NBA). Tú solo escribes el importe y apuestas.

## Instalar (una vez)
1. En Chrome abre `chrome://extensions`.
2. Activa **Modo de desarrollador** (arriba a la derecha).
3. Pulsa **Cargar descomprimida** y elige esta carpeta (`stake-extension`).
4. Instálala en el perfil de Chrome desde el que abres el panel y apuestas en Stake.

## Cómo funciona
- El enlace del panel lleva las selecciones en la parte `#oj=...` de la dirección (nunca se envía a ningún servidor).
- Al abrir Stake, la extensión escribe esas selecciones en el talón de la pestaña antes de que cargue la página.
- Stake actualiza las cuotas en directo: revisa que sigan siendo buenas antes de apostar.

## Qué NO hace
- No hace clic, no apuesta, no envía nada y no hace peticiones de red.
- Solo tiene permiso para `stake.com`.
- Los enlaces dejan de servir cuando empieza el partido.
