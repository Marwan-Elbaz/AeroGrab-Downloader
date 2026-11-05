# -*- coding: utf-8 -*-
import os
import json
import urllib.request, urllib.parse, urllib.error
import socket
import logging, logging.handlers
import time
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from aerograb.common import get_ipc_token, log_error
from aerograb.config import APP_VERSION, IS_WINDOWS, PORT
from aerograb.fmt import QUALITY_MAP, is_valid_url
from aerograb.lazyviews import dispatch_add_item, show_link_grabber, wake_up_window
from aerograb.limits import get_default_quality_safe
from aerograb.mediainfo import EXT_ORIGIN_RE, _recent_adds, _recent_lock, get_qualities_cached
from aerograb.netutil import _urlopen
from aerograb.capture import capture_config, program_language
from aerograb.state import ext_info, gui_lock, pending_batches, pending_urls, show_gui_event, ui
from aerograb.uistate import gui


def _is_duplicate_add(key, window=4.0):
    now = time.time()
    with _recent_lock:
        for k in [k for k, t in _recent_adds.items() if now - t > window]:
            del _recent_adds[k]
        if key in _recent_adds:
            return True
        _recent_adds[key] = now
        return False



class RequestHandler(BaseHTTPRequestHandler):
    server_version = "IDMModernPro"

    # --- أمان: بنقبل بس (1) الإضافة (2) النسخة التانية من البرنامج بالـ token. أي صفحة ويب عادية بتترفض.
    def _auth(self):
        host = (self.headers.get("Host") or "").lower()
        if host not in (f"127.0.0.1:{PORT}", f"localhost:{PORT}"):
            return None                       # حماية من DNS rebinding
        origin = self.headers.get("Origin")
        if origin and not EXT_ORIGIN_RE.match(origin):
            return None                       # الطلب جاي من صفحة ويب
        if self.headers.get("X-IDM-Token") == get_ipc_token():
            return origin or ""
        if self.headers.get("X-IDM-Client") == "extension":
            return origin or ""
        return None

    def _send(self, code, body=b"", ctype="text/plain; charset=utf-8", origin=""):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, obj, origin):
        self._send(200, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8", origin)

    def do_OPTIONS(self):
        origin = self.headers.get("Origin", "")
        if origin and EXT_ORIGIN_RE.match(origin):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "X-IDM-Client, X-IDM-Token, Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self._send(403)

    def do_GET(self):
        try:
            origin = self._auth()
            if origin is None:
                self._send(403)
                return
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            qs = urllib.parse.parse_qs(parsed.query)

            def arg(name, default=""):
                return qs.get(name, [default])[0]

            if path == "/ping":
                self._json({"app": "idm-modern-pro", "version": APP_VERSION, "gui": gui.gui_running}, origin)
            elif path == "/get_settings":
                ext_info["t"], ext_info["v"] = time.time(), arg("v")[:20]
                self._json(capture_config(), origin)
            elif path == "/get_lang":
                self._send(200, program_language(), origin=origin)
            elif path == "/get_default_quality":
                self._send(200, get_default_quality_safe(), origin=origin)
            elif path == "/get_qualities":
                self._json(list(QUALITY_MAP.keys()), origin)
            elif path == "/get_video_formats":
                url = arg("url")
                if not is_valid_url(url):
                    self._send(400, "bad url", origin=origin)
                    return
                self._json(get_qualities_cached(url), origin)
            elif path == "/add":
                url = arg("url").strip()
                if not is_valid_url(url):
                    self._send(400, "bad url", origin=origin)
                    return
                quality = arg("quality") or get_default_quality_safe()
                if quality not in QUALITY_MAP:
                    quality = get_default_quality_safe()
                referer = arg("referer")
                referer = referer if is_valid_url(referer) else ""
                clip = arg("clip") == "1"
                playlist = arg("playlist") if arg("playlist") in ("all", "pick") else ""
                if not _is_duplicate_add((url, quality, clip, playlist)):
                    direct = arg("direct") == "1"
                    cookie, ua = arg("cookie")[:8000], arg("ua")[:300]
                    item = {"url": url, "quality": quality, "referer": referer, "direct": direct, "cookie": cookie, "ua": ua,
                            "clip": clip, "playlist": playlist}
                    with gui_lock:
                        if not gui.gui_running:
                            pending_urls.append(item)
                            show_gui_event.set()
                        else:
                            ui(wake_up_window)
                            ui(dispatch_add_item, item)
                self._send(200, "Added", origin=origin)
            elif path == "/wakeup":
                with gui_lock:
                    if not gui.gui_running:
                        show_gui_event.set()
                    else:
                        ui(wake_up_window)
                self._send(200, "OK", origin=origin)
            else:
                self._send(404, origin=origin)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            log_error("do_GET", e)
            try:
                self._send(500)
            except Exception:
                pass

    def do_POST(self):
        try:
            origin = self._auth()
            if origin is None:
                self._send(403)
                return
            path = urllib.parse.urlparse(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 8_000_000:
                self._send(400, "bad length", origin=origin)
                return
            body = self.rfile.read(length)
            if path != "/add_batch":
                self._send(404, origin=origin)
                return
            data = json.loads(body.decode("utf-8"))
            items, seen = [], set()
            for it in (data.get("items") or [])[:5000]:
                u = (it.get("url") or "").strip() if isinstance(it, dict) else ""
                if is_valid_url(u) and u not in seen:
                    seen.add(u)
                    items.append({"url": u, "text": str(it.get("text") or "")[:200]})
            if not items:
                self._send(400, "no links", origin=origin)
                return
            referer = data.get("referer") or ""
            referer = referer if is_valid_url(referer) else ""
            batch = {"items": items, "referer": referer, "cookie": str(data.get("cookie") or "")[:8000],
                     "ua": str(data.get("ua") or "")[:300]}
            with gui_lock:
                if not gui.gui_running:
                    pending_batches.append(batch)
                    show_gui_event.set()
                else:
                    ui(wake_up_window)
                    ui(show_link_grabber, batch["items"], referer, batch["cookie"], batch["ua"])
            self._send(200, "Added", origin=origin)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            log_error("do_POST", e)
            try:
                self._send(500)
            except Exception:
                pass

    def log_message(self, fmt, *args):
        pass



class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    # على Windows: SO_REUSEADDR بيسمح بأكتر من نسخة على نفس البورت، فبنقفله (ونستخدم EXCLUSIVEADDRUSE تحت).
    # على Linux/macOS: بيتخطى TIME_WAIT بس (مبيسمحش بنسختين)، وبنحتاجه عشان إعادة التشغيل السريعة تشتغل.
    allow_reuse_address = (os.name != "nt")

    def server_bind(self):
        if IS_WINDOWS and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()



_server = None



def check_single_instance(retry_seconds=0):
    global _server
    deadline = time.time() + retry_seconds
    while True:
        try:
            _server = LocalServer(("127.0.0.1", PORT), RequestHandler)
            return True
        except OSError:
            if time.time() >= deadline:
                return False
            time.sleep(0.3)



def start_local_server():
    try:
        _server.serve_forever(poll_interval=0.3)
    except Exception as e:
        log_error("start_local_server", e)



def forward_to_running_instance(url, quality):
    """النسخة التانية بتبعت للأولى (لو شغالة). بترجّع True لو اتسلّمت."""
    try:
        if url:
            q = f"&quality={urllib.parse.quote(quality, safe='')}" if quality else ""
            target = f"http://127.0.0.1:{PORT}/add?url={urllib.parse.quote(url, safe='')}{q}"
        else:
            target = f"http://127.0.0.1:{PORT}/wakeup"
        req = urllib.request.Request(target, headers={"X-IDM-Token": get_ipc_token()})
        with _urlopen(req, timeout=3) as r:
            return r.status == 200
    except Exception as e:
        logging.info(f"forward failed: {e}")
        return False


def shutdown_server():
    """بيقفل السيرفر المحلي (بتتنادى قبل إعادة التشغيل في الخلفية)."""
    try:
        _server.shutdown()
        _server.server_close()
    except Exception:
        pass

