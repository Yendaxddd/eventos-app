# Actividad de Discord (beta)

Una **Actividad** es una pantalla web que Discord abre dentro de la app (PC y móvil). Es el tablero de los QTE: botones grandes
con el tiempo medido **en tu pantalla** (sin depender de mensajes ni reacciones), el canal del evento a la vista y una caja
para escribir, para no cambiar de canal en pleno timing.

**Versión 0.11.0:** además de lo anterior, el **panel del GM** (para quien tiene el rol de administrador): lanzar QTE, controlar al
jefe, a los jugadores, los valores del juego y el contenido (logros, árboles, objetos, traducciones) sin tocar archivos ni comandos.
En la 0.10.0 llegaron **tus paneles** (perfil, logros, personajes y poderes, habilidades, inventario, imágenes y ranking) y en la
0.9.0 la interfaz nueva (todo en español), el **botón flotante Esquivar → Parry con el temporizador encima**, varios QTE a la vez
**por prioridad y sin solaparse**, **ajustes por jugador**, la **prueba de latencia** que ajusta tus tiempos y el **tutorial**.
Los QTE siguen funcionando también por el chat de siempre.

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

## Mi panel (lo que antes era `/dashboard`)
Menú (☰) → «Mi personaje», o la pestaña que quieras. Todo lo hace el servidor con **las mismas reglas que los comandos** (y siempre
para ti: la página no puede pedir los datos de otra persona).
- **Resumen:** tus números (aciertos, Black Flash, rachas, mejor tiempo y la gráfica de tus últimos tiempos), las cargas de tus
  poderes, tus puntos de habilidad, título y dominio, tus puestos en el ranking y el interruptor de **participar en los QTE**
  (el `/qte`).
- **Logros:** por categorías, con lo que da cada uno (puntos, título, dominio), el avance de los que se pueden medir (p. ej. 12 / 100
  esquives) y la fecha. Los **secretos** no cuentan nada hasta conseguirlos (el servidor ni siquiera los envía). Aquí eliges tu
  **título** y tu **expansión de dominio** (con su recarga).
- **Personajes:** registra (como `/register`, con sugerencias de los nombres que han hablado en el canal y nadie tiene), quita,
  y crea o edita los **dos poderes** de cada uno (como `/registerpower`): nombre, qué hace, tipo, efecto (daño, curación,
  aturdir), recarga, frase que lo activa e imagen. Al cambiar tus personajes, la lista «escribir como» se actualiza en todas tus
  pantallas.
- **Habilidades:** el árbol de cada rama con líneas entre cada habilidad y lo que necesita; toca una para ver qué hace por rango,
  su coste y qué te falta, y **aprende** o mejora (como `/learnsk`).
- **Inventario:** tus objetos especiales con rareza, lore y el **progreso de adaptación** (por dificultad o total) con cada
  recompensa escrita en español.
- **Imágenes:** las de tu contraataque (como `/setcountergif`): **sube una desde tu dispositivo** (PNG, JPG, GIF o WebP, hasta
  8 MB; el servidor mira que de verdad sea una imagen y la guarda en Discord, en el canal del evento como un mensaje de
  almacén que la Actividad oculta) o pega un enlace https.
- **Ranking:** las seis clasificaciones del `/leaderboard`, con podio y tu puesto.

Los textos de los datos (logros, habilidades, objetos) están en inglés en los archivos del bot; la Actividad los muestra en español
con una tabla incorporada. Para traducir los tuyos, crea `data/i18n_es.json` (se recarga sola al guardarlo):
`{"exact": {"Boss Slayer": "Cazajefes"}, "patterns": [["^Kill (\\d+) bosses$", "Derrota a \\1 jefes"]]}`.

## Panel del GM (para quien tiene el rol de administrador)
Menú (☰) → «Equipo de GM» → **Panel del GM**. Solo aparece si el bot te considera administrador (el mismo rol que usa para
`/registerboss`, `/giveobject`…), y aunque alguien abriera esa página por otro camino, **el servidor vuelve a comprobar el rol en
cada acción**: si te lo quitan, el panel deja de funcionar al instante (lo comprueba una prueba que llama a todas las acciones sin
el rol). Cada acción hace lo mismo que su comando o su tecla del bot y respeta **los mismos límites**; si algo no es válido te lo
explica en español y **no cambia nada**. Todo lo que se cambia queda firmado en el **Historial** (`data/gm_log.jsonl`).
- **Evento:** el estado (combate, QTE en curso, jugadores, sesión, jefe, aturdimiento), **lanzar un QTE** (individual, grupal, combo,
  dirección o falso; dificultad; a quién o al azar; lo mismo que F9–F12 y `/targetqte`), la **tanda de QTE**, el **combate**
  (empezar, terminar, checkpoint, sincronizar comandos) y el **modo de los QTE automáticos** con sus probabilidades. Se actualiza
  solo cada pocos segundos.
- **Jefe:** el jefe en combate (hacerle daño, curarlo, fijar su vida, derrotarlo o retirarlo sin victoria), **registrar** uno
  (`/registerboss`) o hacer aparecer al de **Tupperbox**, sus ajustes, sus **habilidades** (con estado alterado; usarlas al momento),
  las **imágenes** de esquive, contraataque y derrota (sube una o pega un enlace https) y su **dominio**.
- **Jugadores:** la lista con búsqueda (vida, cargas, puntos, quién está en la Actividad). Dentro de cada persona: **vida** (actual y
  máxima, restaurar), **cargas** de los poderes, reiniciar **recargas**, dejarla fuera o dentro de los QTE, **puntos de habilidad**
  (dar, quitar, o reiniciar sus habilidades devolviéndole lo gastado), **logros** (dar y quitar, con su título y dominio) y
  **objetos** (dar, quitar, vueltas de adaptación y espacios del inventario). «Restaurar la vida de todos» pide confirmación.
- **Valores:** los números del juego agrupados (vida máxima, curación de checkpoint, rescates, Black Flash, cargas y recargas, modo
  venganza, tolerancia de latencia…) y los **tiempos y el daño de cada dificultad**. Valen desde ya y **se conservan al reiniciar el
  bot** (lo que ya guardaba `/config save` va a `live_config.json`; el resto, a `data/gm_values.json`, que se vuelve a comprobar al
  cargarlo).
- **Contenido:** **logros** con formulario (crear, cambiar, borrar), **objetos** (aprobar o rechazar los pendientes, con sus errores a
  la vista) y **archivos** (logros, árboles de habilidades, objetos y traducciones en JSON). El editor comprueba el archivo mientras
  escribes y el servidor lo vuelve a comprobar antes de guardarlo: si hay un error, **no se toca nada**. Antes de cada cambio queda una
  **copia del archivo anterior** en `data/backups` (las últimas 20 de cada uno, con botón para recuperarlas) y el cambio se carga en el
  bot sin reiniciarlo. Se pueden crear árboles y objetos nuevos desde las plantillas.
- **Historial:** quién hizo qué y cuándo (también tras reiniciar).

**Probarlo en este PC sin Discord:** `http://127.0.0.1:8765/?dev=Ana&gm=1` (solo funciona abriéndolo desde el propio PC; por el
túnel público el modo de prueba está cerrado, y quien entra con Discord no puede pedir el panel diciéndolo en su saludo).

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
3. **Paneles del jugador** (perfil, logros, personajes y poderes, habilidades, inventario, imágenes, ranking) (0.10.0).
4. **Panel del GM** (evento, jefe, jugadores, valores, contenido, historial) (0.11.0). Siguen: app de escritorio renovada (1.0.0) y
   mensajes del bot en español.

## Desarrollo del cliente
El cliente web está en `discord-bot/activity_client` (Preact + esbuild; `npm ci && npm run build` lo genera en
`eventos_app/activity/web`). `npm test` ejecuta sus pruebas de lógica (ventanas de QTE, colocación de botones, latencia,
ajustes) y `python activity_client/preview.py <carpeta> [escenario…]` lo abre con datos inventados y guarda capturas
(`desktop`, `phone`, `pages`, `modes`, `crowd`, `tutorial`) para revisar el aspecto sin Discord; `preview_panel.py <carpeta>` y
`preview_gm.py <carpeta>` hacen lo mismo con los paneles del jugador y con el del GM, usando el puente real y un bot inventado.
Las pruebas del panel del GM comprueban las operaciones (`test_activity_gm.py`), el acceso por rol de cada acción
(`test_activity_gm_socket.py`), el navegador (`test_activity_gm_browser.py`) y que cada atributo y método del bot que usa el panel
exista y se llame como el bot lo declara (`test_activity_gm_contract.py`).

## Qué falta comprobar en esta versión (con Discord real)
- Cómo se ve y se siente el botón flotante en **móviles reales** dentro de Discord (tamaños, posiciones, zona del pulgar) y con
  varios QTE a la vez. Los ajustes de tamaño y posición están para afinarlo.
- La **prueba de latencia** con conexiones y móviles distintos: si el ajuste te parece corto o largo, dime los números de
  *Ayuda → Datos de tu conexión*.
- La mini-ventana de Discord (el comportamiento de la «PiP interactiva» depende de la versión de Discord).
- El **panel del GM con el rol real** del servidor (las pruebas usan un bot inventado con el mismo contrato que el real, y la
  prueba de contrato lo vigila, pero no hay un Discord de verdad detrás) y el uso de los formularios largos en el móvil.
- **Subir una imagen desde el móvil** dentro de Discord: el selector de archivos de la Actividad puede comportarse distinto según
  el sistema; el enlace https sirve siempre. Y que el canal del evento deje al bot publicar archivos (la imagen se guarda ahí).
