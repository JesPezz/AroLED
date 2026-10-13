# net.py - WiFi (varias redes) + OTA por GitHub.
# Se usa SOLO desde boot.py, en un arranque dedicado (bandera mode.txt), porque
# en este ESP32 WiFi y BLE no pueden convivir en la misma sesion (EIO/crash).
# El resultado se deja en status.txt, que main.py publica por BLE al arrancar.
import network, time, json, os, gc, socket, machine

CFG = "cfg.json"
OTA_API = "https://api.github.com/repos/JesPezz/AroLED/releases/latest"
FW_VERSION = "2.9"   # mantener en sincronia con main.py


def _status(m):
    try:
        with open("status.txt", "w") as f:
            f.write(m)
    except Exception:
        pass


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
            time.sleep_ms(500)
        if w.isconnected():
            _save_last(c, n.get("ssid", ""))
            return w
    return None


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


OTA_FILES = ("main.py", "net.py", "boot.py")


def _asset(assets, name):
    for a in assets:
        if a.get("name") == name:
            return a.get("browser_download_url"), a.get("size")
    return None, None


def ota_check():
    raw = http_get(OTA_API, timeout=20)
    if not raw:
        _status("ota:sin respuesta")
        return
    try:
        rel = json.loads(raw)
        tag = rel.get("tag_name", "")
        assets = rel.get("assets", [])
    except Exception:
        _status("ota:json malo")
        return
    if _ver_key(tag) <= _ver_key(FW_VERSION):
        _status("ota:al dia " + FW_VERSION)
        return
    # Descargar y validar TODO en memoria antes de tocar nada.
    nuevos = {}
    for name in OTA_FILES:
        url, size = _asset(assets, name)
        if not url:
            if name == "main.py":
                _status("ota:sin asset")
                return
            continue
        _status("ota:descargando " + name)
        body = http_get(url, timeout=30, max_redirect=6)
        if not body:
            _status("ota:descarga fallo " + name)
            return
        # Integridad: sha256 es la autoridad; el tamano es solo respaldo.
        shaurl, _s = _asset(assets, name + ".sha256")
        verified = False
        if shaurl:
            shab = http_get(shaurl, timeout=15)
            if shab:
                import hashlib
                if hashlib.sha256(body).hexdigest() != shab.decode().split()[0].strip():
                    _status("ota:error sha256 " + name)
                    return
                verified = True
        if not verified and size is not None and len(body) != int(size):
            _status("ota:error tamano " + name)
            return
        try:
            compile(body, name, "exec")
        except Exception:
            _status("ota:error sintaxis " + name)
            return
        nuevos[name] = body
    # Escribir los .new primero; solo si todos se escriben, rotar a .bak.
    try:
        for name, body in nuevos.items():
            try:
                os.remove(name + ".bak")
            except Exception:
                pass
            with open(name + ".new", "wb") as f:
                f.write(body)
        for name in nuevos:
            os.rename(name, name + ".bak")
            os.rename(name + ".new", name)
        with open("bootcnt", "w") as f:
            f.write("0")
    except Exception:
        _status("ota:error escritura")
        return
    _status("ota:ok " + str(tag) + " reiniciando")
    time.sleep_ms(700)
    machine.reset()


def run(mode):
    w = connect_any()
    if not w:
        _status("wifi:error")
        return
    ip = w.ifconfig()[0]
    _status("wifi:ok " + ip)
    if mode == "ota":
        ota_check()          # si actualiza, reinicia
        _status("ota:al dia")
