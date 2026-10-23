# Changelog

Todas las novedades relevantes del proyecto AroLED.

## [4.1] - 2026-10-23
### Agregado
- `/api/state` publica `ssid`: la red WiFi a la que está conectado el aro (antes solo la IP).
- La app muestra ese SSID junto al estado del aro, así se sabe a qué red se conectó.

## [4.0] - 2026-10-19
### Corregido
- Si el aro estaba en modo WiFi y la red no está disponible, ahora cambia a modo Bluetooth y se reinicia para levantar el BLE limpio. Antes intentaba iniciar el Bluetooth en el mismo arranque en que ya se había inicializado el WiFi, lo que fallaba: el aro quedaba sin Bluetooth y sin WiFi (solo la secuencia azul y los destellos rojos).

## [3.9] - 2026-10-19

### Agregado
- **Pulsador físico** en GPIO27 (se conecta a GND, usa el pull-up interno): cada
  pulsación pasa al siguiente efecto (0..22). No necesita la app ni el móvil.

## [3.8] - 2026-10-19

### Corregido
- El aro **resincroniza la hora por NTP cada 6 h** mientras está en modo WiFi
  (antes solo al arrancar), así el horario nocturno no se desvía si se cae
  internet y vuelve. *(Solo firmware.)*

## [3.7] - 2026-10-12

### Agregado
- **Modo «Nocturno» (23)**: luz cálida y tenue (ámbar con un latido lento y suave),
  pensada como lámpara de noche.
- **Horario de luz nocturna**: el aro enciende el modo Nocturno a una hora y lo
  apaga a otra (admite horarios que cruzan la medianoche). Se configura desde la
  app (`/api/night?on=&off=&bright=&enabled=`); necesita el aro en modo WiFi para
  sincronizar la hora por NTP.
- Botón «Nocturno» y controles de horario en la app.

### Cambiado
- La app oculta la rueda de color salvo en el modo «Color fijo» (0).

## [3.6] - 2026-10-12

### Agregado
- **Encontrar el aro en la red**: la app escanea la LAN (192.168.1.1-254) y
  reconoce el aro por el campo `dev` de `/api/state`; nuevo botón «Buscar el aro
  en la red». Ya no hace falta saber su IP si cambió por DHCP.
- **IP fija opcional**: campo para fijar una IP al aro (se guarda en `cfg.json`
  y se aplica al conectar); alternativa a reservar la MAC en el router.

## [3.5] - 2026-10-12

### Agregado
- Modo «Espectro» (21): color liso siempre encendido que recorre todo el
  espectro de color.
- Modo «Aleatorio» (22): va saltando de efecto en efecto cada pocos segundos.
- Botones de los modos 21 y 22 en la app.

### Cambiado
- «Latido» (4) ahora recorre todo el espectro de color mientras respira.

## [3.4] - 2026-10-12

### Agregado
- **Botón de encendido/apagado de los LEDs** en la app. Nueva característica BLE
  (`…890a9`) y parámetro `on` en la API HTTP (`/api/set?on=0|1`); apagar deja la
  tira en negro sin perder el modo ni los colores.

## [3.3] - 2026-10-12

### Agregado
- **Modo WiFi (LAN)**: el aro puede funcionar por WiFi sin Bluetooth. Si tiene una red
  guardada y el modo es «wifi», arranca en WiFi + servidor HTTP; si el WiFi falla, vuelve
  solo a Bluetooth. La app se conecta por la red local (`http://<ip>/api/…`), recuerda la
  IP y ofrece un botón para pasar de Bluetooth a WiFi y viceversa.
- Comandos para cambiar de modo: `M\twifi|ble` por BLE y `/api/mode` por HTTP.

### Cambiado
- La app ahora soporta dos transportes: Bluetooth (cerca) y WiFi/LAN (a distancia).

### Corregido
- Eliminado de `main.py` el código OTA/HTTP duplicado (lo hace `net.py`), liberando RAM;
  esto arregla el arranque BLE, que fallaba por presión de memoria.

## [3.2] - 2026-10-12

### Corregido
- **OTA del firmware, arreglada de verdad**: la descarga fallaba por el TLS del
  ESP32 (handshakes no deterministas) y por fragmentación de heap al validar con
  `compile()`. Ahora los ficheros se bajan de `raw.githubusercontent.com` (un solo
  handshake, con `cdn.jsdelivr.net` de respaldo) y se validan por **sha256** contra
  un manifiesto (`firmware/version.txt` = versión + hash de cada fichero), sin
  bufferear el cuerpo en RAM. Se actualizan `main.py`, `net.py` y `boot.py`.

## [3.1] - 2026-10-12

### Cambiado
- La comprobación de actualizaciones deja de consultar la API de GitHub (lenta y a
  veces colgaba) y lee un manifiesto de texto `firmware/version.txt`.

## [3.0] - 2026-10-12

### Agregado
- Secuencia de LEDs al actualizar: punto azul girando durante la descarga y
  destellos verdes (ok) o rojos (error) al terminar.

### Corregido
- La OTA descarga en **streaming a disco** (en vez de bufferear el cuerpo en RAM),
  evitando `MemoryError` al bajar el firmware de ~31 KB.

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
