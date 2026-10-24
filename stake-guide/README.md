# Stake Bet Guide

Extensión de Chrome/Brave con dos partes:

1. **Panel lateral** (fuera de la página de Stake): lista tus combinadas, descifradas en tu navegador con la contraseña del panel.
2. **Resaltador** (en la página de Stake): marca lo que hay que pulsar, paso a paso. **Tú haces todos los clics.**

## Instalar (una vez)
1. `chrome://extensions` (o `brave://extensions`) → activa **Modo de desarrollador**.
2. **Cargar descomprimida** → elige esta carpeta (`stake-guide`).
3. Pulsa el icono de la extensión: se abre el panel lateral. Escribe la contraseña del panel (se guarda solo en este navegador).

## Uso
1. En el panel lateral pulsa una pierna (por ejemplo "Max Christie Menos de 3,5 Asistencias").
2. La pestaña va al partido en Stake. Se marca en amarillo **Apuestas al Jugador**; púlsala.
3. Se marca el **jugador**; púlsalo para desplegarlo.
4. La página baja sola hasta el mercado: **mercado en amarillo**. Si la línea que muestra Stake no es la tuya sale en **naranja**; abre la lista de líneas y se marca en **verde** la que toca.
5. Con la línea correcta se marcan en verde la línea y **Sobre/Debajo con su cuota**. Púlsalo.
6. Vuelve al panel lateral y pasa a la siguiente pierna.

## Qué hace y qué no
- Lee el texto visible de la página y pinta con la API de resaltado de CSS (`CSS.highlights`): no añade ni cambia elementos, clases ni atributos (medido: 0 cambios en la página al pintar).
- No hace clic, no escribe en campos, no apuesta y no hace peticiones de red desde la página de Stake.
- Lo único que hace de forma automática en la página es un desplazamiento hasta el mercado.
- El panel lateral descarga `data/nba_picks.enc` de GitHub (cifrado) y lo descifra aquí; la contraseña nunca sale del navegador.
- Las cuotas del panel son las de la última tanda: mira la cuota real que muestra Stake antes de apostar.

## Riesgo (honesto)
Stake no publica qué detecta. Esta extensión no modifica la página y no automatiza clics, pero lee su contenido y usa una API del navegador que el código de Stake podría consultar (`CSS.highlights`, hojas de estilo adjuntas). No hay garantía de que no sea detectable.
