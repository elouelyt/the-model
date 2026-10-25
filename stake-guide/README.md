# Stake Bet Guide

Extensión de Chrome/Brave con dos partes:

1. **Panel lateral** (fuera de la página de Stake): lista tus combinadas, descifradas en tu navegador con la contraseña del panel.
2. **Resaltador** (en la página de Stake): marca lo que hay que pulsar, paso a paso. **Tú haces todos los clics.**

## Instalar (una vez)
1. `chrome://extensions` (o `brave://extensions`) → activa **Modo de desarrollador**.
2. **Cargar descomprimida** → elige esta carpeta (`stake-guide`).
3. Pulsa el icono de la extensión: se abre el panel lateral. Escribe la contraseña del panel (se guarda solo en este navegador).

## Secciones del panel lateral
Tres botones arriba: **NBA** (combinadas de la pestaña NBA), **NFL** (las de la pestaña NFL) y **Total** (combinadas que mezclan piernas de NBA y NFL). El resaltado en Stake funciona igual en las dos ligas (nombres de mercado de NFL en español de Stake: Yardas por Pases, Yardas por acarreo, Yardas de recepción, Recepciones, Intentos de acarreo…).

## Uso
1. En el panel lateral pulsa una pierna (por ejemplo "Max Christie Menos de 3,5 Asistencias").
2. La **misma pestaña** de Stake va al partido (se reutiliza siempre; Stake guarda el talón por pestaña, así que las selecciones de la combinada se acumulan ahí. Si no hay ninguna pestaña de Stake abierta, abre una y la reutiliza después). Se marca en amarillo **Apuestas al Jugador**; púlsala.
3. Se marca el **jugador**; púlsalo para desplegarlo.
4. Baja tú hasta el mercado (la extensión no mueve la página): al verlo sale en **amarillo**. Si la línea que muestra Stake no es la tuya sale en **naranja**; abre la lista de líneas y se marca en **verde** la que toca.
5. Con la línea correcta se marcan en verde la línea y **Sobre/Debajo con su cuota**. Púlsalo.
6. Vuelve al panel lateral y pasa a la siguiente pierna.

## Cambios
- 1.2.1: el panel lateral muestra en qué paso va el resaltador y qué no encuentra (por ejemplo «No encuentro a X entre los N jugadores de la lista», «no tiene ahora el mercado Y»); nombres de jugador tolerantes (Jr./Sr./II, puntos y acentos).
- 1.2.0: secciones NBA / NFL / Total, enlaces por deporte y resaltado para NFL (posiciones QB/WR/TE... y mercados de NFL).
- 1.1.0: reutiliza la misma pestaña de Stake (antes abría una nueva cada vez y el talón se perdía; faltaba el permiso para leer la dirección de la pestaña). Si actualizas desde la 1.0.0, en `chrome://extensions` pulsa **Recargar** en la extensión (el permiso nuevo puede pedir confirmación).

## Qué hace y qué no
- Lee el texto visible de la página y pinta con la API de resaltado de CSS (`CSS.highlights`): no añade ni cambia elementos, clases ni atributos (medido: 0 cambios en la página al pintar).
- No hace clic, no escribe en campos, no apuesta y no hace peticiones de red desde la página de Stake.
- No mueve la página: el desplazamiento lo haces tú.
- El panel lateral descarga `data/nba_picks.enc` de GitHub (cifrado) y lo descifra aquí; la contraseña nunca sale del navegador.
- Las cuotas del panel son las de la última tanda: mira la cuota real que muestra Stake antes de apostar.

## Riesgo (honesto)
Stake no publica qué detecta. Esta extensión no modifica la página y no automatiza clics, pero lee su contenido y usa una API del navegador que el código de Stake podría consultar (`CSS.highlights`, hojas de estilo adjuntas). No hay garantía de que no sea detectable.
