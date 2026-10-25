# Actividad de Discord (beta)

Una **Actividad** es una pantalla web que Discord abre dentro de la app (PC y móvil). Es el tablero de los QTE: botones grandes
con el tiempo medido **en tu pantalla** (sin depender de mensajes ni reacciones), el canal del evento a la vista y una caja
para escribir, para no cambiar de canal en pleno timing.

**Versión 1.0.0:** la **app de escritorio renovada** (ver [APP.md](APP.md)): el panel del GM se abre desde la app en una **ventana
propia** sin pasar por Discord, y la página *Actividad* de la app muestra la dirección, el estado del túnel y quién está conectado.
En la 0.11.0 llegó el **panel del GM** (para quien tiene el rol de administrador): lanzar QTE, controlar al
jefe, a los jugadores, los valores del juego y el contenido (logros, árboles, objetos, traducciones) sin tocar archivos ni comandos;
en la 0.10.0 llegaron **tus paneles** (perfil, logros, personajes y poderes, habilidades, inventario, imágenes y ranking) y en la
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
- **Menú** (☰ arriba a la izquierda): Ajustes, Prueba de latencia, Entrenamiento, Tutorial y Ayuda. `Esc` o la flecha vuelven a donde estabas.
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
  Desde la 1.2.0: el círculo **se enciende solo un instante** en cada ritmo (antes se quedaba encendido y un toque justo antes
  del destello lo apagaba), los toques se miden con la hora real del evento y también vale la **barra espaciadora**; cada toque
  responde a un solo destello; un pong que tarda más de lo que dice la pantalla cuenta como perdido; si la pantalla se oculta o los
  toques son muy irregulares la prueba pide repetirse en vez de guardar un número malo; **«Saltar» ya no borra** la medición
  anterior del dispositivo; y el ajuste solo se da por guardado cuando el servidor lo confirma (si no, ofrece reintentar).
- **Entrenamiento** (menú → Entrenamiento, 1.2.0): QTE de práctica al azar con los tiempos reales del bot, sin daño, sin puntos y
  sin enviar nada al servidor. Eliges los **tipos** (individual, grupal, dirección, combo y cadena de Black Flash), las
  **dificultades** (se elige una al azar de las marcadas), la **cantidad** (10, 25, 50, 100 o sin fin), la **pausa** entre QTE (mínimo
  y máximo), cuántos pueden estar **a la vez** (1 a 3, para practicar la prioridad), la **velocidad** (50 a 200 %: más de 100 acorta
  todas las ventanas), el largo de los combos y la **muerte súbita** (termina al primer fallo); o un preajuste (Calentamiento, Normal,
  Intenso, Caos). Lo elegido se recuerda en el dispositivo. Durante la tanda ves aciertos, fallos, racha, precisión y tiempo medio,
  y puedes pausar o terminar; si te llega un QTE de verdad, el entrenamiento espera. Al final: resumen con precisión, mejor racha,
  tiempo medio y más rápido, Black Flash, QTE sin pulsar, desglose por tipo y por dificultad, y si batiste tus **marcas** (guardadas
  en el dispositivo; la precisión y la velocidad solo cuentan en tandas de 10 o más).
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

**Desde la app de escritorio:** *Inicio → Abrir el panel del GM* (o *Actividad → Panel del GM*) lo abre **como GM, sin Discord**, en
una ventana de Edge o Chrome sin barras (si no hay, en tu navegador). Usa `http://127.0.0.1:PUERTO/?dev=Anfitrión&gm=1&host=1`: el
servidor marca esa conexión como «anfitrión», así que **no cuenta como jugador** ni sale en la lista de conectados de la app.

**Probarlo en este PC sin Discord:** `http://127.0.0.1:8765/?dev=Ana&gm=1` (solo funciona abriéndolo desde el propio PC; por el
túnel público el modo de prueba está cerrado, y quien entra con Discord no puede pedir el panel diciéndolo en su saludo).

## Canal silencioso (1.1.0)
Con la Actividad abierta, el canal ya no se llena: **sin reacciones** (✅ ❌ ⭐…) y **sin un mensaje por cada esquive o parry**. En el
canal queda el mensaje del QTE; cada resultado le aparece **a quien lo hizo** como un aviso en su Actividad (arriba, junto al
chat). Quien no tiene la Actividad abierta sigue recibiendo el mensaje en el canal, así que nadie se queda sin saber cómo le fue.
Se elige en la app: *Configuración → Mensajes del canal*: **Automático** (lo de arriba), **Silencioso** (nunca en el canal) o
**Todo en el canal** (como antes). El veredicto del juego (puntos, logros) se guarda igual en los tres modos.

## Botones de los QTE (1.1.0)
Una tecla (o un toque) responde **a un solo QTE**: el más urgente que se pueda responder en ese momento, y es el que la pantalla
marca con el aro y la tecla. Al responder, su barra desaparece de inmediato y la tecla pasa al siguiente. Los toques en
pantallas táctiles se registran al soltar el dedo sobre el botón correcto, sin dobles.

## Audio en la Actividad (1.1.0)
Panel del GM → **Audio**. Sube música y sonidos (MP3, OGG, WAV, M4A, WebM, FLAC o AAC; hasta 25 MB cada uno, 1 GB en total) o
**pégalos desde un enlace https** (la app los descarga ella misma y no sigue enlaces a redes privadas). Se guardan en el PC del
anfitrión, en la carpeta `activity_media` de los datos de la app (**no entra en las copias de seguridad de los datos del bot**;
cópiala aparte si cambias de PC).
- **Música:** elige una pista y dale *Reproducir*; suena en la Actividad de todos, con fundido al cambiar y volumen propio. Quien
  entra tarde la oye a partir del segundo en que va.
- **Sonidos ligados a eventos:** QTE (por dificultad o tipo), Black Flash, cadena máxima, combo, expansión, jefe que aparece o cae,
  combate, checkpoint… cada evento tiene su sonido, si quieres, y puede sonar para todos o solo para el objetivo del QTE.
- **Pad de sonidos:** lanza uno en el momento.
- Cada jugador ajusta en *Ajustes* el volumen de música y de efectos o los apaga. Los navegadores y Discord en el móvil no dejan
  sonar nada hasta el primer toque: aparece «Toca para activar el sonido» y, en cuanto se toca, suena lo que estaba esperando.

## Importar personajes de Tupperbox (1.1.0)
Mi panel → Personajes → **Importar de Tupperbox**: sube el archivo `.json` del comando `tul!export` (o pégalo). Se crean los
personajes con sus nombres y **las imágenes se descargan y se guardan en el PC del anfitrión** (así no caducan como los archivos de
Discord y no necesitan URL Mappings). Te dice qué se importó, qué ya existía y qué imagen no se pudo descargar y por qué.

## Cinemáticas (1.1.0)
Panel del GM → **Cinemáticas**. Una cinemática es una lista de pasos con tiempo (en segundos desde el inicio): **texto** (con quién
habla, color y una imagen opcional), **sonido o música** de tu biblioteca, y el final. Se pueden lanzar a mano o **ligar a un
evento** (el jefe cae, empieza el combate, expansión…) para que salten solas. Todos la ven a la vez, sincronizada con el reloj del
servidor; cada jugador puede **saltarla** o apagarlas en *Ajustes → Cinemáticas* (entonces solo oye el sonido). Un QTE nunca queda
tapado: los botones están por encima. Si el canal tiene mensajes activados, el texto también queda escrito en él.

## Estilos de la Actividad (1.1.0)
*Ajustes → Pantalla*: **8 temas** (Oscuro, Muy oscuro, Alto contraste, Medianoche, Brasa, Bosque, Rosa, Sepia), **7 colores de
acento**, **esquinas** rectas, redondas o muy redondas y **fondo** liso, cuadrícula o aurora. Se guardan por persona en el servidor,
así que te siguen del PC al móvil. «Daltonismo» y «Alto contraste» siguen funcionando con cualquier combinación.

## Chat con los personajes (1.3.0)
Los mensajes de un personaje ahora salen **juntos** (una sola cabecera mientras habla la misma persona, aunque el mensaje haya salido
por otro de los webhooks del bot) y **con la imagen del personaje**: si la importaste de Tupperbox, el mensaje sale en el canal con esa
imagen, que Discord descarga de la dirección del túnel de la Actividad. Sin túnel (o sin imagen importada) sale con la última
imagen conocida o con tu foto, como antes.

## Sonidos de combate (1.3.0)
En *Panel del GM → Audio → Avisos automáticos* hay ranuras nuevas: **Tus respuestas** (esquive, parry, contraataque, rescate, paso de
combo, fallo), **Golpes y vida** (un jugador recibe daño, vida baja, curación, el jefe recibe daño) y **Poderes** (cualquier poder, o
el Poder 1 y el Poder 2 por separado). Los de «tus respuestas» y los golpes a jugadores suenan solo para quien los vive (se puede
cambiar a «todos»).
- **Música del combate:** la música también sigue al combate sola: elige una pista (o parar la música) para *empieza el combate*,
  *aparece el jefe*, *el jefe despliega su dominio*, *cae el jefe* y *termina el combate*. Si pones música en dos momentos seguidos
  suena la del último.

## Efectos de los poderes y de lo que pasa (1.3.0)
*Panel del GM → Efectos.* Cuando alguien usa un poder (o pasa algo: Black Flash, un golpe, el jefe que cae…), todas las pantallas
dibujan un efecto: **corte, explosión, rayo, curación, escudo, carga, dominio, impacto o pulso**, con su color, **fuerza**,
**velocidad**, **retraso**, un **rótulo** grande (el nombre del poder o el texto que escribas) y un **sonido**. Todo se guarda solo y
hay un botón *Probar aquí*.
- Un poder sin efecto propio usa el de su ranura («Poder 1» o «Poder 2»), luego el de «Alguien usa un poder» y, si no, un aspecto
  según su tipo (destructivo: explosión, apoyo: curación, defensa: escudo, construcción: carga, control: rayo). Se apaga con *Por
  defecto según su tipo*.
- Cada jugador elige en *Ajustes → Efectos visuales*: **completos**, **suaves** (sin temblores ni destellos fuertes; también se
  aplica con «animaciones reducidas») o **apagados**. Los efectos van por encima de la pantalla y por debajo de los botones de QTE.
- Las **cinemáticas** tienen un paso nuevo, **Efecto visual**, con los mismos efectos. Los datos están en `data/activity_fx.json`.

## Editor de cinemáticas (1.3.0)
Rehecho: una **línea de tiempo con una fila por tipo de paso** (texto, sonido, imagen y escena, efectos, canal), un **bloque por paso**
(clic para editarlo, arrastrar para moverlo; con el teclado, flechas izquierda y derecha), una **lista de pasos** debajo y **el
formulario solo del paso elegido**. Eliges el segundo donde se añade el siguiente paso. **Se guarda sola**: arriba pone «Guardando…»
y «Todo guardado», y si falta algo (el nombre, un texto vacío, un sonido sin elegir) dice cuál es el paso y por qué no se guarda
todavía. *Ver aquí* la prueba solo en tu pantalla y *Poner para todos* la lanza. Una cinemática ligada a «aparece / cae el jefe» o a
su dominio puede ser **solo para un jefe** por su nombre; la hecha para ese jefe gana a la de «cualquier jefe».

## Mando del GM (1.3.0)
Para quien tiene el rol de administrador, el panel de la derecha tiene dos pestañas: **Mi personaje** y **Mando del GM** (en el móvil,
el botón de la corona de la barra de arriba). Todo a mano y sin salir del evento: **hacer aparecer al jefe de Tupperbox** (y el modo
jefe), su vida (−5 %, −10 %, −25 %, +10 %, un daño exacto, derrotar, retirar), sus **habilidades y su dominio**, **iniciar o terminar el
combate**, un **checkpoint**, **lanzar un QTE** al azar (tipo y dificultad), **poner una cinemática** o **música**, y un resumen de lo que
tiene **enlazado cada momento** del combate. Cada botón hace lo mismo que su botón del panel completo y el servidor comprueba el rol
en cada uno.
- *Panel del GM → Jefe → «Qué pasa en cada momento del combate»*: para *empieza el combate*, *aparece el jefe*, *su dominio*, *cae el
  jefe* y *termina el combate* eliges de una vez la **cinemática**, la **música**, el **efecto** y el **sonido**. Se guarda al elegir; los
  detalles se afinan en las pestañas Cinemáticas, Audio y Efectos.

## Novedades de la 2.0
### Moverse por la Actividad
- **Móvil:** barra abajo con *Evento*, *Mi panel*, *Entrenar*, *GM* (si tienes el rol) y *Más*. La lupa de arriba abre «Ir a…».
- **PC:** accesos en la barra de arriba y **«Ir a…»** con `Ctrl+K` o `/`: escribe unas letras («inventario», «enemigos», «latencia»…)
  y Enter. Encuentra cualquier página o pestaña del GM.
- Al cambiar de página el foco va a su título (teclado y lector de pantalla); en pantallas táctiles todo control mide al menos 44 px.

### QTE de la Actividad
**Deslizar** (en la dirección que marca), **arrastrar** (la ficha hasta la diana) y **machacar** (tocar N veces), además del **falso**:
parece real y quien lo responde cae. También desde el teclado (flechas, Espacio). Los lanza el GM o los mini enemigos.

### Mini enemigos
*Panel del GM → Enemigos*: un **bestiario** (nombre, vida, imagen, color, cada cuánto ataca, qué QTE lanza y su dificultad, daño, carga
al derrotarlo) y el **campo** (dañar, curar, derrotar, retirar, pausar). Cada enemigo ataca por su cuenta a alguien que juegue desde la
Actividad; responder bien le devuelve el golpe. Los jugadores lo **golpean tocándolo** (uno cada 2 s, con su arma y sus mejoras) y quien
lo remata se lleva la carga. El mando lateral del GM también los envía. Sus momentos (*aparecen*, *ataca*, *recibe un golpe*, *cae*,
*no queda ninguno*) admiten sonido, efecto y cinemática.

### Cinemáticas para creadores
- **Diálogo:** líneas a la izquierda y a la derecha; los retratos de los dos personajes se quedan en escena, quien habla se ilumina.
  «Personaje» rellena nombre y retrato con los personajes guardados.
- **Efectos de pantalla** que se solapan: pantallazo, temblor, zoom, desenfoque, fundido a negro o a blanco, teñido, latido, viñeta,
  blanco y negro, sepia, negativo, aberración de color y glitch, con fuerza y duración. Los textos nunca se desenfocan.
- **Cámara** (acercarse, alejarse, barridos, flotar) en fondos e imágenes; entradas y tamaños de imagen; transición de escena.
- **Títulos** (cine, capítulo, impacto, lugar, sencillo) y **clima** (lluvia, tormenta, nieve, brasas, chispas, niebla, pétalos,
  estrellas, ceniza).
- **Sobre el juego:** fondo transparente; los efectos se aplican a la pantalla del juego.
- **Plantillas** (diálogo, entrada del jefe, capítulo, recuerdo, victoria, tormenta, lugar), **copiar y pegar pasos** entre
  cinemáticas y **«Desde aquí»** para ver solo una parte.

### Poderes que valen lo que dicen
El efecto de un poder son hasta **4 partes** (el creador en *Personajes* las arma con menús y números y dice qué pasará con tu arma y tus
mejoras actuales). En texto, para quien lo prefiera:

| Parte | Qué hace |
|---|---|
| `damage:N` | N de daño al jefe (× arma, mejora de daño, venganza; con el tope del juego) |
| `damage_all:N` | lo mismo, y N a cada mini enemigo |
| `heal:N` / `heal_team:N` | curarte / curar a todos los que siguen en pie |
| `shield:P:S` / `shield_team:P:S` | P % menos de daño recibido durante S segundos |
| `stun:S` | jefe aturdido S segundos (los mini enemigos también esperan) |
| `buff:damage_boost:P:S`, `buff:bf_boost:P:S` | +P % de daño o de Black Flash (S = 0: solo el próximo) |
| `charge_team:P` | P % de carga para los demás |
| `afflict:burn:S` (también `bleed`, `poison`) | el jefe arde, sangra o se envenena |
| `cleanse` / `cleanse_team` | quita sangrado, quemadura, veneno, debilidad, aturdimiento y maldición |

Las formas antiguas (`damage:50`, `heal:30`, `stun`, `buff:damage_boost:0.2:30`) siguen valiendo. La **imagen o GIF** del poder llena la
pantalla de la Actividad al usarlo: para **todos**, **solo para quien lo usa** o **nadie**. La debilidad ya reduce el daño y la
maldición la carga.

### Daño, efectos e inventario
- Números de **daño y curación** sobre el jefe, cada jugador y tu barra, sea cual sea la causa.
- **Efectos y mejoras** con su cuenta atrás en tu tarjeta (veneno, quemadura, escudo, más daño…) e iconos en la lista y en el jefe.
- *Inventario:* el **Mirror Shard** se invoca desde ahí (60 s de recarga), efectos activos explicados y el **catálogo** de todos los
  objetos del evento.

### Para el GM
- **Objetos por formulario** (*Contenido → Objetos*): crear y editar sin JSON, pasos de adaptación con efectos elegidos de una lista,
  imagen, y dar o quitar a quien lo tiene.
- **Poderes de todos** (*Contenido → Poderes*), editables con el mismo creador.
- **Apoyo** en la ficha de cada jugador (lo que hacía `/support`): curar, escudo, más daño, más Black Flash, carga y reducir recargas.

### Seguridad y fiabilidad
- Una página web abierta en el PC del anfitrión ya no puede entrar como prueba local ni como GM.
- Un cliente no puede elegir su propio tiempo de respuesta; el servidor lo limita por lo que vio.
- Las imágenes descargadas no pueden redirigir a la red de casa; tokens inventados no se llevan a Discord sin límite.
- Una pantalla lenta no frena a las demás; las peticiones largas terminan aunque tarden.

## Puesta en marcha (una sola vez)
En <https://discord.com/developers/applications> → tu aplicación (la del bot principal):
1. **Activities**: actívalas («Enable Activities»). Discord crea el comando de entrada «Launch».
2. **OAuth2 → Redirects**: añade `https://127.0.0.1` (lo pide el flujo de autorización).
3. **Activities → URL Mappings**: en la raíz `/` pon la dirección del túnel **sin** `https://` (la app la muestra y tiene el
   botón «Copiar dirección»). **Ya no hace falta** añadir `/cdn` ni `/media`: las imágenes pasan por la propia app. Solo
   la aplicación del **bot principal** necesita la Actividad; los bots auxiliares no se tocan.
4. **OAuth2 → Client Secret**: «Reset Secret», cópialo y pégalo en *Actividad → Ajustes de la Actividad → Client Secret*.
5. **App Testers**: mientras la app no esté verificada, solo la ven tú, tu equipo y los *testers* (hasta 100), y solo en
   servidores de **menos de 25 miembros**. Añade a cada jugador como tester (debe aceptar la invitación y activar el ajuste de
   pruebas de Actividades en su Discord).
6. **Activities → Settings → Default Orientation Lock State** (opcional): **Portrait**. La Actividad ya se pone sola en vertical
   en el móvil al cargar (2.0.2); con este ajuste también arranca en vertical, sin girar al principio.

## Dirección fija con Tailscale Funnel (opcional, recomendado)
El túnel de Cloudflare cambia de dirección cada vez, y Discord no tiene API para cambiar los URL Mappings, así que habría que
pegarla a mano en cada inicio. **Tailscale Funnel** (gratis para uso personal) da una dirección fija
`equipo.tailXXXX.ts.net` **sin página de aviso** (ngrok gratis sí la pone, y deja la Actividad en blanco dentro de Discord).
1. Instala Tailscale desde <https://tailscale.com/download> e inicia sesión.
2. En <https://login.tailscale.com/admin/dns> activa **MagicDNS** y **HTTPS Certificates**.
3. En la app: *Actividad → Ajustes de la Actividad → Dirección → Tailscale Funnel*, y pulsa **Comprobar Tailscale**: te dice
   si está listo y cuál será tu dirección. Guarda e inicia el bot.
4. La primera vez, Tailscale pide permitir Funnel: la app muestra un enlace (`login.tailscale.com/f/funnel…`); ábrelo, aprueba
   y reinicia la Actividad.
5. Pega la dirección (`equipo.tailXXXX.ts.net`) en URL Mappings `/` **una sola vez**.
Al detener el bot la app apaga el Funnel (nada queda público). Con Funnel, el servidor de la Actividad es accesible desde
internet en esa dirección: entrar exige iniciar sesión con Discord y ser miembro del servidor, el acceso de prueba local
está bloqueado fuera de tu PC y `/media` solo sirve imágenes de Discord. Sin Tailscale, deja «Túnel rápido de Cloudflare».

## «Error 1016» o pantalla en blanco con Tailscale (2.0.1)
Si al abrir la dirección de la Actividad sale *Error 1016 · Origin DNS error*, internet no conoce tu dirección `…ts.net`: Tailscale la
quita del DNS público cuando Funnel se apaga y tarda en volver a publicarla (minutos, a veces horas). Desde la 2.0.1 la app no apaga
Funnel al parar el bot, y la página *Actividad* avisa mientras la dirección no sea pública. Compruébalo con
`nslookup tu-equipo.tu-red.ts.net 1.1.1.1`: cuando devuelva una IP, Discord ya llega.

## En el móvil (2.0.2)
- La Actividad se juega **en vertical**: al cargar le pide a Discord que fije la orientación (también en la ventana flotante).
- Deja libre lo que Discord pone encima de la Actividad (sus botones arriba, la barra del sistema abajo).
- Con el **teclado abierto**, la página mide lo que queda visible: el cuadro de texto queda justo encima del teclado y se
  esconden la barra de abajo y la de acciones (y en pantallas bajas, tu barra de vida y los mini enemigos) hasta que lo cierres.
- Si te llega un QTE mientras escribes, el teclado se cierra solo para dejar sitio al botón; lo que escribiste sigue en el cuadro.

## Mis efectos y ajustes de pantalla (2.0.6)
- **Mi panel → Efectos**: cada jugador elige el efecto visual de lo que le pasa (poderes, esquives, parrys, contraataque, Black Flash,
  golpes, curarse…): el que pongan sustituye al de los GM en su pantalla, o en la de todos si eligen «Todos lo ven». Sin sonido (la
  biblioteca de sonidos es de los GM). Se guarda en el archivo de efectos de la app (`fx.json`, clave `people`).
- **Ajustes → Mi pantalla**: márgenes extra (arriba, abajo, laterales) para una pantalla en la que la interfaz sale recortada.
- **Ajustes → Sonido → Probar**: un pitido por el camino del audio del evento, y si el móvil lo bloquea lo dice.
- En el registro de la app: `la página dice: pantalla — …` (medidas de cada pantalla) y `audio …` (por qué no sonó algo).

## Colocación de los QTE y QTE falsos (2.0.4)
- Los QTE de **gesto** (arrastrar, deslizar, machacar) no se mueven nunca: si la pantalla se llena, los demás se recolocan
  alrededor de ellos.
- El QTE **falso** es un «Esquivar» **rojo** con un «?» en lugar del escudo. Igual en entrenamiento y evento (2.0.5).
- Los QTE que ya están en pantalla no se mueven cuando llega otro (2.0.5); la caja entera de un QTE recibe los toques.
- Machacar pide 4 / 6 / 8 / 10 toques (fácil / medio / difícil / imposible).
- En el entrenamiento hay un tope de esfuerzo: no coinciden QTE imposibles de atender a la vez (p. ej. un arrastre con un combo).

## Tiempos de los QTE (2.0.3)
El tiempo de cada respuesta lo mide la pantalla del jugador: lo que tarde la respuesta en volver al servidor no cuenta. Para que
las pulsaciones en camino lleguen, el bot deja cada QTE abierto un poco más (0,5 s + dos viajes del jugador más lento, como mucho
1,5 s) cuando hay alguien en la Actividad.

## Si alguien no puede entrar (2.0.2)
- La pantalla de entrada dice en qué paso va (servidor, Discord, permiso, sesión). Si Discord no responde, la página se reinicia
  sola una vez; si sigue igual, aparece **Reintentar**.
- Si el jugador pulsa *Cancelar* en la ventana de permiso de Discord, ve «Falta tu permiso» con **Reintentar** (antes tenía que
  cerrar y volver a abrir la Actividad).
- En el registro: `la página dice: Discord no responde` o `permiso de Discord — …` indican cuál de los dos fue.
- Quien **no aparece en el registro** ni siquiera con `GET /`: Discord no le deja abrir la Actividad. Mientras la app no esté
  verificada, cada jugador tiene que ser **App Tester** (invitación aceptada) y el servidor tener menos de 25 miembros.

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
4. *Ver la Actividad como jugador* (página Actividad) la abre en tu navegador (solo desde este PC, no a través del túnel) para ver que carga.

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
4. **Panel del GM** (evento, jefe, jugadores, valores, contenido, historial) (0.11.0).
5. **App de escritorio renovada** (inicio, Actividad, datos con copias, registro, ayuda, panel del GM en ventana propia, aviso de
   versión nueva) (1.0.0). Sigue: los mensajes del bot en español.

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
- La **ventana propia del panel del GM** con Edge o Chrome en tu Windows (la apertura con `--app` se prueba con navegadores falsos;
  si algo falla, se abre en tu navegador) y la app de escritorio en un Windows real más allá de la prueba de arranque del instalador.
- **Subir una imagen desde el móvil** dentro de Discord: el selector de archivos de la Actividad puede comportarse distinto según
  el sistema; el enlace https sirve siempre. Y que el canal del evento deje al bot publicar archivos (la imagen se guarda ahí).
- **Audio dentro de Discord**, sobre todo en el móvil (el permiso de sonido y la reproducción en segundo plano dependen de la
  versión de Discord), y la **temporización de las cinemáticas** con latencias reales.
- **Exportaciones reales de Tupperbox** (las pruebas usan archivos con el mismo formato documentado, no los de tu servidor).
- **Voz:** esta versión no reproduce en un canal de voz; el sonido va por la Actividad de cada persona.
- **Mensajes del canal en español (2.0):** con *Idioma: Español* el bot traduce sus mensajes, comandos y registro; lo que escriben los
  jugadores no se toca. Si ves alguna frase en inglés, dímela: es un texto que el catálogo aún no tiene.
- **Mini enemigos, gestos y cinemáticas nuevas en móviles reales** (sensibilidad al deslizar y arrastrar, rendimiento del clima y los
  efectos). *Ajustes → Efectos visuales → Suaves* y «menos movimiento» los alivian.
- **Imagen del personaje en el canal (1.3.0):** que Discord descargue la imagen importada desde la dirección del túnel (con el túnel
  rápido de Cloudflare la dirección cambia cada vez, pero Discord la pide en cada mensaje, así que no hay problema mientras la
  Actividad esté abierta).
- **Efectos visuales en móviles flojos:** si algún efecto va a tirones, *Ajustes → Efectos visuales → Suaves* los alivia.
