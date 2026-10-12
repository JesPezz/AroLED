# boot.py - se ejecuta en cada arranque.
# Arranque normal: no hace nada (main.py levanta el BLE).
# Arranque de red: si existe mode.txt ('wifi' o 'ota'), conecta el WiFi y
# (para 'ota') actualiza el firmware; deja el resultado en status.txt y
# reinicia. Se hace en un arranque aparte porque en este ESP32 WiFi y BLE no
# pueden convivir en la misma sesion (EIO/crash).
import os, machine


def _flag():
    try:
        with open("mode.txt") as f:
            return f.read().strip()
    except Exception:
        return ""


mode = _flag()
if mode:
    try:
        os.remove("mode.txt")
    except Exception:
        pass
    try:
        import net
        net.run(mode)
    except Exception as e:
        try:
            with open("status.txt", "w") as f:
                f.write("net:error " + repr(e)[:40])
        except Exception:
            pass
    machine.reset()
