# Actividad de Discord (beta)

Una **Actividad** es una pantalla web que Discord abre dentro de la app (PC y móvil). Es el tablero de los QTE: botones grandes
con el tiempo medido **en tu pantalla** (sin depender de mensajes ni reacciones), el canal del evento a la vista y una caja
para escribir, para no cambiar de canal en pleno timing.

**Versión 0.7.0:** se puede **escribir** y **responder QTE con botones** (con la barra de tiempo y sus ventanas), ver el **HP, el
jefe y tus cargas**, y las imágenes salen por la propia app. Los QTE siguen funcionando también por el chat de siempre.

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
- **Barra de tiempo:** muestra todo el QTE con sus zonas: verde = evade (hasta el límite), naranja = parry, oscuro = ventana de
  Black Flash (solo es la ventana: luego hay una tirada de suerte), y un cursor que arranca donde va el reloj del motor.
  Respeta el modo REVENGE (ventana de parry movida).
- **Estado:** barra del jefe, HP de los jugadores, tu HP, tus cargas de Power 1 y 2 (brillan al llegar al 100 %) y tu racha de evades.
- **Personajes:** el selector de abajo es tu *personaje activo*: lo que escribes y los botones actúan como ese personaje
  (poderes, registro, etc.), no solo cambia el nombre. La foto de cada personaje se recuerda entre sesiones, sin peticiones extra.
  Tupperbox sigue sirviendo para el chat normal; la Actividad no lo usa (publica con su webhook: un mensaje por mensaje).
- Combo, dirección, falso y Cadena BF **muestran el panel pero se responden por el chat** (un aviso lo dice).
- El espejo muestra ahora respuestas, reacciones, stickers y embeds completos (imagen, GIF de Tenor/Klipy como clip silencioso,
  campos, pie).

## Puesta en marcha (una sola vez)
En <https://discord.com/developers/applications> → tu aplicación (la del bot principal):
1. **Activities**: actívalas («Enable Activities»). Discord crea el comando de entrada «Launch».
2. **OAuth2 → Redirects**: añade `https://127.0.0.1` (lo pide el flujo de autorización).
3. **Activities → URL Mappings**: en la raíz `/` pon la dirección del túnel **sin** `https://` (la app la muestra y tiene el
   botón «Copiar dirección»). **Ya no hace falta** añadir `/cdn` ni `/media`: las imágenes pasan por la propia app. Solo
   la aplicación del **bot principal** necesita la Actividad; los bots auxiliares no se tocan.
4. **OAuth2 → Client Secret**: «Reset Secret», cópialo y pégalo en *Configuración → Actividad de Discord → Client Secret*.
5. **App Testers**: mientras la app no esté verificada, solo la ven tú, tu equipo y los *testers* (hasta 100), y solo en
   servidores de **menos de 25 miembros**. Añade a cada jugador como tester (debe aceptar la invitación y activar el ajuste de
   pruebas de Actividades en su Discord).

## Dirección fija con Tailscale Funnel (opcional, recomendado)
El túnel de Cloudflare cambia de dirección cada vez, y Discord no tiene API para cambiar los URL Mappings, así que habría que
pegarla a mano en cada inicio. **Tailscale Funnel** (gratis para uso personal) da una dirección fija
`equipo.tailXXXX.ts.net` **sin página de aviso** (ngrok gratis sí la pone, y deja la Actividad en blanco dentro de Discord).
1. Instala Tailscale desde <https://tailscale.com/download> e inicia sesión.
2. En <https://login.tailscale.com/admin/dns> activa **MagicDNS** y **HTTPS Certificates**.
3. En la app: *Configuración → Actividad de Discord → Dirección → Tailscale Funnel*, y pulsa **Comprobar Tailscale**: te dice
   si está listo y cuál será tu dirección. Guarda e inicia el bot.
4. La primera vez, Tailscale pide permitir Funnel: la app muestra un enlace (`login.tailscale.com/f/funnel…`); ábrelo, aprueba
   y reinicia la Actividad.
5. Pega la dirección (`equipo.tailXXXX.ts.net`) en URL Mappings `/` **una sola vez**.
Al detener el bot la app apaga el Funnel (nada queda público). Con Funnel, el servidor de la Actividad es accesible desde
internet en esa dirección: entrar exige iniciar sesión con Discord y ser miembro del servidor, el acceso de prueba local
está bloqueado fuera de tu PC y `/media` solo sirve imágenes de Discord. Sin Tailscale, deja «Túnel rápido de Cloudflare».

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
1. **Escribir + QTE básico** (0.6.0): caja de escribir con identidad, botones evade/parry/adapt/ataque con tiempo
   medido en el cliente, render mejorado del espejo.
2. **Estado, barra con ventanas, personajes, imágenes y enlace fijo** (0.7.0).
3. Resto de modos (combo, dirección, falso, Cadena BF…) y botones de poderes con medición propia.
4. Pulido, antitrampas y documentación.

## Qué falta comprobar en esta versión
- Que escribir con webhook salga con el nombre/foto correctos y sin duplicar mensajes, y cómo se siente el teclado en móvil.
- Que los resultados de un QTE respondido con botón coincidan con lo esperado (compáralo con un QTE respondido por el chat).
- Imágenes y GIF (avatares, adjuntos, Klipy/Tenor): ahora salen por la app; si algo sigue sin verse, dímelo.
