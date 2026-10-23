# boot.py - se ejecuta en cada arranque.
# - Arranque de red (one-shot): si existe mode.txt ('wifi' o 'ota'), conecta el
#   WiFi y (para 'ota') actualiza; deja el resultado en status.txt y REINICIA.
# - Modo persistente: si netmode.txt == 'wifi', conecta el WiFi y NO reinicia,
#   para que main.py sirva la API HTTP por LAN (BLE apagado).
# - En cualquier otro caso no hace nada (main.py levanta el BLE).
# WiFi y BLE no conviven en la misma sesion en este ESP32 (EIO/crash).
import os, machine


def _flag(name):
    try:
        with open(name) as f:
            return f.read().strip()
    except Exception:
        return ""


mode = _flag("mode.txt")
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
else:
    try:
        import net
        if net.netmode() == "wifi":
            net.run_wifi_mode()
    except Exception:
        pass
    # Suelta net antes de que cargue main.py: con el WiFi ya arriba (~20 KB)
    # el heap no da para importar main.py y el aro se queda mudo (LED verde).
    try:
        import sys, gc
        sys.modules.pop("net", None)
        del net
        gc.collect()
    except Exception:
        pass
