# Actividad de Discord (beta)

Una **Actividad** es una pantalla web que Discord abre dentro de la app (PC y móvil). Es el tablero de los QTE: botones grandes
con el tiempo medido **en tu pantalla** (sin depender de mensajes ni reacciones), el canal del evento a la vista y una caja
para escribir, para no cambiar de canal en pleno timing.

**Versión 0.9.0:** interfaz nueva (diseño propio, todo en español), **botón flotante Esquivar → Parry con el temporizador encima**,
varios QTE a la vez **por prioridad y sin solaparse**, **menú**, **ajustes por jugador** (se guardan en el servidor y te siguen del
móvil al PC), **prueba de latencia** que ajusta tus tiempos y un **tutorial** con práctica. Los QTE siguen funcionando también por
el chat de siempre.

## Cómo funciona
- La app abre un servidor web en tu PC (puerto 8765) dentro del mismo proceso del bot.
- Discord descarga la Actividad desde internet, así que la app abre un **túnel gratuito de Cloudflare** (`cloudflared`, se
  descarga una vez en `tools\`) que da una dirección pública `https://algo.trycloudflare.com`. **Esa dirección cambia cada vez
  que inicias el bot**, y hay que pegarla en el Developer Portal (paso 3). Con **Tailscale Funnel** la dirección es fija.
- Cada jugador entra con su cuenta de Discord (OAuth2, solo el permiso «identify»). El bot comprueba que sea miembro del
  servidor y pueda ver el canal del evento: si no, no ve nada.
- El tiempo de cada respuesta lo mide **la pantalla del jugador** (desde que ve el QTE hasta que lo pulsa) y el servidor lo
  compensa con la red y el dispositivo de cada persona (más abajo), rechazando lo imposible (menos de 80 ms, o más que el tiempo
  real que lleva el QTE).

## Jugar desde la Actividad
- **Pantalla:** a la izquierda el equipo (vida de cada jugador) y quién está en la Actividad; en el centro el canal del evento
  (espejo en vivo, con respuestas, reacciones, stickers y embeds completos) con la barra del jefe encima y la caja para escribir
  debajo; a la derecha tu personaje (HP, cargas, racha) y tus botones. En pantallas medianas la columna del equipo pasa a un
  cajón (icono de personas); en el móvil queda el chat, una franja con tu HP y cargas, y los botones abajo.
- **Escribir:** la caja publica en el canal **con tu nombre y tu foto** (por el webhook del bot, sin pings). Con personajes
  registrados aparece un selector para escribir **como uno de ellos** (con la foto con la que Tupperbox lo mostró por última vez).
  El bot trata lo escrito como cualquier mensaje del chat: `*attack*`, frases entre comillas, etc. `Enter` envía y
  `Mayús+Enter` hace un salto de línea. Sin permiso «Gestionar webhooks» el bot lo publica como `**Nombre:** texto`.
- **QTE: un botón flotante por cada QTE que te toca.** Aparece en un sitio distinto de la pantalla cada vez, con el
  **temporizador encima** y debajo el número de prioridad y la dificultad:
  - Primero es **ESQUIVAR** (barra verde que se vacía hasta que se abre la ventana de parry). Al abrirse esa ventana, el botón
    **cambia a PARRY** y aparece en otro sitio: ahora la barra es la propia ventana del parry, con un cursor que avanza y una
    **banda violeta que marca la zona de Black Flash** (luego hay una tirada de suerte). Pulsar el parry antes o después de la
    ventana falla, igual que en el chat. Esquivar sigue valiendo (con la tecla `E`) hasta el final de *su* ventana; si quieres un
    botón pequeño para ello mientras el parry está abierto, actívalo en Ajustes («Mantener Esquivar durante el parry»).
  - **Varios a la vez:** se ordenan por urgencia (el que antes se acaba es el **1**, más grande y con un halo) y **nunca se
    solapan**: si la pantalla está llena, el último botón se hace más pequeño en vez de taparse con otro (y, en un caso extremo, se
    recolocan todos en filas). Cada botón responde exactamente a *su* QTE. Con «Un QTE a la vez» solo ves el más urgente y los
    demás esperan en cola (sus tiempos siguen corriendo). Si tienes el cajón de jugadores abierto, se cierra solo al llegarte un QTE.
  - **Grupal:** solo Esquivar (el bot rechaza el parry en un QTE de grupo).
  - **Combo:** el botón del paso que toca (Esquivar o Parry) con puntos de progreso; solo ves el siguiente cuando aciertas, como en
    el chat. **Dirección:** una cruz de 4 flechas y la flecha mostrada: pulsa la **opuesta**. **Cadena Black Flash:** espera
    («Prepárate») a que se abra su ventana y entonces solo ofrece el Parry; pulsarlo antes terminaría la cadena.
  - **Falso:** no tiene botón ni dice a quién va (igual que en el chat, donde no hay ping).
  - **Rescatar:** si el QTE es de otro jugador aparece arriba una pastilla «Rescatar a …» con su cuenta atrás y tus rescates
    restantes (máximo 2 por minuto); se apaga cuando pasa su ventana, porque un rescate tardío haría daño a quien rescata.
  - **Contraataque:** tras esquivar a tiempo aparece un botón rojo **ATACAR** con los segundos que quedan de la ventana.
  - El resultado se dice una vez, bajo el botón («¡Parry perfecto!», «¡BLACK FLASH!», «Fallaste»…) con el tiempo contado, y la
    pantalla destella en rojo si pierdes vida, en verde si te curas y en violeta con un Black Flash.
- **Botones siempre disponibles** (columna derecha, o franja inferior en el móvil): **Adaptar**, **Ataque**, **Poder 1 / 2** del
  personaje activo (nombre, % de carga, brillo al estar listo, enfriamiento o «en pausa» si espera a la próxima pelea) y
  **Dominio** si tienes uno.
- **Teclado (PC):** `Espacio` responde al QTE más urgente (esquivar o parry, según toque); `E` esquivar, `P` parry, `S` rescatar,
  flechas para el QTE de direcciones, `A` adaptar, `Q` ataque, `1`/`2` poderes, `3` dominio. Mientras escribes en la caja,
  `Alt`+tecla. `Esc` sale de la caja o vuelve atrás.
- **Aún por el chat:** Final Judgement, choque de dominios y juicios (puedes escribirlos en la caja: pasan por el mismo camino
  que el chat, pero sin medición del cliente).
- **Mini-ventana de Discord:** si Discord reduce la Actividad a una ventanita flotante, queda lo esencial (jefe, tu HP y cargas,
  botones) y los QTE siguen funcionando.

## Menú, ajustes, latencia y tutorial
- **Menú** (☰ arriba a la izquierda): Ajustes, Prueba de latencia, Tutorial y Ayuda. `Esc` o la flecha vuelven a donde estabas.
- **Ajustes por jugador** (engranaje): tema (oscuro, muy oscuro, alto contraste), colores para daltonismo (azul y naranja), tamaño
  del texto, espaciado, animaciones reducidas (los temporizadores siguen moviéndose), **tamaño de los botones**, **dónde aparecen**
  (al azar, abajo, izquierda o derecha: más cómodo con una mano), mantener Esquivar durante el parry, un QTE a la vez, sonidos y
  volumen (sintetizados, sin archivos), vibración, fotos de perfil, hora, cargar imágenes solas, panel del equipo y cuántos
  mensajes se guardan. Se aplican al momento, se guardan en el servidor por jugador (`data/activity_prefs.json`) y también en el
  navegador, para que la apariencia sea la correcta antes de conectar.
- **Prueba de latencia** (menú, o tocando el indicador de ms de arriba): mide **tu conexión** (24 mensajes de ida y vuelta: tiempo
  típico, saltos, pérdidas) y **tu dispositivo** (tocas un círculo al ritmo de un destello: una pantalla o un toque con retraso
  tocan *después* del destello). El resultado se guarda (`data/activity_latency.json`). El servidor mide además la red de cada
  jugador por su cuenta (un ping cada 2 s) y a cada respuesta le **suma** el retraso típico de la red (el QTE tardó en llegarte)
  y le **resta** el retraso de tu dispositivo (tu pantalla y tu toque tardan), con un tope de ±300 ms. Nadie puede comprar tiempo
  inflando un número: la red la mide el servidor y el dispositivo está limitado a 150 ms.
- **Tutorial:** por pasos (el canal, escribir, esquivar, parry con práctica real usando las ventanas del bot, rescatar/poderes,
  menú y ajustes). Empieza solo la primera vez y se repite desde el menú. La práctica no envía nada al servidor.

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

## Si la Actividad sale en blanco: el registro de la app
La app escribe en su registro (gris, con 🌐) todo lo que pasa con la Actividad. Léelo mientras abres la Actividad en Discord:
- `GET / → 200 (por el túnel, …)` o `GET /api/config → 200`: Discord **sí** llegó a tu PC. Si luego no hay nada más, el fallo está
  en el navegador de Discord.
- `la página dice: página cargada / SDK de Discord listo / autorizado por Discord / token canjeado / websocket abierto /
  conectado`: hasta dónde llegó la página. La última línea es donde se atascó; `error — …` o `fallo — …` dicen por qué.
- `entrada rechazada: …`: Discord entró pero la app no dejó pasar al jugador (no es miembro, sin acceso al canal, Client Secret).
- **Nada de lo anterior**: Discord no llega a tu PC. Revisa el mapping del Portal (la raíz `/`), que el túnel esté «listo» y que
  la dirección abra `/healthz` desde fuera. Tras cambiar el mapping, cierra la Actividad y vuelve a lanzarla.

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

## Fases
0. Prototipo y puerta de decisión (0.5.0): servidor, túnel, autenticación, reloj, espejo de solo lectura.
1. **Escribir + QTE básico** (0.6.0), **estado, personajes, imágenes y enlace fijo** (0.7.0), **varios QTE, todos los modos y
   cooldowns** (0.8.x).
2. **Interfaz nueva, QTE flotante, menú, ajustes, latencia y tutorial** (0.9.0).
3. Paneles del jugador (perfil, logros, habilidades, inventario, ranking, jefe) y panel del GM: ver `CHANGELOG`/notas de versión.

## Desarrollo del cliente
El cliente web está en `discord-bot/activity_client` (Preact + esbuild; `npm ci && npm run build` lo genera en
`eventos_app/activity/web`). `npm test` ejecuta sus pruebas de lógica (ventanas de QTE, colocación de botones, latencia,
ajustes) y `python activity_client/preview.py <carpeta> [escenario…]` lo abre con datos inventados y guarda capturas
(`desktop`, `phone`, `pages`, `modes`, `crowd`, `tutorial`) para revisar el aspecto sin Discord.

## Qué falta comprobar en esta versión (con Discord real)
- Cómo se ve y se siente el botón flotante en **móviles reales** dentro de Discord (tamaños, posiciones, zona del pulgar) y con
  varios QTE a la vez. Los ajustes de tamaño y posición están para afinarlo.
- La **prueba de latencia** con conexiones y móviles distintos: si el ajuste te parece corto o largo, dime los números de
  *Ayuda → Datos de tu conexión*.
- La mini-ventana de Discord (el comportamiento de la «PiP interactiva» depende de la versión de Discord).
