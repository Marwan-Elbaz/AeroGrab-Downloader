# -*- coding: utf-8 -*-
"""
عدّاد استهلاك الإنترنت + حد الاستهلاك (يومي / شهري / فترة مخصصة).

- add(n) بيتنادى من أماكن التحميل (المحمّل المباشر، التحميل المجزّأ، yt-dlp، وسيط القص) بعدد البايتات اللي نزلت فعلاً.
- الاستهلاك بيتحفظ لكل يوم في usage.json (آخر 400 يوم) فنقدر نحسب اليوم / الشهر / أي فترة.
- allows() بتقول هل لسه مسموح نحمّل. لما الحد يخلص: التحميلات الشغالة بتتوقف والجديدة بتستنى للفترة الجاية،
  أو المستخدم يختار "كمّل برضه" للفترة الحالية.
"""
import atexit
import calendar
import json
import os
import threading
import time
from datetime import date, datetime, timedelta

from aerograb.common import get_setting, log_error, save_settings
from aerograb.config import APP_DATA_DIR

USAGE_FILE = os.path.join(APP_DATA_DIR, "usage.json")
KEEP_DAYS = 400
MB = 1024 * 1024

_lock = threading.Lock()
_days = {}                  # "YYYY-MM-DD" -> bytes
_dirty = [False]
_last_save = [0.0]
_loaded = [False]
_events = []                # أحداث تنبيه لسه متعرضتش للمستخدم: ("warn"|"limit", period_key)


# ----------------------------------------------------------------------------- تخزين
def _load():
    if _loaded[0]:
        return
    _loaded[0] = True
    try:
        with open(USAGE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        days = raw.get("days", {}) if isinstance(raw, dict) else {}
        for k, v in days.items():
            if isinstance(k, str) and isinstance(v, (int, float)) and v >= 0:
                _days[k] = int(v)
    except FileNotFoundError:
        pass
    except Exception as e:
        log_error("usage load", e)


def _save_locked():
    try:
        keep = sorted(_days)[-KEEP_DAYS:]
        data = {"days": {k: _days[k] for k in keep}}
        os.makedirs(APP_DATA_DIR, exist_ok=True)
        tmp = USAGE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, USAGE_FILE)
        _dirty[0] = False
        _last_save[0] = time.monotonic()
    except Exception as e:
        log_error("usage save", e)


def flush():
    with _lock:
        _load()
        if _dirty[0]:
            _save_locked()


atexit.register(flush)


def add(n):
    """بيزوّد العدّاد بعدد بايتات نزلت (بيتنادى من أي thread، وخفيف)."""
    if not n or n <= 0:
        return
    key = date.today().isoformat()
    with _lock:
        _load()
        _days[key] = _days.get(key, 0) + int(n)
        _dirty[0] = True


def tick():
    """بتتنادى من الـ heartbeat: بتحفظ كل ~5 ثواني لو فيه تغيير."""
    if _dirty[0] and time.monotonic() - _last_save[0] > 5:
        with _lock:
            if _dirty[0]:
                _save_locked()


# ----------------------------------------------------------------------------- الفترة
PERIODS = ("day", "month", "custom")


def _parse_date(s):
    try:
        return datetime.strptime(str(s), "%Y-%m-%d").date()
    except Exception:
        return None


def _add_months(d, m):
    y, mo = divmod(d.year * 12 + (d.month - 1) + m, 12)
    mo += 1
    return date(y, mo, min(d.day, calendar.monthrange(y, mo)[1]))


def period_window(today=None):
    """(بداية، نهاية (مش شاملة)، النوع) للفترة اللي إحنا فيها دلوقتي."""
    today = today or date.today()
    kind = get_setting("quota_period", "month")
    if kind not in PERIODS:
        kind = "month"
    if kind == "day":
        return today, today + timedelta(days=1), kind
    if kind == "month":
        try:
            r = max(1, min(28, int(get_setting("quota_reset_day", 1))))
        except Exception:
            r = 1
        start = date(today.year, today.month, r)
        if today < start:
            start = _add_months(start, -1)
        return start, _add_months(start, 1), kind
    try:
        n = max(1, min(366, int(get_setting("quota_custom_days", 30))))
    except Exception:
        n = 30
    base = _parse_date(get_setting("quota_cycle_start", "")) or today
    k = (today - base).days // n
    start = base + timedelta(days=k * n)
    return start, start + timedelta(days=n), kind


def used_between(start, end):
    with _lock:
        _load()
        total = 0
        d = start
        while d < end:
            total += _days.get(d.isoformat(), 0)
            d += timedelta(days=1)
        return total


def used_today():
    with _lock:
        _load()
        return _days.get(date.today().isoformat(), 0)


def last_days(n=7):
    """[(date, bytes)] لآخر n يوم (الأقدم أولاً)."""
    today = date.today()
    with _lock:
        _load()
        return [(today - timedelta(days=i), _days.get((today - timedelta(days=i)).isoformat(), 0)) for i in range(n - 1, -1, -1)]


def total_all():
    with _lock:
        _load()
        return sum(_days.values())


# ----------------------------------------------------------------------------- الحد
def enabled():
    return bool(get_setting("quota_enabled", False)) and limit_bytes() > 0


def limit_bytes():
    try:
        return max(0, int(float(get_setting("quota_limit_mb", 0)) * MB))
    except Exception:
        return 0


def _period_key():
    s, e, kind = period_window()
    return f"{kind}:{s.isoformat()}"


def overridden():
    return get_setting("quota_override", "") == _period_key()


def snapshot():
    s, e, kind = period_window()
    used = used_between(s, e)
    lim = limit_bytes()
    on = bool(get_setting("quota_enabled", False)) and lim > 0
    frac = (used / lim) if on else 0.0
    return {
        "enabled": on, "kind": kind, "start": s, "end": e, "used": used, "limit": lim, "frac": frac,
        "exceeded": on and used >= lim, "overridden": overridden(), "today": used_today(),
    }


def allows():
    """هل مسموح نحمّل دلوقتي من ناحية حد الاستهلاك؟"""
    if not get_setting("quota_enabled", False):
        return True
    lim = limit_bytes()
    if lim <= 0 or overridden():
        return True
    s, e, _k = period_window()
    return used_between(s, e) < lim


def override_this_period():
    save_settings("quota_override", _period_key())


def reset_period_counter():
    """بيصفّر استهلاك الفترة الحالية."""
    s, e, _k = period_window()
    with _lock:
        _load()
        d = s
        while d < e:
            _days.pop(d.isoformat(), None)
            d += timedelta(days=1)
        _save_locked()
    save_settings("quota_warned", "")


def check_events():
    """
    بتتنادى من الـ heartbeat. بترجّع "warn" (وصلنا 90%) أو "limit" (الحد خلص) مرة واحدة بس لكل فترة، وإلا None.
    """
    if not get_setting("quota_enabled", False):
        return None
    snap = snapshot()
    if not snap["enabled"]:
        return None
    key = _period_key()
    warned = str(get_setting("quota_warned", ""))
    if snap["exceeded"] and not snap["overridden"] and warned != key + ":limit":
        save_settings("quota_warned", key + ":limit")
        return "limit"
    if snap["frac"] >= 0.9 and not snap["exceeded"] and warned not in (key + ":warn", key + ":limit"):
        save_settings("quota_warned", key + ":warn")
        return "warn"
    return None
