import machine, neopixel, time, math

PIN = 23
NUM = 16
BRIGHT = 140   # 0-255, limita corriente

np = neopixel.NeoPixel(machine.Pin(PIN), NUM)

def breathe():
    while True:
        steps = 90
        for s in range(steps + 1):
            t = s / steps
            b = math.sin(math.pi * t)   # respiracion 0 -> 1 -> 0
            g = t * 220                 # color rojo -> naranja -> amarillo
            rr = int(255 * b * BRIGHT / 255)
            gg = int(g * b * BRIGHT / 255)
            for i in range(NUM):
                np[i] = (rr, gg, 0)
            np.write()
            time.sleep_ms(60)
        time.sleep_ms(150)

breathe()