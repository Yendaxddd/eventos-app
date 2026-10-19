# Actividad de Discord (beta, fase 1)

Una **Actividad** es una pantalla web que Discord abre dentro de la app (PC y móvil). Es el tablero de los QTE: botones grandes
con el tiempo medido **en tu pantalla** (sin depender de mensajes ni reacciones), el canal del evento a la vista y una caja
para escribir, para no cambiar de canal en pleno timing.

**Versión 0.6.0 (fase 1):** se puede **escribir** desde la Actividad y **responder QTE con botones**. Los QTE siguen funcionando
también por el chat de siempre, para quien no use la Actividad.

## Cómo funciona
- La app abre un servidor web en tu PC (puerto 8765) dentro del mismo proceso del bot.
- Discord descarga la Actividad desde internet, así que la app abre un **túnel gratuito de Cloudflare** (`cloudflared`, se
  descarga una vez en `tools\`) que da una dirección pública `https://algo.trycloudflare.com`. **Esa dirección cambia cada vez
  que inicias el bot**, y hay que pegarla en el Developer Portal (paso 3).
- Cada jugador entra con su cuenta de Discord (OAuth2, solo el permiso «identify»). El bot comprueba que sea miembro del
  servidor y pueda ver el canal del evento: si no, no ve nada.
- El cliente y el servidor sincronizan relojes (ping/pong tipo NTP) y la app muestra el ida y vuelta y el desfase de cada
  jugador. Es la base para mostrar cosas a la misma hora a todos y medir reacciones en el cliente.

## Jugar desde la Actividad
- **Escribir:** la caja de abajo publica en el canal del evento **con tu nombre y tu foto** (por el webhook del bot, sin
  menciones/pings). Si tienes personajes registrados aparece un selector para escribir como uno de ellos (con la foto con la
  que Tupperbox lo mostró por última vez). El bot trata lo escrito como cualquier mensaje del chat: `*attack*`, frases entre
  comillas, etc. funcionan igual. Sin permiso «Gestionar webhooks» el bot lo publica como `**Nombre:** texto`.
- **QTE:** cuando aparece uno, el panel de abajo se enciende con una barra de tiempo. Si es para ti, **Evade** y **Parry** se
  activan. Se miden desde que el QTE se pinta en tu pantalla; el servidor suma la mitad del ida y vuelta y rechaza tiempos
  imposibles (menos de 80 ms) o más largos que el tiempo real. **Adapt** y **Ataque** (contraataque) funcionan siempre, igual
  que escribir `*adapt*` / `*attack*`.
- **Teclas (PC):** `E` evade, `P` parry, `A` adapt, `Q` ataque; mientras escribes en la caja, `Alt`+letra. `Esc` sale de la caja.
- En el canal, la respuesta aparece con ✅/❌ en el mensaje del QTE, como siempre, y los mensajes de resultado de siempre.
- **Por ahora solo** los QTE normales (individual y de grupo). Combo, dirección, falso, Cadena BF, poderes y dominio siguen
  por el chat (también puedes escribirlos en la caja: `*power1*`, etc. pasan por el mismo camino que el chat, pero sin la
  medición del cliente).
- El espejo muestra ahora respuestas, reacciones, stickers y embeds completos (imagen, GIF de Tenor/Klipy como clip silencioso,
  campos, pie).

## Puesta en marcha (una sola vez)
En <https://discord.com/developers/applications> → tu aplicación (la del bot principal):
1. **Activities**: actívalas («Enable Activities»). Discord crea el comando de entrada «Launch».
2. **OAuth2 → Redirects**: añade `https://127.0.0.1` (lo pide el flujo de autorización).
3. **Activities → URL Mappings**: en la raíz `/` pon la dirección del túnel **sin** `https://` (la app la muestra y tiene el
   botón «Copiar dirección»). Añade también `/cdn` → `cdn.discordapp.com` y `/media` → `media.discordapp.net` (imágenes).
4. **OAuth2 → Client Secret**: «Reset Secret», cópialo y pégalo en *Configuración → Actividad de Discord → Client Secret*.
5. **App Testers**: mientras la app no esté verificada, solo la ven tú, tu equipo y los *testers* (hasta 100), y solo en
   servidores de **menos de 25 miembros**. Añade a cada jugador como tester (debe aceptar la invitación y activar el ajuste de
   pruebas de Actividades en su Discord).

## Cada evento
1. En la app: marca *Activar la Actividad*, guarda e inicia el bot. Espera a ver «● Túnel listo: …».
2. Pega esa dirección en URL Mappings `/` (paso 3) y guarda.
3. Los jugadores abren la Actividad desde Discord (en un canal de voz: icono de cohete; en un canal de texto: «+» → Apps) y
   eligen la aplicación.
4. *Probar en este PC* abre la Actividad en tu navegador (solo desde este PC, no a través del túnel) para ver que carga.

## Qué falta comprobar (no se pudo probar sin Discord real)
- Que los testers vean la Actividad y puedan lanzarla en tu servidor (límite de 25 miembros, ajuste de testers).
- Cómo se ve y se comporta en **móvil** dentro de Discord (el diseño sí se probó en un navegador de móvil).
- Que `cloudflared` se descargue y abra el túnel en tu red (la app prueba dos protocolos antes de rendirse).
- Los permisos exactos del Developer Portal (los pasos de arriba salen de la documentación de Discord; si algo se llama
  distinto, dímelo y lo corrijo).

## Qué hace falta de Discord y qué no
- No se puede incrustar el canal real de Discord dentro de la Actividad: se hace un **espejo** (el bot ya lee los mensajes).
- Si el servidor supera los 25 miembros hará falta verificar la aplicación en Discord.

## Fases previstas
0. Prototipo y puerta de decisión (0.5.0): servidor, túnel, autenticación, reloj, espejo de solo lectura.
1. **Escribir + QTE básico** (0.6.0, esta versión): caja de escribir con identidad, botones evade/parry/adapt/ataque con tiempo
   medido en el cliente, render mejorado del espejo.
2. Paneles de HP/jefe y estado del jugador.
3. Resto de modos (combo, dirección, falso, Cadena BF…) y paleta de poderes con medición propia.
4. Pulido, antitrampas y documentación.

## Qué falta comprobar en esta versión
- Que escribir con webhook salga con el nombre/foto correctos y sin duplicar mensajes, y cómo se siente el teclado en móvil.
- Que los resultados de un QTE respondido con botón coincidan con lo esperado (compáralo con un QTE respondido por el chat).
- Los GIF de otros sitios (Klipy/Tenor) llegan por el proxy de Discord; si alguno no se ve dentro de la Actividad, dímelo.
