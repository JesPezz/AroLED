import machine, neopixel, time

PIN = 23    # datos del aro
NUM = 16
BTN = 0     # botón BOOT integrado (activo en bajo)
BRIGHT = 70

np = neopixel.NeoPixel(machine.Pin(PIN), NUM)
btn = machine.Pin(BTN, machine.Pin.IN, machine.Pin.PULL_UP)

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

def press():
    if btn.value() != 0:
        return False
    time.sleep_ms(20)
    if btn.value() != 0:
        return False
    while btn.value() == 0:
        time.sleep_ms(10)
    return True

def run_rainbow():
    s = 0
    while True:
        for i in range(NUM):
            np[i] = scale(wheel((i * 256 // NUM + s) & 255))
        np.write()
        s = (s + 8) % 768
        time.sleep_ms(30)
        if press():
            return

def run_chase():
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255),
              (255, 255, 0), (0, 255, 255), (255, 0, 255), (255, 255, 255)]
    ci = 0
    head = 0
    while True:
        col = scale(colors[ci])
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
        if head == 0:
            ci = (ci + 1) % len(colors)
        time.sleep_ms(70)
        if press():
            return

def run_wipe():
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    for col in colors:
        c = scale(col)
        for i in range(NUM):
            np[i] = c
            np.write()
            time.sleep_ms(60)
            if press():
                return
        time.sleep_ms(300)
        if press():
            return

def run_clock():
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
        time.sleep_ms(80)
        if press():
            return

def main():
    mode = 0
    while True:
        if mode == 0:
            run_rainbow()
        elif mode == 1:
            run_chase()
        elif mode == 2:
            run_wipe()
        else:
            run_clock()
        mode = (mode + 1) % 4
        np.fill((0, 0, 0))
        np.write()

main()