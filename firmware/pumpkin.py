import machine, neopixel, time, random

PIN = 23
NUM = 16
BRIGHT = 130   # 0-255, limita corriente (~1A con LEDs naranjas)

np = neopixel.NeoPixel(machine.Pin(PIN), NUM)

def flame():
    level = 0.85
    while True:
        level += (random.random() - 0.5) * 0.25
        level = min(1.0, max(0.6, level))
        for i in range(NUM):
            f = level * (0.75 + random.random() * 0.25)
            if random.random() < 0.06:
                f *= 0.35
            r = 255 * f                                  # rojo siempre alto
            g = (63 + 63 * f) * f                         # mas amarillo al brillar
            np[i] = (int(r * BRIGHT / 255), int(g * BRIGHT / 255), 0)
        np.write()
        time.sleep_ms(random.randint(20, 60))

flame()