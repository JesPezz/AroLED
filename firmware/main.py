# AroLED - firmware MicroPython (ESP32)
# OTA por GitHub Releases (release ESTABLE = /releases/latest).
# Assets del release: "main.py" (este firmware) y, opcional, "main.py.sha256".
import bluetooth, machine, neopixel, time, struct, math, random
import os, json, network, socket
from micropython import const

_IRQ_DISCONNECT = const(2)
_IRQ_WRITE = const(3)

PIN = 23
NUM = 16

_np = neopixel.NeoPixel(machine.Pin(PIN), NUM)

BTN_PIN = 27   # pulsador fisico a GND (pull-up interno); cambia de efecto
_btn = machine.Pin(BTN_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

FW_VERSION = "4.4"

SERVICE   = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890ab")
CH_BRIGHT = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a1")
CH_SPEED  = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a2")
CH_HUE    = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a3")
CH_MODE   = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a4")
CH_SAT    = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a5")
CH_CMD    = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a6")
CH_STAT   = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a7")
CH_VER    = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a8")
CH_ON     = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a9")

# ---------------- config / OTA ----------------
CFG_PATH     = "cfg.json"
BOOTCNT_PATH = "bootcnt"
NETMODE_PATH = "netmode.txt"   # "ble" (defecto) o "wifi" (API HTTP en LAN, sin BLE)

def netmode():
    try:
        with open(NETMODE_PATH) as f:
            m = f.read().strip()
        if m in ("ble", "wifi"):
            return m
    except Exception:
        pass
    return "ble"

def save_netmode(m):
    try:
        with open(NETMODE_PATH, "w") as f:
            f.write("wifi" if m == "wifi" else "ble")
    except Exception:
        pass

def load_cfg():
    try:
        with open(CFG_PATH) as f:
            c = json.load(f)
    except Exception:
        c = {}
    # Migracion del formato viejo {"ssid","pass"} a lista de redes.
    if "nets" not in c:
        nets = []
        if c.get("ssid"):
            nets.append({"ssid": c["ssid"], "pass": c.get("pass", "")})
        c = {"nets": nets, "last": c.get("ssid", "")}
    return c

def save_cfg(c):
    try:
        with open(CFG_PATH, "w") as f:
            json.dump(c, f)
    except Exception:
        pass

def _read_int(path, d=0):
    try:
        return int(open(path).read().strip())
    except Exception:
        return d

def _write_int(path, v):
    try:
        with open(path, "w") as f:
            f.write(str(v))
    except Exception:
        pass

# ---------------- rollback automatico (boot-loop) ----------------
# Si el firmware nuevo no llega a "confirmar" el arranque (3 reintentos),
# se restaura main.bak y se reinicia. Ojo: una sola main.py (no hay boot.py),
# asi que solo cubre fallos que provocan reset (excepcion -> reset en el
# arranque o un colgado que acaba en WDT). Un cuelgue duro sin reset no se
# recupera solo; para eso habria que anadir machine.WDT.
def _restore_bak():
    try:
        src = open("main.bak", "rb").read()
        with open("main.py", "wb") as f:
            f.write(src)
        os.remove("main.bak")
        _write_int(BOOTCNT_PATH, 0)
        return True
    except Exception:
        return False

def boot_guard():
    cnt = _read_int(BOOTCNT_PATH, 0) + 1
    _write_int(BOOTCNT_PATH, cnt)
    if cnt > 3:
        # Restaurar la version previa y reiniciar; si no hay copia, no quedarse
        # en un bucle de reinicios: limpiar el contador y continuar.
        if _restore_bak():
            machine.reset()
        _write_int(BOOTCNT_PATH, 0)

# ---------------- estado de red publicado por BLE ----------------
netmsg = "wifi:off"
ble = None
h_stat = None

def set_net(m):
    global netmsg
    netmsg = m
    try:
        ble.gatts_write(h_stat, m.encode())
    except Exception:
        pass

# ---------------- wifi ----------------
wlan = None

def _wifi_up():
    # True si el WiFi ya quedo conectado (lo conecta boot.py en modo WiFi).
    global wlan
    try:
        if wlan is None:
            wlan = network.WLAN(network.STA_IF)
        return wlan.isconnected()
    except Exception:
        return False

def nets_list():
    return load_cfg().get("nets", [])

def net_ssids():
    return [n.get("ssid", "") for n in nets_list() if n.get("ssid")]

def add_net(ssid, pw):
    if not ssid:
        return
    c = load_cfg()
    nets = [n for n in c.get("nets", []) if n.get("ssid") != ssid]
    nets.append({"ssid": ssid, "pass": pw or ""})
    c["nets"] = nets
    save_cfg(c)

def del_net(ssid):
    c = load_cfg()
    c["nets"] = [n for n in c.get("nets", []) if n.get("ssid") != ssid]
    save_cfg(c)

# ---------------- BLE ----------------
# modo: 0 Fijo | 1 Arcoiris | 2 Fuego | 3 Cometa | 4 Latido | 5 Destellos |
#       6 Rebote | 7 Halloween | 8 Navidad | 9 Sinelon | 10 Juggle |
#       11 Confeti | 12 Cylon | 13 Meteoro | 14 Centelleo | 15 Pride |
#       16 Vela | 17 Rayo | 18 Policia | 19 Purpurina | 20 Pacifica
state = {"bright": 5, "speed": 50, "hue": 0, "sat": 255, "mode": 1, "on": 1}

h_bright = h_speed = h_hue = h_mode = h_sat = h_cmd = h_ver = None
pending = None
cmd_buf = b""

def advertise():
    nm = b"AroLED"
    payload = struct.pack("BBB", 2, 0x01, 0x06)
    payload += struct.pack("BB", len(nm) + 1, 0x09) + nm
    ble.gap_advertise(100000, adv_data=payload)

def _irq(event, data):
    global cmd_buf, pending
    if event == _IRQ_DISCONNECT:
        advertise()
    elif event == _IRQ_WRITE:
        conn, attr = data
        if attr == h_bright:
            state["bright"] = ble.gatts_read(h_bright)[0]
        elif attr == h_speed:
            state["speed"] = ble.gatts_read(h_speed)[0]
        elif attr == h_hue:
            state["hue"] = ble.gatts_read(h_hue)[0]
        elif attr == h_mode:
            state["mode"] = ble.gatts_read(h_mode)[0]
        elif attr == h_sat:
            state["sat"] = ble.gatts_read(h_sat)[0]
        elif attr == h_on:
            state["on"] = ble.gatts_read(h_on)[0]
        elif attr == h_cmd:
            cmd_buf += ble.gatts_read(h_cmd)
            k = cmd_buf.find(b"\x00")
            if k >= 0:
                pending = cmd_buf[:k].decode("utf-8", "ignore")
                cmd_buf = b""

def start_ble():
    global ble, h_bright, h_speed, h_hue, h_mode, h_sat, h_cmd, h_stat, h_ver, h_on
    ble = bluetooth.BLE()
    ble.active(True)
    ble.config(gap_name="AroLED")
    ((h_bright, h_speed, h_hue, h_mode, h_sat, h_cmd, h_stat, h_ver, h_on),) = ble.gatts_register_services((
        (SERVICE, (
            (CH_BRIGHT, bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
            (CH_SPEED,  bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
            (CH_HUE,    bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
            (CH_MODE,   bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
            (CH_SAT,    bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
            (CH_CMD,    bluetooth.FLAG_WRITE),
            (CH_STAT,   bluetooth.FLAG_READ),
            (CH_VER,    bluetooth.FLAG_READ),
            (CH_ON,     bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
        )),
    ))
    ble.gatts_write(h_bright, bytes([state["bright"]]))
    ble.gatts_write(h_speed,  bytes([state["speed"]]))
    ble.gatts_write(h_hue,    bytes([state["hue"]]))
    ble.gatts_write(h_mode,   bytes([state["mode"]]))
    ble.gatts_write(h_sat,    bytes([state["sat"]]))
    ble.gatts_write(h_cmd,    bytes(20))
    ble.gatts_write(h_stat,   netmsg.encode())
    ble.gatts_write(h_ver,    FW_VERSION.encode())
    ble.gatts_write(h_on,     bytes([state["on"]]))
    ble.irq(_irq)
    advertise()

# ---------------- comandos (fuera del IRQ) ----------------
def _goto_net(mode):
    # Cambia a un arranque de red: deja la bandera y reinicia. boot.py hara el
    # WiFi/OTA (WiFi y BLE no conviven en una misma sesion en este ESP32).
    set_net("reiniciando:" + mode)
    try:
        with open("mode.txt", "w") as f:
            f.write(mode)
    except Exception:
        set_net("cmd:error")
        return
    time.sleep_ms(300)
    machine.reset()

def handle_cmd(c):
    if c.startswith("W"):
        parts = c.split("\t")
        ssid = parts[1] if len(parts) > 1 else ""
        pw = parts[2] if len(parts) > 2 else ""
        add_net(ssid, pw)
        if len(parts) > 3 and parts[3]:
            c2 = load_cfg()
            c2["static"] = parts[3]
            save_cfg(c2)
        _goto_net("wifi")
    elif c == "C":
        _goto_net("wifi")
    elif c == "X":
        set_net("wifi:off")
    elif c == "U":
        _goto_net("ota")
    elif c == "R":
        set_net("reiniciando")
        time.sleep_ms(200)
        machine.reset()
    elif c.startswith("M"):
        # M\twifi | M\tble : cambia el modo persistente y reinicia.
        parts = c.split("\t")
        save_netmode(parts[1] if len(parts) > 1 else "wifi")
        set_net("reiniciando:" + netmode())
        time.sleep_ms(200)
        machine.reset()
    else:
        set_net("cmd:" + c[:12])

# ---------------- color ----------------
def hsv(h, s, v):
    if s == 0:
        return (v, v, v)
    h = (h & 255) * 6
    i = h // 256
    f = h % 256
    p = v * (255 - s) // 255
    q = v * (255 - (s * f // 256)) // 255
    t = v * (255 - (s * (256 - f) // 256)) // 255
    if i == 0: return (v, t, p)
    if i == 1: return (q, v, p)
    if i == 2: return (p, v, t)
    if i == 3: return (p, q, v)
    if i == 4: return (t, p, v)
    return (v, p, q)

def scaled(rgb):
    sc = state["bright"] * 255 // 100
    return (rgb[0] * sc // 255, rgb[1] * sc // 255, rgb[2] * sc // 255)

# ---------------- efectos (1 frame cada uno) ----------------
off = 0
heat = [0] * NUM
pos = 0
breath = 0.0
bpos = 0.0
bdir = 1
hphase = 0.0
nphase = 0.0
specph = 0.0

_HALLOW = ((255, 90, 0), (150, 0, 255))   # naranja / morado
_XMAS   = (200, 0, 0)                     # base rojo; verde y blanco abajo

def fx_fixed():
    px = scaled(hsv(state["hue"], state["sat"], 255))
    for i in range(NUM):
        _np[i] = px

def fx_rainbow():
    global off
    sat = state["sat"]
    for i in range(NUM):
        _np[i] = scaled(hsv(i * 256 // NUM + off, sat, 255))
    off = (off + 4 + state["speed"] // 12) & 255

def fx_fire():
    global heat
    sp = state["speed"]
    cool = 6 + (100 - sp) * 30 // 100
    for i in range(NUM):
        heat[i] = heat[i] - random.randint(0, cool // NUM + 1)
        if heat[i] < 0: heat[i] = 0
    if random.randint(0, max(1, (100 - sp) // 3 + 1)) == 0:
        y = random.randint(0, NUM - 1)
        heat[y] = min(255, heat[y] + random.randint(160, 255))
    for i in range(NUM - 1, 1, -1):
        heat[i] = (heat[i - 1] + heat[i - 2] + heat[i - 2]) // 3
    for i in range(NUM):
        t = heat[i]
        r = min(255, t * 3)
        g = min(255, (t - 85) * 3) if t > 85 else 0
        b = min(40, (t - 170) * 3) if t > 170 else 0
        _np[i] = scaled((r, g, b))

def fx_chase():
    global pos
    base = hsv(state["hue"], state["sat"], 255)
    for i in range(NUM):
        d = (i - pos) % NUM
        if d > NUM // 2: d -= NUM
        d = -d if d < 0 else d
        if d < 5:
            f = 255 - d * 50
            _np[i] = scaled((base[0] * f // 255, base[1] * f // 255, base[2] * f // 255))
        else:
            _np[i] = scaled((18, 9, 0))
    pos = (pos + 1) % NUM

def fx_breath():
    # Respiracion: el brillo sube y baja, y el color recorre todo el espectro.
    global breath
    v = int((math.sin(breath) * 0.5 + 0.5) * 255)
    hue = (state["hue"] + int(breath * 40)) & 255
    px = scaled(hsv(hue, state["sat"], v))
    for i in range(NUM):
        _np[i] = px
    breath += 0.06 + state["speed"] * 0.004

def fx_sparkle():
    base = hsv(state["hue"], state["sat"], 255)
    for i in range(NUM):
        r, g, b = _np[i]
        _np[i] = (r * 180 // 255, g * 180 // 255, b * 180 // 255)
    for _ in range(1 + random.randint(0, 2)):
        i = random.randint(0, NUM - 1)
        _np[i] = scaled((255, 255, 255)) if random.randint(0, 3) == 0 else scaled(base)

def fx_bounce():
    global bpos, bdir
    base = hsv(state["hue"], state["sat"], 255)
    for i in range(NUM):
        d = i - int(bpos)
        if d < 0: d = -d
        f = 255 - d * 60
        if f < 0: f = 0
        _np[i] = scaled((base[0] * f // 255, base[1] * f // 255, base[2] * f // 255))
    bpos += bdir * (1 + state["speed"] // 25)
    if bpos >= NUM - 1:
        bpos = NUM - 1; bdir = -1
    if bpos <= 0:
        bpos = 0; bdir = 1

def fx_halloween():
    # Naranja/morado alternos girando, con pulso lento y destellos blancos.
    global hphase
    v = 0.55 + 0.45 * (math.sin(hphase) * 0.5 + 0.5)
    shift = int(hphase * 3) % 2
    for i in range(NUM):
        c = _HALLOW[(i + shift) % 2]
        _np[i] = scaled((int(c[0] * v), int(c[1] * v), int(c[2] * v)))
    if random.randint(0, 14) == 0:
        _np[random.randint(0, NUM - 1)] = scaled((255, 255, 180))
    hphase += 0.03 + state["speed"] * 0.004

def fx_navidad():
    # Segmentos rojo/verde que se desplazan + centelleo blanco.
    global nphase
    seg = 4
    phase = int(nphase) % (2 * seg)
    for i in range(NUM):
        g = ((i + phase) // seg) % 2
        _np[i] = scaled((200, 0, 0) if g == 0 else (0, 180, 0))
    if random.randint(0, 9) == 0:
        _np[random.randint(0, NUM - 1)] = scaled((255, 255, 255))
    nphase += 0.2 + state["speed"] * 0.02

# --- efectos populares (estilo WLED / FastLED) ---
sinpos = 0.0
jphase = 0.0
cylpos = 0.0
cyldir = 1
mphase = 0.0
twstate = [0] * NUM
ltimer = 0
polphase = 0.0
pacph = 0.0

def _fade(f):
    for i in range(NUM):
        r, g, b = _np[i]
        _np[i] = (r * f // 255, g * f // 255, b * f // 255)

def fx_sinelon():
    # Punto que se mueve con suavidad (seno) dejando estela.
    global sinpos
    _fade(200)
    p = int((math.sin(sinpos) * 0.5 + 0.5) * (NUM - 1))
    _np[p] = scaled(hsv(state["hue"], state["sat"], 255))
    sinpos += 0.10 + state["speed"] * 0.012

def fx_juggle():
    # Varios puntos de colores rebotando con estela.
    global jphase
    _fade(180)
    n = 4
    for k in range(n):
        p = int((math.sin(jphase + k * 1.7) * 0.5 + 0.5) * (NUM - 1))
        _np[p] = scaled(hsv(k * 256 // n, 255, 255))
    jphase += 0.08 + state["speed"] * 0.008

def fx_confetti():
    # Puntos de color aleatorios que se apagan poco a poco.
    _fade(225)
    for _ in range(1 + state["speed"] // 30):
        _np[random.randint(0, NUM - 1)] = scaled(hsv(random.randint(0, 255), 255, 255))

def fx_cylon():
    # Escáner tipo Cylon/Larson (punto rojo que barre con estela).
    global cylpos, cyldir
    _fade(150)
    _np[int(cylpos)] = scaled((255, 0, 0))
    cylpos += cyldir * (0.4 + state["speed"] * 0.03)
    if cylpos >= NUM - 1:
        cylpos = NUM - 1; cyldir = -1
    if cylpos <= 0:
        cylpos = 0; cyldir = 1

def fx_meteor():
    # Meteoro con cola que decae.
    global mphase
    _fade(130)
    _np[int(mphase) % NUM] = scaled(hsv(state["hue"], state["sat"], 255))
    mphase += 0.3 + state["speed"] * 0.05

def fx_twinkle():
    # LEDs que centellean en colores aleatorios.
    for i in range(NUM):
        if twstate[i] > 0:
            twstate[i] -= 1
            r, g, b = _np[i]
            _np[i] = (r * 150 // 255, g * 150 // 255, b * 150 // 255)
        else:
            _np[i] = (0, 0, 0)
    for _ in range(1 + state["speed"] // 25):
        i = random.randint(0, NUM - 1)
        if twstate[i] == 0:
            twstate[i] = random.randint(3, 9)
            _np[i] = scaled(hsv(random.randint(0, 255), 210, 255))

def fx_pride():
    # Arcoíris girando con brillo ondulante (Pride 2015).
    global off
    for i in range(NUM):
        v = 128 + int(127 * math.sin(i * 0.5 + off * 0.1))
        _np[i] = scaled(hsv((i * 256 // NUM + off) & 255, 255, v))
    off = (off + 2 + state["speed"] // 15) & 255

def fx_candle():
    # Parpadeo cálido tipo vela.
    for i in range(NUM):
        r = random.randint(150, 255)
        _np[i] = scaled((r, r * 45 // 100, r // 8))

def fx_lightning():
    # Fondo oscuro con destellos blancos aleatorios (tormenta).
    global ltimer
    _fade(70)
    if ltimer > 0:
        ltimer -= 1
        _np[random.randint(0, NUM - 1)] = scaled((255, 255, 255))
    elif random.randint(0, max(1, 50 - state["speed"] // 2)) == 0:
        ltimer = random.randint(2, 5)

def fx_police():
    # Mitad roja / mitad azul alternando (policía).
    global polphase
    p = int(polphase) % 4
    for i in range(NUM):
        _np[i] = (0, 0, 0)
    if p < 2:
        for i in range(NUM // 2):
            _np[i] = scaled((255, 0, 0))
    else:
        for i in range(NUM // 2, NUM):
            _np[i] = scaled((0, 0, 255))
    polphase += 0.15 + state["speed"] * 0.02

def fx_glitter():
    # Arcoíris de fondo con destellos blancos.
    global off
    for i in range(NUM):
        _np[i] = scaled(hsv((i * 256 // NUM + off) & 255, state["sat"], 120))
    off = (off + 3 + state["speed"] // 15) & 255
    for _ in range(1 + state["speed"] // 30):
        _np[random.randint(0, NUM - 1)] = scaled((255, 255, 255))

def fx_pacifica():
    # Olas azules/cian lentas.
    global pacph
    for i in range(NUM):
        v = (math.sin(i * 0.5 + pacph) + math.sin(i * 0.8 - pacph * 1.3)) * 0.5
        g = int(70 + 60 * v)
        b = int(120 + 100 * v)
        if g < 0: g = 0
        if b < 0: b = 0
        _np[i] = scaled((0, g, b))
    pacph += 0.03 + state["speed"] * 0.004

def fx_spectrum():
    # Color liso que recorre todo el espectro (siempre encendido).
    global specph
    px = scaled(hsv(int(specph) & 255, 255, 255))
    for i in range(NUM):
        _np[i] = px
    specph += 1 + state["speed"] // 8

nightph = 0.0

def fx_night():
    # Lampara de noche: ambar calido y tenue, con un latido lento y suave.
    global nightph
    v = 0.8 + 0.2 * (math.sin(nightph) * 0.5 + 0.5)
    px = scaled((int(255 * v), int(110 * v), int(25 * v)))
    for i in range(NUM):
        _np[i] = px
    nightph += 0.015 + state["speed"] * 0.001

# ---- reloj de agujas (port de neoclock) ----
_ck_s = 0
_ck_ms = 0

def _clock_now():
    # Segundos con fraccion, anclados al segundo real: monotono.
    # (mezclar la segunda del RTC con la fase de ticks_ms hacia parpadear el par de LEDs)
    global _ck_s, _ck_ms
    s = time.time()
    ms = time.ticks_ms()
    if s != _ck_s:
        _ck_s = s
        _ck_ms = ms
    return s + time.ticks_diff(ms, _ck_ms) / 1000.0

def _clock_add(i, c):
    i %= NUM
    p = _np[i]
    r = p[0] + c[0]
    g = p[1] + c[1]
    b = p[2] + c[2]
    if r > 255: r = 255
    if g > 255: g = 255
    if b > 255: b = 255
    _np[i] = (r, g, b)

def _clock_plot(pos, c):
    # Antialias: reparte el color entre dos LEDs (gamma ~2 para que no "camine").
    base = int(pos)
    frac = pos - base
    f0 = 1.0 - frac
    f0 = f0 * f0
    fr = frac * frac
    _clock_add(base, (int(c[0] * f0), int(c[1] * f0), int(c[2] * f0)))
    _clock_add(base + 1, (int(c[0] * fr), int(c[1] * fr), int(c[2] * fr)))

def fx_clock():
    # Hora en rojo, minuto en verde, segundo en azul. Necesita hora valida (NTP).
    t = time.localtime(time.time() + tz * 3600)
    h12 = t[3] % 12
    if h12 == 0:
        h12 = 12
    for i in range(NUM):
        _np[i] = (0, 0, 0)
    _clock_plot((h12 + t[4] / 60.0) / 12.0 * NUM, scaled((255, 60, 60)))
    _clock_plot(t[4] / 60.0 * NUM, scaled((60, 255, 60)))
    _clock_plot((_clock_now() % 60.0) / 60.0 * NUM, scaled((60, 60, 255)))

_RND_MODES = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21)
rnd_cur = 1
rnd_cnt = 0

def _run(m):
    if m == 0: fx_fixed()
    elif m == 1: fx_rainbow()
    elif m == 2: fx_fire()
    elif m == 3: fx_chase()
    elif m == 4: fx_breath()
    elif m == 5: fx_sparkle()
    elif m == 6: fx_bounce()
    elif m == 7: fx_halloween()
    elif m == 8: fx_navidad()
    elif m == 9: fx_sinelon()
    elif m == 10: fx_juggle()
    elif m == 11: fx_confetti()
    elif m == 12: fx_cylon()
    elif m == 13: fx_meteor()
    elif m == 14: fx_twinkle()
    elif m == 15: fx_pride()
    elif m == 16: fx_candle()
    elif m == 17: fx_lightning()
    elif m == 18: fx_police()
    elif m == 19: fx_glitter()
    elif m == 20: fx_pacifica()
    elif m == 21: fx_spectrum()
    elif m == 23: fx_night()
    elif m == 24: fx_clock()

def fx_random():
    # Va saltando de efecto en efecto cada cierto tiempo.
    global rnd_cur, rnd_cnt
    rnd_cnt += 1
    if rnd_cnt >= 90 - state["speed"] * 6 // 10:
        rnd_cnt = 0
        rnd_cur = random.choice(_RND_MODES)
    _run(rnd_cur)

def render():
    if not state["on"]:
        for i in range(NUM):
            _np[i] = (0, 0, 0)
        _np.write()
        return
    m = state["mode"]
    if m == 22: fx_random()
    else: _run(m)
    _np.write()

# ---------------- servidor HTTP (LAN) ----------------
# API minima (GET): /api/state, /api/set?bright=&speed=&hue=&sat=&mode=,
# /api/wifi?add=SSID&pass= | ?del=SSID, /api/ota, /api/reboot.
http_sock = None

def _jesc(s):
    out = ""
    for ch in s:
        if ch == '"' or ch == "\\":
            out += "\\" + ch
        elif ch == "\n":
            out += "\\n"
        elif ch == "\r":
            out += "\\r"
        else:
            out += ch
    return out

def _url_decode(s):
    s = s.replace("+", " ")
    out = ""
    i = 0
    while i < len(s):
        if s[i] == "%" and i + 2 < len(s):
            try:
                out += chr(int(s[i + 1:i + 3], 16))
                i += 3
                continue
            except Exception:
                pass
        out += s[i]
        i += 1
    return out

def _parse_qs(q):
    d = {}
    if not q:
        return d
    for kv in q.split("&"):
        if "=" in kv:
            k, v = kv.split("=", 1)
        else:
            k, v = kv, ""
        d[_url_decode(k)] = _url_decode(v)
    return d

def _clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)

# ---------------- luz nocturna (horario) ----------------
night_str = ""
night_active = False
night_saved = None
tz = -6
ntp_at = 0

def _mins(s):
    try:
        p = s.split(":")
        return int(p[0]) * 60 + int(p[1])
    except Exception:
        return -1

def _local_min():
    # Minutos del dia en hora local (tz en horas); -1 si la hora aun no es valida.
    t = time.localtime(time.time() + tz * 3600)
    if t[0] < 2020:
        return -1
    return t[3] * 60 + t[4]

def night_load():
    global night_str, tz
    c = load_cfg()
    tz = int(c.get("tz", -6))
    n = c.get("night") or {}
    night_str = "%s|%s|%s|%s" % (n.get("on", ""), n.get("off", ""), n.get("bright", 12), n.get("enabled", 0))

def night_set(on, off, bright, enabled, zone):
    global night_str, tz
    c = load_cfg()
    c["night"] = {"on": on, "off": off, "bright": _clamp(int(bright), 0, 255), "enabled": int(enabled)}
    if zone is not None:
        c["tz"] = int(zone)
        tz = int(zone)
    save_cfg(c)
    night_str = "%s|%s|%d|%d" % (on, off, c["night"]["bright"], c["night"]["enabled"])

def night_restore():
    global night_active, night_saved
    if night_saved:
        state["mode"], state["bright"], state["on"] = night_saved
        _push_ble()
    night_active = False

def night_check():
    global night_active, night_saved
    n = load_cfg().get("night") or {}
    if not n.get("enabled"):
        if night_active:
            night_restore()
        return
    on = _mins(n.get("on", ""))
    off = _mins(n.get("off", ""))
    mn = _local_min()
    if on < 0 or off < 0 or mn < 0:
        return
    inside = (on <= mn < off) if on <= off else (mn >= on or mn < off)
    if inside and not night_active:
        night_saved = (state["mode"], state["bright"], state["on"])
        state["mode"] = 23
        state["bright"] = _clamp(int(n.get("bright", 12)), 0, 255)
        state["on"] = 1
        _push_ble()
        night_active = True
    elif not inside and night_active:
        night_restore()

def _state_json():
    ip = ""
    ssid = ""
    try:
        if wlan is not None and wlan.isconnected():
            ip = wlan.ifconfig()[0]
            ssid = wlan.config("essid")
    except Exception:
        pass
    nets = ",".join('"%s"' % _jesc(s) for s in net_ssids())
    return ('{"dev":"AroLED","ver":"%s","bright":%d,"speed":%d,"hue":%d,"sat":%d,"mode":%d,"on":%d,'
            '"net":"%s","ip":"%s","ssid":"%s","netmode":"%s","night":"%s","nets":[%s]}'
            % (FW_VERSION, state["bright"], state["speed"], state["hue"],
               state["sat"], state["mode"], state["on"], _jesc(netmsg), ip, _jesc(ssid), netmode(),
               night_str, nets))

def _apply_param(k, v):
    if k == "bright":
        state["bright"] = _clamp(int(v), 0, 255)
    elif k == "speed":
        state["speed"] = _clamp(int(v), 0, 100)
    elif k == "hue":
        state["hue"] = _clamp(int(v), 0, 255)
    elif k == "sat":
        state["sat"] = _clamp(int(v), 0, 255)
    elif k == "mode":
        state["mode"] = _clamp(int(v), 0, 24)
    elif k == "on":
        state["on"] = _clamp(int(v), 0, 1)

def _push_ble():
    try:
        ble.gatts_write(h_bright, bytes([state["bright"]]))
        ble.gatts_write(h_speed,  bytes([state["speed"]]))
        ble.gatts_write(h_hue,    bytes([state["hue"]]))
        ble.gatts_write(h_mode,   bytes([state["mode"]]))
        ble.gatts_write(h_sat,    bytes([state["sat"]]))
        ble.gatts_write(h_on,     bytes([state["on"]]))
    except Exception:
        pass

def http_start():
    global http_sock
    try:
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", 80))
        s.listen(2)
        s.setblocking(False)
        http_sock = s
    except Exception as e:
        http_sock = None
        print("http:error", repr(e))

def http_ensure():
    if http_sock is None and wlan is not None and wlan.isconnected():
        http_start()

def _http_reply(c, body):
    r = ("HTTP/1.0 200 OK\r\n"
         "Content-Type: application/json\r\n"
         "Access-Control-Allow-Origin: *\r\n"
         "Content-Length: " + str(len(body)) + "\r\n"
         "Connection: close\r\n\r\n" + body)
    c.send(r.encode())

def http_handle(path, q):
    global pending
    if path == "/api/state":
        return _state_json()
    if path == "/api/set":
        for k in ("bright", "speed", "hue", "sat", "mode", "on"):
            if k in q:
                try:
                    _apply_param(k, q[k])
                except Exception:
                    pass
        _push_ble()
        return _state_json()
    if path == "/api/wifi":
        if "add" in q:
            add_net(q["add"], q.get("pass", ""))
            pending = "W\t" + q["add"] + "\t" + q.get("pass", "")
        elif "del" in q:
            del_net(q["del"])
        if "static" in q:
            try:
                c = load_cfg()
                c["static"] = q["static"]
                save_cfg(c)
            except Exception:
                pass
        return _state_json()
    if path == "/api/ota":
        pending = "U"
        return '{"ok":true,"msg":"ota iniciada"}'
    if path == "/api/reboot":
        pending = "R"
        return '{"ok":true,"msg":"reiniciando"}'
    if path == "/api/mode":
        m = q.get("set", "ble")
        pending = "M\t" + m
        return '{"ok":true,"mode":"' + m + '"}'
    if path == "/api/night":
        if "on" in q or "off" in q or "enabled" in q or "tz" in q:
            c = load_cfg().get("night") or {}
            on = q.get("on", c.get("on", ""))
            off = q.get("off", c.get("off", ""))
            br = q.get("bright", c.get("bright", 12))
            en = q.get("enabled", c.get("enabled", 0))
            night_set(on, off, br, en, q.get("tz", None))
        return _state_json()
    return '{"error":"ruta desconocida"}'

def http_poll():
    if http_sock is None:
        return
    try:
        c, _ = http_sock.accept()
    except Exception:
        return
    try:
        c.settimeout(1)
        req = c.recv(512)
        line = req.split(b"\r\n", 1)[0].decode("utf-8", "ignore")
        parts = line.split(" ")
        path = parts[1] if len(parts) > 1 else "/"
        q = ""
        if "?" in path:
            path, q = path.split("?", 1)
        body = http_handle(path, _parse_qs(q))
        _http_reply(c, body)
    except Exception:
        pass
    finally:
        try:
            c.close()
        except Exception:
            pass

# ---------------- boton fisico (BTN_PIN) ----------------
btn_last = 1
btn_at = 0

def button_poll():
    # Pulsacion corta: pasa al siguiente efecto (0..22).
    global btn_last, btn_at
    v = _btn.value()
    if v == 0:
        if btn_last == 1:
            btn_at = time.ticks_ms()
    elif btn_last == 0:
        if time.ticks_diff(time.ticks_ms(), btn_at) >= 25:
            state["mode"] = 0 if state["mode"] >= 22 else state["mode"] + 1
            _push_ble()
    btn_last = v

# ---------------- bucle principal ----------------
def loop():
    global pending, ntp_at
    stat_sent = None
    boot_at = time.ticks_ms()
    committed = False
    last = time.ticks_ms()
    night_at = time.ticks_ms()
    while True:
        button_poll()
        http_poll()
        if pending is not None:
            c = pending
            pending = None
            try:
                handle_cmd(c)
            except Exception:
                set_net("cmd:error")
        if netmsg != stat_sent:
            try:
                ble.gatts_write(h_stat, netmsg.encode())
            except Exception:
                pass
            stat_sent = netmsg
        if not committed and time.ticks_diff(time.ticks_ms(), boot_at) > 3000:
            _write_int(BOOTCNT_PATH, 0)
            committed = True
        now = time.ticks_ms()
        interval = 200 - state["speed"] * 2
        if interval < 8:
            interval = 8
        if state["mode"] == 24 and interval > 40:
            interval = 40  # el reloj barre suave (~25 fps)
        if time.ticks_diff(now, last) >= interval:
            last = now
            render()
        if time.ticks_diff(now, night_at) >= 10000:
            night_at = now
            try:
                night_check()
            except Exception:
                pass
            try:
                # Resincroniza la hora cada 6 h (el RTC se desvia sin NTP).
                if _wifi_up() and time.time() - ntp_at >= 21600:
                    import ntptime
                    ntptime.settime()
                    ntp_at = time.time()
            except Exception:
                pass
        time.sleep_ms(2)

def main():
    global netmsg, ntp_at
    # Resultado del ultimo arranque de red (wifi/ota), si lo hubo: se publica
    # por BLE y se borra.
    try:
        with open("status.txt") as f:
            netmsg = f.read().strip()
        os.remove("status.txt")
    except Exception:
        pass
    # Modo WiFi persistente: boot.py ya conecto la red; aqui solo se sirve la
    # API HTTP por LAN (BLE apagado: no pueden convivir). Si no hay WiFi, se
    # retrocede a BLE para no quedarse sin control.
    night_load()
    if netmode() == "wifi" and _wifi_up():
        try:
            netmsg = "wifi:ok " + wlan.ifconfig()[0]
        except Exception:
            netmsg = "wifi:ok"
        try:
            import ntptime
            ntptime.settime()
            ntp_at = time.time()
        except Exception:
            pass
        http_ensure()
        render()
        print("AroLED listo v" + FW_VERSION + " " + netmsg + " (HTTP"
              + ("" if http_sock is not None else " NOSOCK") + ")")
        loop()
        return
    # Modo BLE: el WiFi se hace en un arranque aparte (bandera mode.txt + reset).
    # Si venia en modo WiFi y la red no esta, el BLE NO arranca fiable en este
    # mismo arranque (el driver WiFi ya se inicializo): se pasa a BLE y se
    # reinicia para levantar el BLE limpio.
    if netmode() == "wifi":
        save_netmode("ble")
        machine.reset()
    start_ble()
    render()
    print("AroLED listo v" + FW_VERSION + " " + netmsg)
    loop()

boot_guard()
try:
    main()
except Exception as e:
    # Fallo al arrancar: dejar que boot_guard reintente y, si persiste, revierta.
    import sys
    try:
        sys.print_exception(e)
    except Exception:
        pass
    pending = None
    time.sleep_ms(500)
    machine.reset()
