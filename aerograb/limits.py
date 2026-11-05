# -*- coding: utf-8 -*-
import os
import threading
import re
import time
from datetime import datetime
from aerograb.common import get_setting, log_error
from aerograb.fmt import EXT_KIND, QUALITY_MAP


# ----------------------------------------------------------------------------- Limiter (ديناميكي)
class DownloadLimiter:
    """بيتحكم في عدد التحميلات المتزامنة. الدور بيتحدد بالأولوية (الأقل أولاً) وبوقت الجدولة (gate)."""
    def __init__(self, n, gate=None):
        self._n = max(1, n)
        self._active = 0
        self._cv = threading.Condition()
        self._waiting = {}
        self._seq = 0
        self._gate = gate or (lambda: True)

    def set_limit(self, n):
        with self._cv:
            self._n = max(1, n)
            self._cv.notify_all()

    def poke(self):
        with self._cv:
            self._cv.notify_all()

    def _key(self, wid):
        try:
            return (float(self._waiting[wid]()), wid)
        except Exception:
            return (float("inf"), wid)

    def acquire(self, should_abort, key=None):
        with self._cv:
            self._seq += 1
            me = self._seq
            self._waiting[me] = key or (lambda: me)
            try:
                while True:
                    if should_abort():
                        return False
                    if self._active < self._n and self._gate():
                        mine = self._key(me)
                        if all(mine <= self._key(o) for o in self._waiting if o != me):
                            self._active += 1
                            return True
                    self._cv.wait(0.4)
            finally:
                self._waiting.pop(me, None)
                self._cv.notify_all()

    def release(self):
        with self._cv:
            self._active -= 1
            self._cv.notify_all()



try:
    MAX_CONCURRENT_DOWNLOADS = max(1, min(6, int(get_setting("max_concurrent", 3))))
except Exception:
    MAX_CONCURRENT_DOWNLOADS = 3

def _start_allowed():
    from aerograb import usage
    return schedule_allows() and usage.allows()


limiter = DownloadLimiter(MAX_CONCURRENT_DOWNLOADS, gate=_start_allowed)


_default_quality_lock = threading.Lock()

_default_quality_plain = get_setting("default_quality", "1080p")

if _default_quality_plain not in QUALITY_MAP:
    _default_quality_plain = "1080p"



def get_default_quality_safe():
    with _default_quality_lock:
        return _default_quality_plain



def set_default_quality_safe(q):
    global _default_quality_plain
    with _default_quality_lock:
        _default_quality_plain = q



# ----------------------------------------------------------------------------- Speed limit (global)
class RateLimiter:
    """تحديد سرعة التحميل الكلية (KB/s). كل الاتصالات بتتشارك نفس الحصة."""
    def __init__(self):
        self._lock = threading.Lock()
        self.rate = 0
        self._tokens = 0.0
        self._t = time.monotonic()

    def set_rate(self, bytes_per_sec):
        with self._lock:
            self.rate = max(0, int(bytes_per_sec))
            self._tokens = 0.0
            self._t = time.monotonic()

    def consume(self, n, abort=None):
        if self.rate <= 0:
            return
        with self._lock:
            rate = self.rate
            if rate <= 0:
                return
            now = time.monotonic()
            self._tokens = min(rate * 0.5, self._tokens + (now - self._t) * rate)
            self._t = now
            self._tokens -= n
            wait = -self._tokens / rate if self._tokens < 0 else 0.0
        end = time.monotonic() + wait
        while True:
            left = end - time.monotonic()
            if left <= 0 or (abort is not None and abort()):
                return
            time.sleep(min(left, 0.2))



rate_limiter = RateLimiter()



def speed_limit_kbps():
    try:
        return max(0, int(get_setting("speed_limit_kbps", 0)))
    except Exception:
        return 0



def apply_speed_limit():
    rate_limiter.set_rate(speed_limit_kbps() * 1024)



def fmt_limit(kbps):
    if not kbps:
        return "Unlimited"
    return f"{kbps / 1024:g} MB/s" if kbps >= 1024 else f"{kbps} KB/s"



apply_speed_limit()



# ----------------------------------------------------------------------------- Scheduler
def _parse_hhmm(text):
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", text or "")
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return h * 60 + mi if 0 <= h < 24 and 0 <= mi < 60 else None



def schedule_allows(now=None):
    """هل مسموح نبدأ/نكمّل التحميل دلوقتي حسب الجدولة؟"""
    if not get_setting("schedule_enabled", False):
        return True
    start = _parse_hhmm(get_setting("schedule_start", ""))
    if start is None:
        return True
    stop = _parse_hhmm(get_setting("schedule_stop", ""))
    now = now or datetime.now()
    days = get_setting("schedule_days", list(range(7)))
    cur = now.hour * 60 + now.minute
    if stop is None:
        stop = 24 * 60                       # من وقت البداية لآخر اليوم
    if start <= stop:
        inside, day = start <= cur < stop, now.weekday()
    else:                                    # فترة بتعدي نص الليل (مثلاً 23:00 → 06:00): اليوم بيتحسب بيوم البداية
        inside = cur >= start or cur < stop
        day = now.weekday() if cur >= start else (now.weekday() - 1) % 7
    return inside and day in days



def schedule_wait_text():
    return f"⏰ Waiting for schedule (starts {get_setting('schedule_start', '--:--')})"



# ----------------------------------------------------------------------------- Categories (فولدر لكل نوع ملف)
CATEGORY_NAMES = {"video": "Video", "audio": "Music", "archive": "Compressed", "app": "Programs",
                  "doc": "Documents", "file": "General"}



def category_dir(base, filename, kind_hint=None):
    """فولدر الحفظ حسب نوع الملف (لو الميزة مفعّلة)."""
    if not get_setting("use_categories", False):
        return base
    ext = os.path.splitext(filename or "")[1].lstrip(".").lower()
    kind = EXT_KIND.get(ext) or kind_hint or "file"
    custom = (get_setting("cat_dirs", {}) or {}).get(kind)
    folder = custom or os.path.join(base, CATEGORY_NAMES.get(kind, "General"))
    try:
        os.makedirs(folder, exist_ok=True)
        return folder
    except Exception as e:
        log_error("category_dir", e)
        return base
