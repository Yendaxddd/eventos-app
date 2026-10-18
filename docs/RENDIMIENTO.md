# Rendimiento: latencia y límites de Discord

Qué se midió, qué se optimizó y cuántos jugadores aguanta el evento. Los números del modelo salen de
`discord-bot/eventos_app/capacity.py`; la app los recalcula con tu latencia real en *Configuración → Rendimiento*.

## Lo que no se puede evitar

"Latencia cero" no existe: cada mensaje, reacción o edición es una petición a Discord y cuesta un viaje de red
(normalmente 50–150 ms). Lo que sí se puede quitar es **toda la latencia que añadía el bot**: colas, esperas
internas, pausas artificiales y pasos en serie. Eso es lo que se hizo.

## Límites de Discord (por bot y por canal)

| Qué | Límite | Con 1 bot | Con 5 bots |
|---|---|---:|---:|
| Mensajes | 5 cada 5 s | ~57 por minuto | ~283 por minuto |
| Reacciones | 1 cada 250 ms | ~3.7 por segundo | ~18 por segundo |
| Editar mensajes (barras de HP) | 5 cada 5 s, compartido por todos los mensajes del canal | 5 por ventana | 25 por ventana |

Cada bot tiene su propio cupo, así que cada bot auxiliar suma la misma capacidad.
(La app planea con 5.3 s para mensajes. Para reacciones empieza con 350 ms y aprende el espaciado real de cada bot: ver
"Diagnóstico de límites".)

## De dónde venía la latencia y qué se hizo

| Problema | Efecto | Solución |
|---|---|---|
| discord.py hace esperar a `await send()` hasta que se reinicia la ventana cuando hay 3–4 envíos en paralelo en el mismo bot, aunque quede cupo | Los temporizadores del QTE arrancaban hasta ~5 s tarde | El pool paga el cupo él mismo y le entrega a discord.py un "bucket abierto" solo para mensajes, reacciones y pings. Los 429 reales siguen manejándose |
| Las reacciones salían todas por el bot principal (1 cada 250 ms) | 20 jugadores → la última reacción a los ~5 s | Las reacciones se reparten entre todos los bots |
| Reacción a cada respuesta: `sleep(0.15)` + consulta del historial del canal + la reacción | +150 ms y una petición extra por jugador | Sin consulta; con Tupperbox el bot espera por evento el mensaje del webhook |
| El tiempo de reacción del jugador se medía con el reloj del bot, desde *antes* de enviar el QTE | La latencia de envío y las colas se descontaban al jugador | Se mide con las marcas de tiempo de Discord (QTE visible → respuesta visible) en todos los tipos de QTE |
| Intervalo mínimo artificial de 150 ms entre mensajes por canal | Latencia añadida en cada ráfaga | El pool lleva el control; el intervalo es 0 |
| Barras de HP: una petición para leer el mensaje + 300 ms de espera entre ediciones, en serie | Con 20 jugadores, 6 s o más | Edición directa por id, en paralelo, sin esperas; ventana de agrupado de 0.4 s (antes 2 s) |
| Guardado: ~10 archivos JSON escritos de forma síncrona en el bucle de eventos | El bot se congelaba decenas o cientos de ms (antivirus de Windows) | Hilo de escritura aparte, con escritura atómica |
| Conexiones HTTPS cerradas por inactividad | El primer mensaje tras un rato paga TCP+TLS (~100–300 ms) | Conexiones calientes (3 por bot, cada 8 s) |
| Tras reiniciar, el bot no sabía qué bot escribió cada barra de HP | Cada primera edición iba al bot equivocado y daba 403 | Se recuerda quién escribió los mensajes del hilo de HP |

## Medición (Discord simulado)

Servidor simulado con los límites reales (5 mensajes/5 s y 1 reacción/250 ms por bot y canal) y 100 ms de latencia.
Tiempo hasta que sale el último:

| | discord.py solo | 2 bots | 3 bots | 5 bots |
|---|---:|---:|---:|---:|
| 12 mensajes a la vez | 10.2 s | 5.4 s | 0.11 s | 0.11 s |
| 20 mensajes a la vez | 20.4 s | 10.6 s | 5.4 s | 0.11 s |
| 12 reacciones a la vez | 4.2 s | 1.4 s | 0.9 s | 0.6 s |

Con el código real del bot (`webhook_send` + `safe_add_reaction`), 20 jugadores respondiendo a la vez (1 mensaje y 1 reacción
cada uno) quedan atendidos en **~1 s con 5 bots**, sin ningún 429 (100 ms de latencia simulada). Con 3 bots son ~1.8 s y con
2 bots ~2.6 s. A partir de 5 bots lo que manda es el ritmo de las reacciones (4 por bot, una cada 270 ms en esa simulación).
(Esa prueba usa una ventana de 1 s en vez de 5 s para no tardar; el caso de 5 bots cabe en la primera ventana, así que no cambia.)

> Esto es contra un Discord **simulado**. Los números reales dependen de tu conexión: por eso la app trae la prueba
> de abajo.

## Cuántos jugadores aguanta

Es lo que cabe en el tiempo máximo que aceptas esperar por el resultado del último jugador ("plazo"). Lo que sobra
no se pierde: se encola y sale tarde. Supuestos del modelo:

* **Pesimista:** cada jugador necesita 1 mensaje + 1 reacción + 1 edición de su barra de HP.
* **Realista:** la mayoría de las respuestas solo necesitan reacción (✅); solo fallos y contraataques mandan mensaje
  → 0.5 mensajes y 0.5 ediciones por jugador.

Pesimista:

| Bots | Mensajes/min | Jugadores en 3 s | en 6 s | en 12 s |
|---:|---:|---:|---:|---:|
| 1 | 57 | 5 | 10 | 15 |
| 2 | 113 | 10 | 20 | 30 |
| 3 | 170 | 15 | 30 | 45 |
| 4 | 226 | 20 | 40 | 60 |
| 5 | 283 | 25 | 50 | 75 |
| 8 | 453 | 40 | 80 | 120 |

Realista:

| Bots | Jugadores en 3 s | en 6 s | en 12 s |
|---:|---:|---:|---:|
| 1 | 10 | 20 | 30 |
| 3 | 30 | 60 | 90 |
| 5 | 50 | 100 | 150 |
| 8 | 80 | 160 | 240 |

Si el límite fueran solo las reacciones (respuestas sin mensaje ni edición): ~11 jugadores por bot en 3 s.

## La prueba de rendimiento (con tus bots reales)

*Configuración → Rendimiento → Prueba rápida (~30 s) o completa (~1 min)*. Hazla con el evento parado: manda decenas de
mensajes y reacciones de prueba al canal del evento y los borra al terminar.

1. **Latencia de cada bot** (mensaje y reacción por separado). Si uno destaca, ese bot tiene mala conexión o está lejos.
2. **Ráfagas** del tamaño de lo que aguantan tus bots (y un poco más): primero / mediana / último. Con los bots
   suficientes el "último" debería ser ≈ un viaje de red.
3. **Reacciones** a la vez.
4. **Ritmo sostenido** (solo la completa): mensajes por minuto que el canal admite de forma estable.
5. **Capacidad estimada** con tu latencia medida, y cuántos jugadores suma cada bot.

Se detiene sola si Discord responde con demasiados límites (429). El informe queda en el registro y en
`logs/rendimiento_<fecha>.txt` (con el detalle en JSON al final).

Antes de cada fase la prueba espera a que todos los bots recuperen su cupo (si no, la fase anterior le quitaría turnos
a la siguiente y el "último" de la ráfaga saldría ≈ 5 s peor de lo real). La ráfaga 2 supera el cupo a propósito: junto
a cada ráfaga se indica cuánto de su "último" fue esperar turno para no pasar el límite.

**El informe sale antes de borrar.** Después se borran los mensajes de prueba: en bloque (una sola petición, hasta 100
mensajes) si el bot principal tiene *Gestionar mensajes*; si no, cada bot borra los suyos a la vez. Si algo falla en una
fase, el informe sale igual con lo medido y los errores marcados con ✗.

Cómo leerla: si el "último" de una ráfaga es mucho mayor que la latencia de un bot, es que esa ráfaga superó el cupo y
una parte esperó su turno → agrega bots auxiliares o reduce lo que el bot manda por respuesta.

## Lo que midió una prueba real (0.3.1, 5 bots)

- Ráfaga de 25 mensajes (5 por bot): primero 240 ms, mediana 456 ms, último 1252 ms, sin esperar turno.
- Ritmo sostenido: 274 mensajes por minuto frente a 283 teóricos, así que el modelo de mensajes coincide con Discord real.
- Ráfaga de 40 mensajes: 15 no caben en la primera ventana y esperan 5.3 s (último a 6.1 s). Es el coste de pasar el cupo.
- **Reacciones: 59 de 60 recibieron un 429 y 4 se perdieron** (discord.py abandona tras 5 intentos). Discord limita las
  reacciones más de lo que dice su documentación (mediana 2.2 s, última 5 s con 12 reacciones por bot, ≈ 0.4 s por
  reacción y bot). Desde la 0.3.2 se espacian a 350 ms por defecto, cada bot aprende su espaciado de los 429 y de las
  cabeceras de Discord, y una reacción rendida por discord.py se reintenta en vez de perderse.

### Segunda prueba real (0.3.2): qué reveló el diagnóstico

- Reacciones: 0 perdidas (antes 4). Discord confirma por sus cabeceras el límite documentado (1 cada 250 ms), así que los 11
  429 no eran un límite oculto: eran una **cascada**. Tras un 429, discord.py reenvía esa reacción por su cuenta y el
  reintento ocupa el cupo de 250 ms; la siguiente reacción ya estaba planificada con un hueco fijo y chocaba con él, y la
  siguiente con la anterior... (los bots B y D recibieron 5–6 seguidos, cada ~0.45 s). Además el espaciado aprendido se
  inflaba a 691 ms y la capacidad de reacciones salía pesimista.
- Desde la 0.3.3, al llegar un 429 se **retrasan las reservas pendientes de ese bot** (`Sender.push_back`) para dejar pasar
  el reintento, y el espaciado solo sube un paso por episodio de 429 (+50 ms, máx. 800 ms). Con un Discord simulado con
  jitter de red: 23 → 8 respuestas 429 para 24 reacciones, todas entregadas, misma duración.
- Carga del bot: 13 ms en el peor caso, así que el bot no va justo. Mensajes: 295 por minuto sostenidos. Discord dice que la
  ventana es de 5.0 s (la app usa 5.3 s de margen: ≈ 6 % de capacidad que se podría ganar si hiciera falta).

### Prueba con webhooks (0.4.0): lo que falló

La ráfaga de 50 mensajes (5 bots + 5 webhooks) dio 70 respuestas 429 de webhooks y **12 mensajes perdidos**, y la prueba se
detuvo. Dos fallos míos: (1) supuse un límite independiente por webhook cuando es compartido por canal (arriba); (2) cuando
discord.py se rendía tras 5 intentos con un 429, el envío fallaba en vez de planificarse otra vez. Desde la 0.4.1 un mensaje
que discord.py abandona se vuelve a enviar (por un bot, si el límite de webhooks está lleno) y los 429 de webhooks ya no
cuentan para detener la prueba (como los de reacciones: se reintentan).

### Tercera prueba real (0.3.3)

- Ráfaga de 25: último a 624 ms (antes 1139 ms). Sostenido: 301 mensajes por minuto. Carga del bot: 13 ms.
- Reacciones: 0 perdidas y 11 con un 429. **Son jitter de red, no un límite oculto**: Discord confirma 1 cada 250 ms y
  las reacciones planificadas con 330 ms de hueco llegaron a veces con 39–249 ms porque la latencia de una reacción varía
  entre 160 y 580 ms. Un 429 solo cuesta un reintento (≈ 300 ms) y es más rápido que espaciar a 500 ms para evitarlos:
  60 reacciones en 5 s con 5 bots.
- Ráfaga de 40: último a 8.9 s = 5.3 s de espera (esperado) + **una sola petición de 3.6 s**. En las tres pruebas hay una o
  dos peticiones de ≈ 3 s entre 225 (3083 ms, 3647 ms): es el tiempo de retransmisión de un paquete SYN perdido al abrir una
  conexión nueva en Windows. Desde la 0.3.4 el informe dice si cada petición lenta abrió una conexión nueva y cuánto tardó
  en conectar, para confirmarlo.

## Webhooks como carriles de envío (0.4.0)

Registrar más bots es engorroso, así que **cada bot registra un webhook** en el canal del evento y el reparto los usa como
emisores extra de mensajes:

- **Automático y uno por bot.** Al arrancar y cada vez que cambias el canal del evento, cada bot (el principal y los
  auxiliares) busca su webhook en ese canal y solo crea uno si no tiene (`data\webhook_lanes.json` recuerda cuál; si se
  pierde, lo reconoce por nombre). Un canal admite 15 webhooks en total, así que nunca se crean dos por bot. Los webhooks
  del canal anterior no se borran: si vuelves, se reutilizan.
- **Permiso.** El bot necesita «Gestionar webhooks» en el canal (la invitación nueva ya lo incluye; a los ya invitados hay que
  dárselo). Si falta, o el canal ya tiene 15, ese bot sigue enviando como siempre y la pestaña Configuración dice por qué.
- **Los bots van primero.** Un mensaje va al bot con hueco; los webhooks reciben lo que los bots ya no pueden mandar sin esperar
  turno. El webhook muestra el nombre y la imagen del bot que lo registró.
- **Solo mensajes.** Los webhooks no pueden reaccionar, responder (reply), usar stickers ni botones: eso sigue en los bots.
  Con muchos webhooks las reacciones pasan a ser el límite (la prueba de rendimiento lo dice).
- **Un solo límite para todos los webhooks del canal.** Lo mostró la primera prueba real (0.4.0): los 429 de los webhooks
  llegaron con `ámbito: shared` y las cabeceras dan 5 mensajes cada ~2 s **en total**, no por webhook. Cinco webhooks no
  dan cinco veces más: dan lo mismo que uno (≈ 2.5 mensajes por segundo, el equivalente a unos 2–3 bots). Desde la 0.4.1 se
  reparten como un único cupo y la app aprende ese límite de las cabeceras. Que cada bot registre el suyo no estorba, pero
  tampoco suma.
- **Edición y borrado** van al webhook que escribió el mensaje. El token del webhook nunca se escribe en los registros.
- El bot ignora los mensajes de sus propios webhooks (no los confunde con jugadores ni con Tupperbox).
- Se puede desactivar en *Configuración → Webhooks de envío*.

No se pudo comprobar contra el Discord real (solo contra el simulado): los números de arriba se confirman con la prueba de
rendimiento, que ahora cuenta los webhooks (burst, ritmo y capacidad).

## Diagnóstico de límites

Para saber cuándo y por qué Discord limita (0.3.2):

- **`logs\requests.jsonl`**: una línea por petición (mensaje, reacción, edición, borrado) con el bot, la fase, lo que
  tardó y las cabeceras reales de Discord (límite, restantes, reinicio, a cuánto esperar, ámbito). Rota sola a 3 MB × 3.
- **Cada 429 se explica en el panel** (máximo una línea por bot y tipo cada 3 s): qué bot, cuánto pidió esperar Discord y
  cuántas reservas llevaba ese bot en la ventana, para distinguir "nos pasamos" de "no fue por nosotros" (otro programa
  usando el mismo bot, o desfase de reloj).
- **La prueba de rendimiento incluye un DIAGNÓSTICO**: peticiones por tipo con su tiempo de respuesta, el límite que
  Discord dice de verdad frente al que la app asume, los primeros 429 con su fase, y la **carga del bot**.
- **Carga del bot**: mide cuánto tarda en despertar el bucle del bot. Si es alto (> 250 ms) el cuello de botella es el
  propio bot (demasiado trabajo a la vez), no Discord. Con eso el panel avisa por sí solo.

## Cómo conseguir más capacidad

1. **Más bots auxiliares.** Cada uno suma ~5 jugadores en el peor caso (~10 en el realista) por cada 3 s.
2. **Menos mensajes por respuesta.** Las reacciones tienen unas 4 veces más capacidad que los mensajes; si el resultado
   de un acierto/fallo se comunica solo con ✅/❌, el límite deja de ser el mensaje.
3. **Menos ediciones de HP.** Una barra por jugador cuesta una edición por golpe; un solo mensaje resumen para todos los
   jugadores usaría una edición por ronda en lugar de una por jugador (es un cambio de diseño, candidato a refactor).
4. **Webhooks como carriles extra** (no implementado): cada webhook del canal tiene su propio cupo (~5 cada 2 s),
   independiente de los bots. Es la siguiente palanca grande si 8–10 bots no bastan.

## Lo que no se pudo comprobar

* El comportamiento exacto con los servidores de Discord reales (solo se probó contra un simulado con sus mismos límites).
* Cuántos mensajes y reacciones manda *realmente* cada tipo de QTE en tus eventos: los supuestos "pesimista/realista" son
  estimaciones leyendo el código. La prueba de la app y tus eventos reales los afinan.
