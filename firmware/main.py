import bluetooth, machine, neopixel, time, struct, math, random
import os, json, network, socket
from micropython import const

_IRQ_DISCONNECT = const(2)
_IRQ_WRITE = const(3)

PIN = 23
NUM = 16

_np = neopixel.NeoPixel(machine.Pin(PIN), NUM)

SERVICE   = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890ab")
CH_BRIGHT = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a1")
CH_SPEED  = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a2")
CH_HUE    = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a3")
CH_MODE   = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a4")
CH_SAT    = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a5")
CH_CMD    = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a6")
CH_STAT   = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a7")

# ---------------- config / version (flash) ----------------
CFG_PATH = "cfg.json"
VER_PATH = "ver.txt"
OTA_URL  = "http://192.168.1.107:8800/ota/esp/aro-esp.json"

def load_cfg():
    try:
        with open(CFG_PATH) as f:
            return json.load(f)
    except Exception:
        return {"ssid": "", "pass": ""}

def save_cfg(c):
    try:
        with open(CFG_PATH, "w") as f:
            json.dump(c, f)
    except Exception:
        pass

def load_ver():
    try:
        with open(VER_PATH) as f:
            return f.read().strip()
    except Exception:
        return "0"

def save_ver(v):
    try:
        with open(VER_PATH, "w") as f:
            f.write(v)
    except Exception:
        pass

# ---------------- estado de red publicado por BLE ----------------
netmsg = "wifi:off"

def set_net(m):
    global netmsg
    netmsg = m
    try:
        ble.gatts_write(h_stat, m.encode())
    except Exception:
        pass

# ---------------- wifi ----------------
wlan = None

def wifi_connect(ssid, pw, tries=30):
    global wlan
    if not ssid:
        return False
    if wlan is None:
        wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        try:
            wlan.disconnect()
        except Exception:
            pass
        wlan.connect(ssid, pw)
    for _ in range(tries):
        if wlan.isconnected():
            return True
        time.sleep_ms(500)
    return wlan.isconnected()

def wifi_off():
    global wlan
    if wlan is not None:
        try:
            wlan.active(False)
        except Exception:
            pass

# ---------------- HTTP (LAN, sin TLS) ----------------
# ponytail: HTTP/1.0 plano y verificacion tamano+suma (servidor de confianza en LAN).
def http_get(url, timeout=15):
    if not url.startswith("http://"):
        return None
    rest = url[7:]
    i = rest.find("/")
    hostport = rest[:i] if i >= 0 else rest
    path = rest[i:] if i >= 0 else "/"
    if ":" in hostport:
        host, ps = hostport.split(":", 1)
        port = int(ps)
    else:
        host, port = hostport, 80
    data = None
    s = None
    try:
        addr = socket.getaddrinfo(host, port)[0][-1]
        s = socket.socket()
        s.settimeout(timeout)
        s.connect(addr)
        s.send(b"GET " + path.encode() + b" HTTP/1.0\r\nHost: " +
               host.encode() + b"\r\nConnection: close\r\n\r\n")
        buf = b""
        while True:
            d = s.recv(1024)
            if not d:
                break
            buf += d
        j = buf.find(b"\r\n\r\n")
        if j >= 0:
            data = buf[j + 4:]
    except Exception:
        data = None
    finally:
        if s:
            try:
                s.close()
            except Exception:
                pass
    return data

def ota_check():
    set_net("ota:consultando")
    raw = http_get(OTA_URL)
    if not raw:
        set_net("ota:sin respuesta")
        return
    try:
        m = json.loads(raw)
    except Exception:
        set_net("ota:json malo")
        return
    cur = load_ver()
    if m.get("version") == cur:
        set_net("ota:al dia " + cur)
        return
    set_net("ota:descargando")
    body = http_get(m["url"])
    if not body or len(body) != int(m.get("size", -1)):
        set_net("ota:error tamano")
        return
    if "sum" in m and (sum(body) & 65535) != int(m["sum"]):
        set_net("ota:error suma")
        return
    try:
        try:
            os.remove("main.bak")
        except Exception:
            pass
        with open("main.py.new", "wb") as f:
            f.write(body)
        os.rename("main.py", "main.bak")
        os.rename("main.py.new", "main.py")
        save_ver(m["version"])
    except Exception:
        set_net("ota:error escritura")
        return
    set_net("ota:ok " + str(m["version"]) + " reiniciando")
    time.sleep_ms(700)
    machine.reset()

# ---------------- arranque: wifi + OTA (antes de BLE) ----------------
_cfg = load_cfg()
if _cfg.get("ssid"):
    set_net("wifi:conectando")
    if wifi_connect(_cfg["ssid"], _cfg.get("pass", "")):
        set_net("wifi:ok " + wlan.ifconfig()[0])
        ota_check()
    else:
        set_net("wifi:error")
else:
    set_net("wifi:off")

# ---------------- BLE ----------------
# modo: 0 Fijo | 1 Arcoiris | 2 Fuego | 3 Cometa | 4 Latido | 5 Destellos | 6 Rebote
state = {"bright": 40, "speed": 50, "hue": 0, "sat": 255, "mode": 1}

ble = bluetooth.BLE()
ble.active(True)
ble.config(gap_name="AroLED")

((h_bright, h_speed, h_hue, h_mode, h_sat, h_cmd, h_stat),) = ble.gatts_register_services((
    (SERVICE, (
        (CH_BRIGHT, bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
        (CH_SPEED,  bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
        (CH_HUE,    bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
        (CH_MODE,   bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
        (CH_SAT,    bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
        (CH_CMD,    bluetooth.FLAG_WRITE),
        (CH_STAT,   bluetooth.FLAG_READ),
    )),
))

ble.gatts_write(h_bright, bytes([state["bright"]]))
ble.gatts_write(h_speed,  bytes([state["speed"]]))
ble.gatts_write(h_hue,    bytes([state["hue"]]))
ble.gatts_write(h_mode,   bytes([state["mode"]]))
ble.gatts_write(h_sat,    bytes([state["sat"]]))
ble.gatts_write(h_cmd,    bytes(20))
ble.gatts_write(h_stat,   netmsg.encode())

def advertise():
    nm = b"AroLED"
    payload = struct.pack("BBB", 2, 0x01, 0x06)
    payload += struct.pack("BB", len(nm) + 1, 0x09) + nm
    ble.gap_advertise(100000, adv_data=payload)

pending = None
cmd_buf = b""

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
        elif attr == h_cmd:
            cmd_buf += ble.gatts_read(h_cmd)
            k = cmd_buf.find(b"\x00")
            if k >= 0:
                pending = cmd_buf[:k].decode("utf-8", "ignore")
                cmd_buf = b""

ble.irq(_irq)
advertise()

# ---------------- comandos (fuera del IRQ) ----------------
def handle_cmd(c):
    global wlan
    if c.startswith("W"):
        parts = c.split("\t")
        ssid = parts[1] if len(parts) > 1 else ""
        pw = parts[2] if len(parts) > 2 else ""
        save_cfg({"ssid": ssid, "pass": pw})
        set_net("wifi:conectando")
        if wifi_connect(ssid, pw):
            set_net("wifi:ok " + wlan.ifconfig()[0])
        else:
            set_net("wifi:error")
    elif c == "C":
        cfg = load_cfg()
        set_net("wifi:conectando")
        if wifi_connect(cfg.get("ssid", ""), cfg.get("pass", "")):
            set_net("wifi:ok " + wlan.ifconfig()[0])
        else:
            set_net("wifi:error")
    elif c == "X":
        wifi_off()
        set_net("wifi:off")
    elif c == "U":
        ota_check()
    elif c == "R":
        set_net("reiniciando")
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
    global breath
    v = int((math.sin(breath) * 0.5 + 0.5) * 255)
    px = scaled(hsv(state["hue"], state["sat"], v))
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

def render():
    m = state["mode"]
    if m == 0: fx_fixed()
    elif m == 1: fx_rainbow()
    elif m == 2: fx_fire()
    elif m == 3: fx_chase()
    elif m == 4: fx_breath()
    elif m == 5: fx_sparkle()
    elif m == 6: fx_bounce()
    _np.write()

print("AroLED listo v" + load_ver() + " " + netmsg)

last = time.ticks_ms()
stat_sent = None
while True:
    if pending is not None:
        c = pending; pending = None
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
    now = time.ticks_ms()
    interval = 200 - state["speed"] * 2
    if interval < 8:
        interval = 8
    if time.ticks_diff(now, last) >= interval:
        last = now
        render()
    time.sleep_ms(2)
