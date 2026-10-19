# Actividad de Discord (beta, fase 0)

Una **Actividad** es una pantalla web que Discord abre dentro de la app (PC y móvil). La idea final: el tablero de los QTE con
botones y tiempos medidos en tu pantalla (sin depender de mensajes ni reacciones) y el canal del evento a la vista, para no
cambiar de canal en pleno timing. **Esta versión (0.5.0) es la fase 0, un prototipo para comprobar que todo funciona con tus
jugadores**: espeja el canal en solo lectura, muestra quién está conectado y mide la conexión de cada uno. Todavía no cambia
cómo se juegan los QTE.

Plan completo y fases: ver el final de este documento.

## Cómo funciona
- La app abre un servidor web en tu PC (puerto 8765) dentro del mismo proceso del bot.
- Discord descarga la Actividad desde internet, así que la app abre un **túnel gratuito de Cloudflare** (`cloudflared`, se
  descarga una vez en `tools\`) que da una dirección pública `https://algo.trycloudflare.com`. **Esa dirección cambia cada vez
  que inicias el bot**, y hay que pegarla en el Developer Portal (paso 3).
- Cada jugador entra con su cuenta de Discord (OAuth2, solo el permiso «identify»). El bot comprueba que sea miembro del
  servidor y pueda ver el canal del evento: si no, no ve nada.
- El cliente y el servidor sincronizan relojes (ping/pong tipo NTP) y la app muestra el ida y vuelta y el desfase de cada
  jugador. Es la base para mostrar cosas a la misma hora a todos y medir reacciones en el cliente.

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
- Escribir desde la Actividad llegará en la fase 1 (publicará con un webhook a nombre del jugador).
- Si el servidor supera los 25 miembros hará falta verificar la aplicación en Discord.

## Fases previstas
0. **Prototipo y puerta de decisión** (esta versión): servidor, túnel, autenticación, sincronización de reloj, espejo de solo
   lectura. Se prueba con 2–3 testers en PC y móvil.
1. Espejo con escritura (webhook) y paneles de HP/jefe.
2. QTE sencillos dentro de la Actividad (evade/parry/adapt) con tiempos medidos en el cliente y resumen único en Discord.
3. Resto de modos (grupo, combo, dirección, contraataque…) y paleta de poderes.
4. Pulido, antitrampas y documentación.
