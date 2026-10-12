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

FW_VERSION = "2.0"

SERVICE   = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890ab")
CH_BRIGHT = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a1")
CH_SPEED  = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a2")
CH_HUE    = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a3")
CH_MODE   = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a4")
CH_SAT    = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a5")
CH_CMD    = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a6")
CH_STAT   = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a7")
CH_VER    = bluetooth.UUID("a0e1e0a0-1b1c-4a2b-8c3d-1234567890a8")

# ---------------- config / OTA ----------------
CFG_PATH     = "cfg.json"
BOOTCNT_PATH = "bootcnt"
OTA_API      = "https://api.github.com/repos/JesPezz/AroLED/releases/latest"

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
        _restore_bak()
        machine.reset()

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

# ---------------- HTTP/HTTPS ----------------
def _split_url(url):
    if url.startswith("https://"):
        scheme, rest = "https", url[8:]
    elif url.startswith("http://"):
        scheme, rest = "http", url[7:]
    else:
        return None
    i = rest.find("/")
    hostport = rest[:i] if i >= 0 else rest
    path = rest[i:] if i >= 0 else "/"
    if not hostport:
        return None
    if ":" in hostport:
        host, ps = hostport.split(":", 1)
        try:
            port = int(ps)
        except Exception:
            return None
    else:
        host = hostport
        port = 443 if scheme == "https" else 80
    return (scheme, host, port, path)

def _dechunk(s, data):
    out = b""
    while True:
        while b"\r\n" not in data:
            d = s.recv(1024)
            if not d:
                return out
            data += d
        line, data = data.split(b"\r\n", 1)
        try:
            size = int(line.split(b";")[0], 16)
        except Exception:
            return out
        if size == 0:
            return out
        while len(data) < size + 2:
            d = s.recv(1024)
            if not d:
                break
            data += d
        out += data[:size]
        data = data[size + 2:]

def _read_response(s):
    buf = b""
    j = -1
    while j < 0:
        d = s.recv(1024)
        if not d:
            break
        buf += d
        j = buf.find(b"\r\n\r\n")
    if j < 0:
        return None, {}, None
    head = buf[:j].decode("utf-8", "ignore")
    rest = buf[j + 4:]
    lines = head.split("\r\n")
    try:
        status = int(lines[0].split(" ")[1])
    except Exception:
        status = 0
    headers = {}
    for ln in lines[1:]:
        k = ln.find(":")
        if k > 0:
            headers[ln[:k].strip().lower()] = ln[k + 1:].strip()
    if "chunked" in headers.get("transfer-encoding", "").lower():
        body = _dechunk(s, rest)
    elif "content-length" in headers:
        n = int(headers["content-length"])
        body = rest
        while len(body) < n:
            d = s.recv(1024)
            if not d:
                break
            body += d
        body = body[:n]
    else:
        body = rest
        while True:
            d = s.recv(1024)
            if not d:
                break
            body += d
    return status, headers, body

def http_get(url, timeout=15, max_redirect=4):
    for _ in range(max_redirect + 1):
        parsed = _split_url(url)
        if parsed is None:
            return None
        scheme, host, port, path = parsed
        req = ("GET " + path + " HTTP/1.0\r\nHost: " + host +
               "\r\nUser-Agent: AroLED\r\nAccept: */*\r\nConnection: close\r\n\r\n").encode()
        s = None
        status = None
        headers = {}
        body = None
        try:
            addr = socket.getaddrinfo(host, port)[0][-1]
            s = socket.socket()
            s.settimeout(timeout)
            s.connect(addr)
            if scheme == "https":
                import ssl
                s = ssl.wrap_socket(s, server_hostname=host)
            s.send(req)
            status, headers, body = _read_response(s)
        except Exception:
            body = None
        finally:
            if s:
                try:
                    s.close()
                except Exception:
                    pass
        if status is None:
            return None
        if status in (301, 302, 303, 307, 308) and "location" in headers:
            loc = headers["location"]
            if loc.startswith("/"):
                loc = scheme + "://" + host + loc
            url = loc
            continue
        if status != 200:
            return None
        return body
    return None

def _ver_key(v):
    v = v.strip()
    if v[:1] in ("v", "V"):
        v = v[1:]
    v = v.split("-")[0].split("+")[0]
    nums = []
    for p in v.split("."):
        n = ""
        for ch in p:
            if ch.isdigit():
                n += ch
            else:
                break
        nums.append(int(n) if n else 0)
    while len(nums) < 2:
        nums.append(0)
    return nums[0] * 100 + nums[1]

def ota_check():
    set_net("ota:consultando")
    raw = http_get(OTA_API, timeout=20)
    if not raw:
        set_net("ota:sin respuesta")
        return
    try:
        rel = json.loads(raw)
        tag = rel.get("tag_name", "")
        assets = rel.get("assets", [])
    except Exception:
        set_net("ota:json malo")
        return
    if _ver_key(tag) <= _ver_key(FW_VERSION):
        set_net("ota:al dia " + FW_VERSION)
        return
    url = None
    size = None
    shaurl = None
    for a in assets:
        nm = a.get("name", "")
        if nm == "main.py":
            url = a.get("browser_download_url")
            size = a.get("size")
        elif nm == "main.py.sha256":
            shaurl = a.get("browser_download_url")
    if not url:
        set_net("ota:sin asset")
        return
    set_net("ota:descargando " + str(tag))
    body = http_get(url, timeout=30, max_redirect=6)
    if not body:
        set_net("ota:descarga fallo")
        return
    if size is not None and len(body) != int(size):
        set_net("ota:error tamano")
        return
    if shaurl:
        shab = http_get(shaurl, timeout=15)
        if shab:
            import hashlib
            exp = shab.decode().split()[0].strip()
            if hashlib.sha256(body).hexdigest() != exp:
                set_net("ota:error sha256")
                return
    # Validar sintaxis ANTES de sobrescribir: evita dejar el aro inservible.
    try:
        compile(body, "main.py", "exec")
    except Exception:
        set_net("ota:error sintaxis")
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
        _write_int(BOOTCNT_PATH, 0)
    except Exception:
        set_net("ota:error escritura")
        return
    set_net("ota:ok " + str(tag) + " reiniciando")
    time.sleep_ms(700)
    machine.reset()

# ---------------- arranque: wifi + OTA (antes de BLE) ----------------
def net_startup():
    cfg = load_cfg()
    if cfg.get("ssid"):
        set_net("wifi:conectando")
        if wifi_connect(cfg["ssid"], cfg.get("pass", "")):
            set_net("wifi:ok " + wlan.ifconfig()[0])
            ota_check()
        else:
            set_net("wifi:error")
    else:
        set_net("wifi:off")

# ---------------- BLE ----------------
# modo: 0 Fijo | 1 Arcoiris | 2 Fuego | 3 Cometa | 4 Latido | 5 Destellos |
#       6 Rebote | 7 Halloween | 8 Navidad
state = {"bright": 40, "speed": 50, "hue": 0, "sat": 255, "mode": 1}

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
        elif attr == h_cmd:
            cmd_buf += ble.gatts_read(h_cmd)
            k = cmd_buf.find(b"\x00")
            if k >= 0:
                pending = cmd_buf[:k].decode("utf-8", "ignore")
                cmd_buf = b""

def start_ble():
    global ble, h_bright, h_speed, h_hue, h_mode, h_sat, h_cmd, h_stat, h_ver
    ble = bluetooth.BLE()
    ble.active(True)
    ble.config(gap_name="AroLED")
    ((h_bright, h_speed, h_hue, h_mode, h_sat, h_cmd, h_stat, h_ver),) = ble.gatts_register_services((
        (SERVICE, (
            (CH_BRIGHT, bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
            (CH_SPEED,  bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
            (CH_HUE,    bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
            (CH_MODE,   bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
            (CH_SAT,    bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
            (CH_CMD,    bluetooth.FLAG_WRITE),
            (CH_STAT,   bluetooth.FLAG_READ),
            (CH_VER,    bluetooth.FLAG_READ),
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
hphase = 0.0
nphase = 0.0

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

def render():
    m = state["mode"]
    if m == 0: fx_fixed()
    elif m == 1: fx_rainbow()
    elif m == 2: fx_fire()
    elif m == 3: fx_chase()
    elif m == 4: fx_breath()
    elif m == 5: fx_sparkle()
    elif m == 6: fx_bounce()
    elif m == 7: fx_halloween()
    elif m == 8: fx_navidad()
    _np.write()

# ---------------- bucle principal ----------------
def loop():
    global pending
    stat_sent = None
    boot_at = time.ticks_ms()
    committed = False
    last = time.ticks_ms()
    while True:
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
        if time.ticks_diff(now, last) >= interval:
            last = now
            render()
        time.sleep_ms(2)

def main():
    global pending
    net_startup()
    start_ble()
    print("AroLED listo v" + FW_VERSION + " " + netmsg)
    loop()

boot_guard()
try:
    main()
except Exception:
    # Fallo al arrancar: dejar que boot_guard reintente y, si persiste, revierta.
    pending = None
    time.sleep_ms(500)
    machine.reset()
