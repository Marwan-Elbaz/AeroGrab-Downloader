# -*- coding: utf-8 -*-
import os
import threading
import logging, logging.handlers
import re
import itertools
from aerograb.common import get_setting, log_error
from aerograb.netutil import _host


# ----------------------------------------------------------------------------- Batch patterns:  http://site/img[001-050].jpg
def expand_patterns(url, limit=5000):
    """[001-050] أرقام (بنفس عدد الخانات)  و  [a-e] حروف. بيرجّع قايمة روابط."""
    parts = re.split(r"(\[[0-9a-zA-Z]+-[0-9a-zA-Z]+\])", url)
    pools = []
    for part in parts:
        m = re.fullmatch(r"\[([0-9]+)-([0-9]+)\]", part)
        if m:
            a, b = m.group(1), m.group(2)
            lo, hi = int(a), int(b)
            if lo > hi:
                lo, hi = hi, lo
            width = len(a) if a.startswith("0") and len(a) > 1 else 0
            pools.append([str(n).zfill(width) for n in range(lo, hi + 1)])
            continue
        m = re.fullmatch(r"\[([a-zA-Z])-([a-zA-Z])\]", part)
        if m and m.group(1).islower() == m.group(2).islower():
            lo, hi = sorted((ord(m.group(1)), ord(m.group(2))))
            pools.append([chr(c) for c in range(lo, hi + 1)])
            continue
        pools.append([part])
    total = 1
    for pool in pools:
        total *= len(pool)
        if total > limit:
            raise ValueError(f"The pattern expands to more than {limit} links.")
    return ["".join(c) for c in itertools.product(*pools)]



def cookie_for(url, referer, cookie):
    """كوكيز الصفحة بتتبعت بس للروابط اللي من نفس الموقع (أو subdomain منه)."""
    if not cookie:
        return ""
    a, b = _host(url), _host(referer)
    a, b = a[4:] if a.startswith("www.") else a, b[4:] if b.startswith("www.") else b
    if a and b and (a == b or a.endswith("." + b) or b.endswith("." + a)):
        return cookie
    return ""



def extract_urls(text):
    """كل الروابط http/https في نص (ملف txt مثلاً)."""
    seen, out = set(), []
    for u in re.findall(r"https?://[^\s<>\"'\\]+", text or ""):
        u = u.rstrip(".,;)]}")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out



# ----------------------------------------------------------------------------- Files cleanup
def _related_files(path):
    """الملف نفسه + ملفاته الجانبية فقط (.part / صورة مصغرة / ستريمات .f137) — من غير ما نلمس أي ملف تاني."""
    out = set()
    if not path:
        return out
    out.add(path)
    folder, name = os.path.split(path)
    n = name
    changed = True
    while changed:
        changed = False
        for suf in (".part", ".ytdl", ".temp", ".seg"):
            if n.lower().endswith(suf):
                n = n[: -len(suf)]
                changed = True
    base, ext = os.path.splitext(n)
    stem = re.sub(r"\.f\d[\w-]*$", "", base)
    if not stem or not folder or not os.path.isdir(folder):
        return out
    pat = re.compile(
        r"^" + re.escape(stem) + r"(\.f\d[\w-]*\.\w+|\.(jpg|jpeg|png|webp)|" + re.escape(ext) + r")(\.part|\.ytdl|\.temp|\.seg)*$",
        re.IGNORECASE,
    )
    try:
        for fname in os.listdir(folder):
            if pat.match(fname):
                out.add(os.path.join(folder, fname))
    except Exception as e:
        log_error("related_files", e)
    return out



def delete_task_files(*paths):
    deleted = False
    seen = set()
    for p in paths:
        for f in _related_files(p):
            if f in seen:
                continue
            seen.add(f)
            if os.path.isfile(f):
                try:
                    os.remove(f)
                    deleted = True
                except Exception as e:
                    logging.info(f"could not delete {f}: {e}")
    return deleted




# ----------------------------------------------------------------------------- Native downloader (multi-connection)
SEG_MIN_TOTAL = 2 * 1024 * 1024          # الملفات الأصغر من كده بتتحمّل باتصال واحد



_tls = threading.local()



def get_connections():
    ov = getattr(_tls, "conn_override", None)
    if ov:
        return ov
    try:
        return max(1, min(16, int(get_setting("connections", 8))))
    except Exception:
        return 8



TRANSIENT_HINTS = ("403", "forbidden", "429", "too many requests", "timed out", "timeout", "connection reset",
                   "connection closed", "closed early", "incomplete download", "remote end closed", "bad gateway",
                   "service unavailable", "gateway time", "502", "503", "504", "temporarily", "wrong range",
                   "eof occurred", "connection aborted", "urlopen error")



def is_transient_error(msg):
    low = str(msg or "").lower()
    return any(h in low for h in TRANSIENT_HINTS)
