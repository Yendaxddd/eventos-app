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
(La app planea con 5.3 s y 270 ms para dejar margen a la red.)

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
2 bots ~2.6 s. A partir de 5 bots lo que manda es el ritmo de las reacciones (4 por bot, una cada 270 ms).
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
