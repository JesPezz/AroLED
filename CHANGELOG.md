# Changelog

Todas las novedades relevantes del proyecto AroLED.

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
