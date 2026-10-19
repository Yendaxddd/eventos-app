# La app de escritorio (Windows)

Eventos App es la ventana desde la que llevas el evento: arranca el bot, abre la Actividad de Discord y deja a mano lo que
necesitas durante la partida. Todo está en español. Desde la **1.0.0** tiene una barra lateral con seis páginas y las cosas de
cada día ya no hay que buscarlas.

## Instalar y actualizar
- **Instalador (recomendado):** `EventosApp-Setup-X.Y.Z.exe`, en *Releases* de GitHub. Se instala solo para tu usuario (no pide
  administrador) y crea los accesos directos.
- **Portátil:** `EventosApp-windows.zip`; descomprime en cualquier carpeta y abre `EventosApp.exe`.
- **Actualizar:** ejecuta el instalador nuevo encima. Se conservan `settings.json`, los datos (`data\`), los GIFs (`assets\`) y las
  copias de seguridad (`backups\`).
- **Aviso de versión nueva:** unos segundos después de abrir, la app pregunta a GitHub cuál es la última versión. Si hay una más
  nueva aparece un cuadro en la barra lateral con **Descargar e instalar** (abre el instalador de esa versión en tu navegador) y
  **Ver novedades**. *Ayuda → Buscar actualizaciones* lo hace cuando quieras y te dice si estás al día o por qué no pudo mirar.
  Solo se envía la petición a `api.github.com` (sin tus datos); se apaga en *Configuración → Inicio e IA → «Avisar cuando haya una
  versión nueva»* o con la variable de entorno `EVENTOS_NO_UPDATE_CHECK=1`.
- Windows SmartScreen puede avisar la primera vez: el instalador y el `.exe` no están firmados.

## Las páginas
La barra lateral muestra siempre el **estado del bot** y su botón de iniciar o detener, y las carpetas de datos y de logs. Se
cambia de página con el ratón o con **Ctrl + 1 … 6**.

### 🏠 Inicio
- **Antes de empezar:** una lista corta con lo que falta, en orden: el token del bot, iniciar el bot, elegir el servidor y el
  canal del evento y la Actividad (activa, con su Client Secret, y el túnel abierto). Cada paso pendiente lleva al sitio donde
  se arregla. Cuando todo está listo se reduce a una franja «Todo listo».
- **Evento en vivo:** si el combate está en curso, cuántos QTE hay en marcha, cuántos jugadores están en la Actividad, la sesión
  (los QTE lanzados y los Black Flash de hoy), la **vida del jefe** y la de los jugadores (los más heridos primero, con quién está
  en modo venganza o fuera de los QTE). Se actualiza solo, una vez por segundo.
- **Acciones rápidas:** los QTE individuales y grupales por dificultad, checkpoint, modo lote y sincronizar comandos, con su atajo
  de teclado escrito en el botón. Se activan cuando el bot está conectado.
- **Abrir el panel del GM:** abre el panel del GM de la Actividad en una **ventana propia** (ver más abajo).
- **Registro reciente:** las últimas líneas del registro, con enlace a la página completa.

### 🌐 Actividad
- La **dirección pública** de la Actividad con su estado (*Lista*, *Abriendo*, *Error*…), un botón para **copiarla** y otro para
  pedir **otra nueva**; si el túnel falla, el motivo y qué hacer.
- **Abrir:** *Panel del GM (ventana propia)*, *Ver la Actividad como jugador*, el Developer Portal y *Comprobar la dirección desde
  fuera* (la misma comprobación que hace Discord).
- **Conectados ahora:** quién está dentro de la Actividad, con su ping medido (excelente, buena, regular, mala) y cuánto lleva
  conectado. La ventana del propio GM no cuenta como jugador.
- **Ajustes de la Actividad** (Client Secret y cómo llega Discord: Cloudflare o Tailscale Funnel) y la **puesta en marcha** de una sola
  vez, paso a paso.

### 💾 Datos
- Cuántos archivos y cuánto ocupan los datos del evento y cuándo cambiaron por última vez, con botones para abrir la carpeta de datos,
  la de copias y la de logs.
- **Copias de seguridad.** Una copia es un `.zip` con **los datos del evento** (jugadores, logros, objetos, habilidades, los números
  que fijó el GM…), **sin** el token del bot ni el Client Secret.
  - *Crear copia ahora* (antes guarda en disco lo que el bot tiene en memoria).
  - **Una copia cada vez que se detiene el bot**, solo si hubo cambios desde la anterior. De estas se guardan las últimas 10; las
    manuales y las de «antes de restaurar» se quedan hasta que las borres.
  - *Restaurar* devuelve los datos de esa copia. **Solo con el bot detenido**, y antes se hace otra copia de lo que había, así que
    se puede deshacer. Un `.zip` dañado o manipulado no puede escribir fuera de la carpeta de datos.
  - Las copias viven en `backups\` dentro de la carpeta de la app. Si desinstalas y eliges borrar los datos, se van con ellos:
    copia el `.zip` que quieras conservar a otro sitio.

### 📜 Registro
Todo lo que dice el bot, en vivo y con colores. **Buscar** una palabra, ver **solo avisos y errores**, copiar o limpiar. La página
guarda las últimas 4000 líneas; los archivos completos están en la carpeta de logs.

### ⚙ Configuración
Con pestañas, para no tener todo en una columna:
- **Bot y evento:** el token y, con el bot conectado, el servidor, el canal de los QTE y los roles de jugadores y de administrador
  (desplegables con búsqueda). *Aplicar al evento* lo aplica al instante, sin reiniciar, y es lo mismo que `/setchannel`. Mientras
  el bot está apagado se ve lo último que elegiste.
- **Envío:** los **bots auxiliares** (repartir mensajes y esquivar el rate limit), los **webhooks** y la **prueba de rendimiento**.
- **Inicio e IA:** iniciar el bot al abrir la app, reiniciar HP y cargas al iniciar, atajos de teclado globales, el aviso de versión
  nueva y la IA (Ollama) opcional.

Los cambios valen al pulsar **Guardar cambios**; los de token, IA y atajos, al reiniciar el bot.

### ❓ Ayuda
Primeros pasos, atajos de teclado, qué hacer en los problemas más habituales y **Copiar información para soporte**: versión,
estado del bot, ajustes **sin secretos** y las últimas líneas del registro (el token, el Client Secret y cualquier cosa que lo
parezca salen tapados como «oculto»), lista para pegar donde pidas ayuda.

## El panel del GM en una ventana propia
*Inicio → Abrir el panel del GM* (o *Actividad → Panel del GM*) abre la Actividad **como GM, sin pasar por Discord**, en una ventana
de Edge o de Chrome sin barras (`--app`), en `http://127.0.0.1:PUERTO/` desde este mismo PC. Así llevas el evento con el panel a un
lado y Discord al otro. Si no hay ni Edge ni Chrome, se abre en tu navegador normal.

- Solo funciona desde el propio PC: por la dirección pública de la Actividad el acceso de prueba sigue cerrado.
- Esa ventana no aparece en *Conectados ahora* ni cuenta como jugador (el servidor la marca como «anfitrión»).
- Tiene los mismos paneles y los mismos límites que el del GM dentro de Discord (ver [ACTIVIDAD.md](ACTIVIDAD.md)).
- No hace falta que haya jugadores conectados ni Discord abierto, pero sí que el bot esté iniciado y la Actividad activada.

## Dónde está todo
La carpeta de la app (con el instalador, `%LOCALAPPDATA%\Programs\EventosApp`; el botón *Carpeta de datos* la abre) contiene
`settings.json` (incluye el token: no lo compartas), `data\`, `assets\`, `backups\` y `logs\`. Para pasar la app a otro PC basta
con copiar esa carpeta.

## Para quien la desarrolla
- `eventos_app/pages/` tiene una página por archivo (`home`, `activity`, `data`, `log`, `help`; la de configuración es
  `config_page.py`). `theme.py` tiene la paleta, que es la misma de la Actividad, y `widgets.py` los componentes (píldoras, tarjetas
  de cifras, barras de vida, avisos).
- La lógica sin ventana está aparte y se prueba sin pantalla: `backups.py`, `readiness.py`, `snapshot.py`, `support.py`,
  `updates.py` y `browser.py` (`tests/test_desktop_tools.py`).
- `tests/test_desktop_ui.py` abre la ventana de verdad (en Linux, con `xvfb-run`; en Windows, con su pantalla) y comprueba las
  páginas con y sin evento, los botones de copias, el panel del GM y el aviso de versión nueva.
- `python packaging/preview_desktop.py <carpeta> [fresh|event|stopped]` guarda capturas de todas las páginas (necesita Xvfb e
  ImageMagick), para revisar el aspecto sin Windows.
