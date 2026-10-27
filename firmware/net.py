# net.py - WiFi (varias redes) + OTA por GitHub.
# Se usa SOLO desde boot.py, en un arranque dedicado (bandera mode.txt), porque
# en este ESP32 WiFi y BLE no pueden convivir en la misma sesion (EIO/crash).
# El resultado se deja en status.txt, que main.py publica por BLE al arrancar.
import network, time, json, os, gc, socket, machine

CFG = "cfg.json"
REPO = "JesPezz/AroLED"
FW_VERSION = "5.18"   # mantener en sincronia con main.py
# Manifiesto: firmware/version.txt de la rama main. Se sirve directo desde
# raw.githubusercontent.com (un solo handshake TLS, el mas fiable en el ESP32);
# jsdelivr queda de respaldo. NO se usa api.github.com (su TLS cuelga).
RAW = "https://raw.githubusercontent.com/" + REPO
VERSION_URLS = (
    RAW + "/main/firmware/version.txt",
    "https://cdn.jsdelivr.net/gh/" + REPO + "@main/firmware/version.txt",
)
NUM = 16
PIN = 23

_np = None


def _status(m):
    try:
        with open("status.txt", "w") as f:
            f.write(m)
    except Exception:
        pass


# ---------------- LEDs: SIN feedback durante el arranque de red ----------------
# Aqui NO se escribe en la tira: machine.bitstream (RMT) deja el canal tomado
# apuntando al pin y despues main.py no consigue pintar nada (las escrituras no
# dan error pero los LEDs no cambian; el anillo se queda en el ultimo color, p.
# ej. el verde de "conectado"). La tira la usa SOLO main.py.
def _np_init():
    global _np
    _np = None


def _fill(rgb):
    return


_spin_i = 0


def _spin_step():
    # Punto azul girando = "trabajando" (conectar WiFi / descargar).
    global _spin_i
    if _np is None:
        return
    for i in range(NUM):
        _np[i] = (0, 0, 0)
    _np[_spin_i % NUM] = (0, 30, 255)
    _np.write()
    _spin_i += 1


def _blink(rgb, times=3):
    if _np is None:
        return
    for _ in range(times):
        _fill(rgb)
        time.sleep_ms(150)
        _fill((0, 0, 0))
        time.sleep_ms(120)
    _fill(rgb)
    time.sleep_ms(400)
    _fill((0, 0, 0))


def _done_ok():
    _blink((0, 200, 0))       # verde: termino bien


def _done_err():
    _blink((200, 0, 0))       # rojo: error


# ---------------- config / wifi ----------------
def load_cfg():
    try:
        with open(CFG) as f:
            return json.load(f)
    except Exception:
        return {}


def _nets(c):
    ns = c.get("nets")
    if ns:
        return ns
    if c.get("ssid"):
        return [{"ssid": c["ssid"], "pass": c.get("pass", "")}]
    return []


def _save_last(c, ssid):
    c["last"] = ssid
    try:
        with open(CFG, "w") as f:
            json.dump(c, f)
    except Exception:
        pass


def connect_any():
    c = load_cfg()
    nets = _nets(c)
    if not nets:
        return None
    last = c.get("last", "")
    order = sorted(nets, key=lambda n: 0 if n.get("ssid") == last else 1)
    w = network.WLAN(network.STA_IF)
    w.active(True)
    for n in order:
        try:
            w.disconnect()
        except Exception:
            pass
        try:
            w.connect(n.get("ssid", ""), n.get("pass", ""))
        except Exception:
            continue
        for _ in range(16):
            if w.isconnected():
                break
            _spin_step()
            time.sleep_ms(500)
        if w.isconnected():
            _save_last(c, n.get("ssid", ""))
            _static(c, w)
            return w
    return None


def _static(c, w):
    # IP fija opcional (cfg["static"]); vacio = DHCP.
    ip = c.get("static", "")
    if ip:
        try:
            w.ifconfig((ip, "255.255.255.0", "192.168.1.1", "8.8.8.8"))
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


def _read_head(s):
    # Lee solo las cabeceras; devuelve (status, headers, resto_ya_leido).
    buf = b""
    j = -1
    while j < 0:
        d = s.recv(512)
        if not d:
            break
        buf += d
        j = buf.find(b"\r\n\r\n")
    if j < 0:
        return None, {}, b""
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
    return status, headers, rest


def _stream_body(s, headers, rest, dest):
    # Escribe el cuerpo DIRECTAMENTE al fichero, en trozos de 512 B (poca RAM).
    f = open(dest, "wb")
    total = 0
    k = 0
    try:
        chunked = "chunked" in headers.get("transfer-encoding", "").lower()
        n = int(headers["content-length"]) if "content-length" in headers else -1
        data = rest
        if chunked:
            while True:
                while b"\r\n" not in data:
                    d = s.recv(512)
                    if not d:
                        return total
                    data += d
                line, data = data.split(b"\r\n", 1)
                try:
                    size = int(line.split(b";")[0], 16)
                except Exception:
                    return total
                if size == 0:
                    return total
                while len(data) < size + 2:
                    d = s.recv(512)
                    if not d:
                        break
                    data += d
                f.write(data[:size])
                total += size
                data = data[size + 2:]
                k += 1
                if k % 8 == 0:
                    _spin_step()
        elif n >= 0:
            if data:
                take = data[:n]
                f.write(take)
                total += len(take)
            while total < n:
                d = s.recv(512)
                if not d:
                    break
                d = d[:n - total]
                f.write(d)
                total += len(d)
                k += 1
                if k % 8 == 0:
                    _spin_step()
        else:
            if data:
                f.write(data)
                total += len(data)
            while True:
                d = s.recv(512)
                if not d:
                    break
                f.write(d)
                total += len(d)
                k += 1
                if k % 8 == 0:
                    _spin_step()
    finally:
        f.close()
    return total


def _download(url, dest, timeout=30, max_redirect=6):
    # Descarga a disco en streaming. Devuelve bytes escritos o None.
    for _ in range(max_redirect + 1):
        parsed = _split_url(url)
        if parsed is None:
            return None
        scheme, host, port, path = parsed
        req = ("GET " + path + " HTTP/1.0\r\nHost: " + host +
               "\r\nUser-Agent: AroLED\r\nAccept: */*\r\nConnection: close\r\n\r\n").encode()
        s = None
        try:
            addr = socket.getaddrinfo(host, port)[0][-1]
            s = socket.socket()
            s.settimeout(timeout)
            gc.collect()
            s.connect(addr)
            if scheme == "https":
                import ssl
                s = ssl.wrap_socket(s, server_hostname=host)
            s.send(req)
            status, headers, rest = _read_head(s)
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
            return _stream_body(s, headers, rest, dest)
        except Exception:
            return None
        finally:
            if s:
                try:
                    s.close()
                except Exception:
                    pass
    return None


def _file_sha256(path):
    import hashlib, ubinascii
    h = hashlib.sha256()
    f = open(path, "rb")
    try:
        while True:
            c = f.read(512)
            if not c:
                break
            h.update(c)
    finally:
        f.close()
    return ubinascii.hexlify(h.digest()).decode()


def http_get(url, timeout=15, max_redirect=4):
    # Solo para respuestas pequenas (API de GitHub, ficheros .sha256).
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
            gc.collect()
            s.connect(addr)
            if scheme == "https":
                import ssl
                s = ssl.wrap_socket(s, server_hostname=host)
            s.send(req)
            status, headers, rest = _read_head(s)
            if status is None:
                return None
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


OTA_FILES = ("main.py", "net.py", "boot.py", "led.py")


def _cdn_url(tag, name):
    # raw.githubusercontent.com sirve el fichero versionado en git DIRECTAMENTE
    # (un solo handshake TLS, sin redireccion): lo mas fiable en el ESP32.
    return RAW + "/" + tag + "/firmware/" + name


def _cdn2_url(tag, name):
    return "https://cdn.jsdelivr.net/gh/" + REPO + "@" + tag + "/firmware/" + name


def _fetch_text(urls, tries=5):
    # Primer texto que responda; las fallas de raw.githack son rapidas.
    for src in urls:
        for _ in range(tries):
            gc.collect()
            raw = http_get(src, timeout=8)
            if raw:
                return raw.decode("utf-8", "ignore").strip()
    return None


def _fetch_file(tag, name, dest, tries=5):
    # Descarga a disco desde el CDN (ECDSA). Devuelve bytes o 0.
    for _ in range(tries):
        for src in (_cdn_url(tag, name), _cdn2_url(tag, name)):
            gc.collect()
            n = _download(src, dest, timeout=30, max_redirect=6)
            if n:
                return n
    return 0


def ota_check():
    # Devuelve "ok", "al dia" o "err" (y deja el detalle en status.txt).
    # El manifiesto (version.txt de main) trae la version y el sha256 de cada
    # fichero: se verifica el hash (streaming, poca RAM) en vez de compilar.
    gc.collect()
    txt = _fetch_text(VERSION_URLS)
    if not txt:
        _status("ota:sin manifiesto")
        return "err"
    lines = txt.split("\n")
    tag = lines[0].strip().split()[0] if lines[0].strip() else ""
    if not tag:
        _status("ota:manifiesto malo")
        return "err"
    if _ver_key(tag) <= _ver_key(FW_VERSION):
        _status("ota:al dia")
        return "al dia"
    hashes = {}
    for ln in lines[1:]:
        p = ln.split()
        if len(p) >= 2:
            hashes[p[0]] = p[1].strip().lower()
    pend = []
    for name in OTA_FILES:
        _status("ota:descargando " + name)
        dest = name + ".new"
        n = _fetch_file(tag, name, dest)
        if not n:
            _status("ota:descarga fallo " + name)
            return "err"
        want = hashes.get(name)
        if want and _file_sha256(dest) != want:
            _status("ota:error hash " + name)
            return "err"
        pend.append(name)
    # Escribir/rotar solo al final (todos los .new ya estan en disco).
    try:
        for name in pend:
            try:
                os.remove(name + ".bak")
            except Exception:
                pass
            os.rename(name, name + ".bak")
            os.rename(name + ".new", name)
        with open("bootcnt", "w") as f:
            f.write("0")
    except Exception:
        _status("ota:error escritura")
        return "err"
    _status("ota:ok " + str(tag))
    return "ok"


def run(mode):
    _np_init()
    w = connect_any()
    if not w:
        _status("wifi:error")
        _done_err()
        time.sleep_ms(500)
        machine.reset()
        return
    ip = w.ifconfig()[0]
    _status("wifi:ok " + ip)
    if mode == "ota":
        r = ota_check()
        if r == "ok":
            _done_ok()
        elif r == "al dia":
            _status("ota:al dia " + FW_VERSION)
            _done_ok()
        else:
            _done_err()
    else:
        _done_ok()
    time.sleep_ms(500)
    machine.reset()


def netmode():
    # Modo persistente: "ble" (por defecto) o "wifi" (API HTTP en LAN, sin BLE).
    try:
        with open("netmode.txt") as f:
            m = f.read().strip()
        if m in ("ble", "wifi"):
            return m
    except Exception:
        pass
    return "ble"


def run_wifi_mode():
    # Modo WiFi persistente: conecta y NO reinicia; main.py servira la API HTTP
    # (BLE apagado). Si no conecta, deja el error y main.py arranca en BLE.
    _np_init()
    w = connect_any()
    if not w:
        _status("wifi:error")
        _done_err()
        return False
    _status("wifi:ok " + w.ifconfig()[0])
    _done_ok()
    return True
