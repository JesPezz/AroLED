# led.py - unica tira NeoPixel de todo el firmware, escrita por SOFTWARE.
# No se usa neopixel/RMT: en este ESP32 el canal RMT se queda con el pin tras el
# primer envio (las de net.py) y despues ninguna otra escritura llega a los LEDs
# ni con neopixel ni toqueteando el GPIO. machine.bitstream no usa RMT.
import machine

NUM = 16
PIN = 23
_TIMING = (400, 850, 800, 400)   # WS2812: T0H T0L T1H T1L (ns)

_pin = machine.Pin(PIN, machine.Pin.OUT)
_buf = bytearray(NUM * 3)        # orden GRB
writes = 0                       # telemetria: escrituras hechas (ver /api/state)


class _Strip:
    def __setitem__(self, i, rgb):
        j = i * 3
        _buf[j] = rgb[1]
        _buf[j + 1] = rgb[0]
        _buf[j + 2] = rgb[2]

    def __getitem__(self, i):
        j = i * 3
        return (_buf[j + 1], _buf[j], _buf[j + 2])

    def write(self):
        global writes
        machine.bitstream(_pin, 0, _TIMING, _buf)
        writes += 1


_np = None


def get():
    global _np
    if _np is None:
        _np = _Strip()
    return _np
