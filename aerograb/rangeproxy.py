# -*- coding: utf-8 -*-
"""
وسيط محلي (127.0.0.1) بين ffmpeg والسيرفر عشان "تحميل جزء من فيديو" يستخدم أكتر من اتصال.

ffmpeg بيقرأ الرابط باتصال واحد، ويوتيوب وغيره بيخنقوا الاتصال الواحد. هنا ffmpeg بيقرأ من الوسيط (نفس الـ -ss / Range زي ما هو)
والوسيط بيقسّم كل طلب لقطع صغيرة بيجيبها من السيرفر بعدة اتصالات في نفس الوقت ويرجّعها لـ ffmpeg بالترتيب.
بيتحمّل بس الجزء اللي ffmpeg بيطلبه فعلاً (مش الفيديو كله). لو السيرفر مش بيدعم Range بنمرّر الطلب زي ما هو.
"""
import logging
import threading
import urllib.error
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from aerograb import usage
from aerograb.limits import rate_limiter
from aerograb.netutil import _urlopen

CHUNK = 512 << 10                      # حجم القطعة الواحدة اللي بتتجاب باتصال
FETCH_TRIES = 4


class _Source:
    def __init__(self, url, headers):
        self.url = url
        self.headers = dict(headers or {})
        self.total = 0
        self.ranged = False
        self.ctype = "application/octet-stream"
        self._probed = False
        self._lock = threading.Lock()

    def probe(self):
        with self._lock:
            if self._probed:
                return
            h = dict(self.headers)
            h["Range"] = "bytes=0-0"
            try:
                with _urlopen(urllib.request.Request(self.url, headers=h), timeout=25) as r:
                    self.ctype = r.headers.get("Content-Type") or self.ctype
                    tail = (r.headers.get("Content-Range") or "").rsplit("/", 1)[-1]
                    if r.status == 206 and tail.isdigit():
                        self.total, self.ranged = int(tail), True
                    else:
                        cl = r.headers.get("Content-Length")
                        self.total = int(cl) if cl and cl.isdigit() else 0
            except Exception as e:
                logging.info(f"range proxy probe failed: {e}")
            self._probed = True

    def fetch(self, a, b, stop):
        """بايتات a..b (شاملة) من السيرفر، مع إعادة محاولة. بيرمي استثناء لو فشل."""
        last = None
        for attempt in range(FETCH_TRIES):
            if stop.is_set():
                raise InterruptedError("stopped")
            try:
                h = dict(self.headers)
                h["Range"] = f"bytes={a}-{b}"
                with _urlopen(urllib.request.Request(self.url, headers=h), timeout=30) as r:
                    if r.status != 206:
                        raise IOError("server ignored the range")
                    data = r.read()
                if len(data) != b - a + 1:
                    raise IOError("short read")
                usage.add(len(data))
                return data
            except urllib.error.HTTPError as e:
                last = e
                if e.code not in (403, 429, 500, 502, 503, 504):
                    raise
            except (OSError, IOError) as e:
                last = e
            stop.wait(min(1.0 * (attempt + 1), 4.0))
        raise last or IOError("fetch failed")


class RangeProxy:
    def __init__(self, connections=8):
        self.conns = max(1, min(16, int(connections)))
        self._sources = {}
        self._n = 0
        self._stop = threading.Event()
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_HEAD(self):
                self._serve(head=True)

            def do_GET(self):
                self._serve(head=False)

            def _serve(self, head):
                try:
                    src = proxy._sources.get(self.path.strip("/"))
                    if src is None:
                        self.send_error(404)
                        return
                    src.probe()
                    if not src.ranged or not src.total:
                        self._passthrough(src, head)
                        return
                    total = src.total
                    a, b = 0, total - 1
                    rng = self.headers.get("Range")
                    partial = False
                    if rng and rng.startswith("bytes="):
                        s, _, e = rng[6:].split(",")[0].partition("-")
                        if s == "":                      # bytes=-N (آخر N بايت)
                            a = max(0, total - int(e))
                        else:
                            a = int(s)
                            b = min(int(e), total - 1) if e else total - 1
                        partial = True
                    if a >= total or a > b:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{total}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    self.send_response(206 if partial else 200)
                    self.send_header("Content-Type", src.ctype)
                    self.send_header("Accept-Ranges", "bytes")
                    if partial:
                        self.send_header("Content-Range", f"bytes {a}-{b}/{total}")
                    self.send_header("Content-Length", str(b - a + 1))
                    self.end_headers()
                    if head:
                        return
                    self._stream(src, a, b)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, InterruptedError):
                    pass
                except Exception as e:
                    logging.info(f"range proxy request failed: {e}")

            def _stream(self, src, a, b):
                abort = threading.Event()           # بيقفل لما ffmpeg يقطع الاتصال أو الوسيط يتقفل
                ex = ThreadPoolExecutor(max_workers=proxy.conns)
                pend = deque()                      # (future, length)
                nxt = [a]
                delivered = [0]

                def fill():
                    # التحميل المسبق بيبدأ قطعة واحدة وبيتضاعف مع اللي ffmpeg بيقراه فعلاً (لحد عدد الاتصالات). كده طلب بيتقطع بعد
                    # الهيدر أو بعد آخر الجزء مايسحبش عشرات الميجابايتات على الفاضي (ده كان بيضيّع نت وبيزوّد العدّاد).
                    allow = min(proxy.conns * CHUNK, max(CHUNK, delivered[0]))
                    while nxt[0] <= b and not abort.is_set():
                        s_, e_ = nxt[0], min(nxt[0] + CHUNK - 1, b)
                        inflight = sum(ln for _f, ln in pend)
                        if pend and inflight + (e_ - s_ + 1) > allow:
                            break
                        nxt[0] = e_ + 1
                        pend.append((ex.submit(src.fetch, s_, e_, abort), e_ - s_ + 1))

                try:
                    fill()
                    while pend:
                        fut, ln = pend.popleft()
                        data = fut.result()
                        delivered[0] += ln
                        fill()
                        rate_limiter.consume(len(data), lambda: abort.is_set() or proxy._stop.is_set())
                        self.wfile.write(data)
                finally:
                    abort.set()
                    ex.shutdown(wait=False, cancel_futures=True)

            def _passthrough(self, src, head):
                h = dict(src.headers)
                if self.headers.get("Range"):
                    h["Range"] = self.headers["Range"]
                with _urlopen(urllib.request.Request(src.url, headers=h, method="HEAD" if head else "GET"), timeout=30) as r:
                    self.send_response(r.status)
                    for k in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
                        if r.headers.get(k):
                            self.send_header(k, r.headers[k])
                    self.end_headers()
                    if head:
                        return
                    while not proxy._stop.is_set():
                        data = r.read(262144)
                        if not data:
                            break
                        rate_limiter.consume(len(data), proxy._stop.is_set)
                        usage.add(len(data))
                        self.wfile.write(data)

        class _Server(ThreadingHTTPServer):
            daemon_threads = True

        self._server = _Server(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True,
                         name="aerograb-range-proxy").start()

    def add(self, url, headers=None):
        """بيسجّل رابط ويرجّع رابط محلي لـ ffmpeg."""
        self._n += 1
        key = f"s{self._n}"
        self._sources[key] = _Source(url, headers)
        return f"http://127.0.0.1:{self.port}/{key}"

    def close(self):
        self._stop.set()
        try:
            self._server.shutdown()
            self._server.server_close()
        except Exception:
            pass
