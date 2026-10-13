# Changelog

Todas las novedades relevantes del proyecto AroLED.

## [2.9] - 2026-10-12

### Agregado
- 12 efectos nuevos (modos 9-20), inspirados en WLED/FastLED: Sinelon, Juggle,
  Confeti, Cylon, Meteoro, Centelleo, Pride, Vela, Rayo, Policía, Purpurina y
  Pacifica. *(Solo firmware.)*
- Botones de los 12 modos nuevos en la app.

## [2.8] - 2026-10-12

### Cambiado
- **WiFi y BLE ya no coexisten**: en este ESP32 clásico intentarlo hard-crashea
  el controlador (`Guru Meditation` / `npl_freertos_eventq_init`). El arranque
  es **solo-BLE** y las operaciones de red (conectar WiFi, OTA) se hacen en un
  **arranque aparte**: la app envía el comando por BLE, el aro escribe
  `mode.txt` y **reinicia**; `boot.py` (que corre antes que `main.py`) conecta el
  WiFi, ejecuta la OTA si toca, deja el resultado en `status.txt` y reinicia;
  `main.py` publica ese estado por BLE. *(Solo firmware.)*
- El aro guarda **varias redes WiFi** (`cfg.json` → `nets[]` + `last`) y conecta
  la última que funcionó primero. *(Solo firmware.)*
- La app **reconecta sola** tras un `W`/`U`/`R` (el aro se reinicia), en vez de
  quedarse desconectada.

### Agregado
- `firmware/net.py`: red + OTA movidos a su propio módulo, que `boot.py` carga
  solo en el arranque de red (el firmware completo en un solo módulo agotaba la
  RAM del controlador). La OTA actualiza **los tres** ficheros
  (`main.py`, `net.py`, `boot.py`) si están en el release.

## [2.5] - 2026-10-11

### Corregido
- El ESP32 arranca **solo con BLE** y enciende el WiFi **a demanda** (comandos
  `W`/`C`/`U`): en el ESP32 clásico WiFi + BLE simultáneos agotan la RAM
  (`OSError: WiFi Out of Memory`), lo que dejaba el aro en bucle de reset y la
  app sin poder conectar. Ahora el WiFi se enciende apagando el BLE primero y se
  vuelve a levantar el BLE al terminar. *(Solo firmware.)*

## [2.4] - 2026-10-11

### Cambiado
- La app **reintenta la conexión BLE automáticamente** (hasta 3 intentos, con
  desconexión limpia entre ellos y mayor tiempo de espera); el error solo se
  muestra tras agotar los intentos. Evita el fallo `GATT_CONN_TIMEOUT` tras
  reflashear el ESP32. *(Solo app.)*

## [2.3] - 2026-10-11

### Corregido
- El ESP32 levanta la **BLE antes** de conectar al WiFi, para no parecer bloqueado
  durante el arranque (`net_startup` bloqueaba hasta ~1 min sin BLE ni luz).
- `boot_guard` no entra en bucle infinito si no hay `main.bak`.

## [2.2] - 2026-10-11

### Corregido
- Integridad OTA: el **sha256** pasa a ser la comprobación autoritativa y el
  tamaño solo respaldo (evita falsos `ota:error tamano` al bajar de GitHub); los
  errores incluyen longitudes para diagnóstico. *(Solo firmware.)*

## [2.1] - 2026-10-11

### Agregado
- La app **autocompleta el SSID** de la red a la que está conectado el móvil
  (permiso de ubicación) y **recuerda** la última red y contraseña introducidas.

### Nota
- Android no permite leer la contraseña WiFi guardada del sistema; la app solo
  puede rellenar el nombre de la red y memorizar la clave que escribas una vez.

## [2.0] - 2026-10-11

### Agregado
- Modo **Halloween** (7): naranja/morado girando con pulso lento y destellos.
- Modo **Navidad** (8): segmentos rojo/verde en movimiento con centelleo blanco.
- Característica BLE **Ver** (`...890a8`) que expone la versión del firmware.
- La app muestra la **versión de la app y la del ESP32** al conectar.
- OTA por **GitHub Releases**: el ESP32 y la app descargan la actualización del
  release más reciente del repositorio.

### Cambiado
- El ESP32 ya no depende del servidor local de la Pi para actualizarse.
- Verificación de integridad del firmware por tamaño y `sha256` opcional (antes
  el manifiesto exigía `size`/`sum` y descartaba la descarga si faltaban).

### Corregido
- **Rollback automático**: si un firmware nuevo no arranca 3 veces, el ESP32
  restaura `main.bak` y reinicia (antes había que recuperarlo a mano por REPL).
- Validación de sintaxis del firmware descargado antes de aplicarlo.
- El bucle principal ya no re-ejecuta el último comando BLE recibido.

## [1.3] - (anterior)

- Gestión del WiFi del ESP32 desde la app.
- Actualización OTA del ESP32 por WiFi (vía servidor local).
