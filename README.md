# AroLED

Aro de **16 LEDs NeoPixel** controlado por **Bluetooth Low Energy (BLE)**, con una
app Android y una página web para manejarlo en vivo. El proyecto lo armó **Chuyito**.

- **Firmware**: MicroPython en un ESP32 (efectos + BLE + WiFi + OTA).
- **App Android**: `AroLED.apk` (hecha con Capacitor + `@capacitor-community/bluetooth-le`).
- **Versión web**: `aro_led_app.html` (Web Bluetooth, sin instalar nada).

## Estructura

```
firmware/            Scripts MicroPython que corren en el aro (ESP32)
  main.py            Firmware principal: BLE + WiFi + OTA + efectos
  ring.py            Demo básico (arcoíris, barrido, llenado)
  button_sequences.py Modos que se cambian con el botón BOOT
  clock.py           Efecto "reloj" (punto girando por el aro)
  pumpkin.py         Efecto fuego de calabaza de Halloween
  pumpkin_breath.py  Efecto respiración naranja
  probe.py           Prueba de coexistencia BLE + WiFi
  micropython.bin    Firmware base de MicroPython para flashear el ESP32
aro-ble-app/         App Android (proyecto Capacitor)
  www/index.html     UI de control (BLE)
AroLED.apk           APK compilado listo para instalar
aro_led_app.html     App web de control (Web Bluetooth)
```

## Hardware

- ESP32 (MicroPython).
- Aro de 16 LEDs WS2812/NeoPixel.
- Datos de los LEDs en **GPIO 23**.
- Botón **BOOT** (GPIO 0) para cambiar de modo con `button_sequences.py`.

## Cargar el firmware

1. Flashear MicroPython en el ESP32 (`firmware/micropython.bin`).
2. Copiar los scripts a la placa (por ejemplo con `mpremote` o Thonny). Para el
   firmware completo, subir `firmware/main.py` **como `main.py`** (es lo que el
   arranque ejecuta y lo que actualiza el OTA).

## La app

- **Android**: instalar `AroLED.apk`, abrir, pulsar *Buscar dispositivos* y
  elegir el dispositivo **AroLED**.
- **Web**: abrir `aro_led_app.html` en un navegador compatible con Web Bluetooth
  (Chrome/Edge en Android o escritorio).

Controles: 9 modos (Color fijo, Arcoíris, Fuego, Cometa, Latido, Destellos,
Rebote, Halloween y Navidad), rueda de color, brillo y velocidad. Además, desde
la app se puede configurar el **WiFi del ESP32** y pedirle que **busque
actualización (OTA)** o **se reinicie**. La app muestra la **versión de la app y
la del ESP32** al conectar.

## Protocolo BLE

Servicio `a0e1e0a0-1b1c-4a2b-8c3d-1234567890ab` con características:

| Característica | UUID (sufijo) | Uso |
|---|---|---|
| Bright | `...890a1` | Brillo (0-100) |
| Speed | `...890a2` | Velocidad (0-100) |
| Hue | `...890a3` | Tono (0-255) |
| Mode | `...890a4` | Modo (0-6) |
| Sat | `...890a5` | Saturación (0-255) |
| Cmd | `...890a6` | Comandos (WiFi/OTA/reinicio) |
| Stat | `...890a7` | Estado de red (lectura) |
| Ver | `...890a8` | Versión del firmware (lectura) |

Modos: `0` Fijo, `1` Arcoíris, `2` Fuego, `3` Cometa, `4` Latido, `5` Destellos,
`6` Rebote, `7` Halloween, `8` Navidad.

## Actualizaciones (OTA por GitHub Releases)

El firmware del ESP32 (`main.py`) y la app (`AroLED.apk`) se publican como
**assets de un release de GitHub** y el dispositivo los descarga del propio
GitHub (HTTPS). El repositorio es la fuente de verdad.

- **ESP32**: consulta `releases/latest` de `JesPezz/AroLED`, compara el `tag`
  con su `FW_VERSION`, y si es mayor descarga el asset `main.py` (verificando
  tamaño y, si existe, `main.py.sha256`), valida la sintaxis y lo aplica. Si el
  nuevo firmware no arranca 3 veces, **revierte solo** a `main.bak`.
- **App**: consulta la misma API y, si el `tag` es mayor que su `versionName`,
  ofrece instalar el asset `AroLED.apk`.

Los releases se crean primero como **prerelease** y se promueven a estable
(`--prerelease=false`) cuando el usuario lo indica; así el canal estable
(`releases/latest`) solo ve versiones aprobadas. Ver `CHANGELOG.md`.

## Compilar la app Android

```bash
cd aro-ble-app
npm install
npx cap sync android
cd android && ./gradlew assembleRelease
```

## Nota

`telegram.json` (que había en la carpeta original) **no** se incluye: contenía el
token del bot de Telegram.
