import machine, neopixel, time

PIN = 23
NUM = 16
BRIGHT = 70

np = neopixel.NeoPixel(machine.Pin(PIN), NUM)

def scale(c):
    return (c[0] * BRIGHT // 255, c[1] * BRIGHT // 255, c[2] * BRIGHT // 255)

def wheel(pos):
    pos &= 255
    if pos < 85:
        return (255 - pos * 3, pos * 3, 0)
    if pos < 170:
        pos -= 85
        return (0, 255 - pos * 3, pos * 3)
    pos -= 170
    return (pos * 3, 0, 255 - pos * 3)

def main():
    head = 0
    while True:
        col = scale(wheel(head * 255 // NUM))
        for i in range(NUM):
            d = (head - i) % NUM
            if d == 0:
                np[i] = col
            elif d <= 4:
                f = (5 - d) / 5
                np[i] = (int(col[0] * f), int(col[1] * f), int(col[2] * f))
            else:
                np[i] = (0, 0, 0)
        np.write()
        head = (head + 1) % NUM
        time.sleep(0.08)

main()