import machine, neopixel, time

PIN = 23          # GPIO de datos del aro
NUM = 16          # cantidad de LEDs
BRIGHT = 60       # 0-255, limita el consumo de corriente (aro a full ~1A)

np = neopixel.NeoPixel(machine.Pin(PIN), NUM)

def scale(c):
    return (int(c[0] * BRIGHT / 255), int(c[1] * BRIGHT / 255), int(c[2] * BRIGHT / 255))

def wheel(pos):
    pos &= 255
    if pos < 85:
        return (255 - pos * 3, pos * 3, 0)
    if pos < 170:
        pos -= 85
        return (0, 255 - pos * 3, pos * 3)
    pos -= 170
    return (pos * 3, 0, 255 - pos * 3)

def off():
    for i in range(NUM):
        np[i] = (0, 0, 0)
    np.write()

def rainbow_rotate(step):
    for i in range(NUM):
        np[i] = scale(wheel((i * 256 // NUM + step) & 255))
    np.write()

def chase(color, wait=0.07, tail=4):
    for head in range(NUM):
        for i in range(NUM):
            d = (head - i) % NUM
            if d < tail:
                f = (tail - d) / tail
                np[i] = scale((color[0] * f, color[1] * f, color[2] * f))
            else:
                np[i] = (0, 0, 0)
        np.write()
        time.sleep(wait)

def wipe(color, wait=0.06):
    for i in range(NUM):
        np[i] = scale(color)
        np.write()
        time.sleep(wait)

def main():
    while True:
        for s in range(0, 768, 8):          # 1) arcoiris girando
            rainbow_rotate(s)
            time.sleep(0.03)
        for col in [(255, 0, 0), (0, 255, 0), (0, 0, 255),   # 2) barrido de colores
                    (255, 255, 0), (0, 255, 255), (255, 0, 255), (255, 255, 255)]:
            chase(col)
        for col in [(255, 0, 0), (0, 255, 0), (0, 0, 255)]:  # 3) llenado por color
            wipe(col)
            time.sleep(0.3)
        off()
        time.sleep(0.3)

main()
