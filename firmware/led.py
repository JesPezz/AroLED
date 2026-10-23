# led.py - unica instancia de la tira NeoPixel para todo el firmware.
# net.py (arranque de red) y main.py (efectos) comparten este objeto: dos
# instancias sobre el mismo pin dejan el anillo congelado en el ultimo frame,
# porque la segunda "escribe" sin que los LEDs reciban nada.
import machine, neopixel

NUM = 16
PIN = 23

_np = None


def get():
    global _np
    if _np is None:
        _np = neopixel.NeoPixel(machine.Pin(PIN), NUM)
    return _np
