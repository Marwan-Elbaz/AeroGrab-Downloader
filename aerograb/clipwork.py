# -*- coding: utf-8 -*-
"""شغل تحميل جزء من فيديو بشكل قابل للاستكمال.

الفكرة: الجزء بيتقسم لشرائح مدة كل واحدة CLIP_SEG ثانية (ملفات .ts)، وكل شريحة مكتملة بتفضل محفوظة.
لما التحميل يتوقف (Pause / إغلاق البرنامج / انقطاع) بنكمّل من آخر شريحة مكتملة بدل ما نبدأ من الأول،
وفي الآخر بنضم الشرائح في ملف واحد بدون إعادة ترميز."""
import json
import logging
import os
import re
import shutil
import subprocess
import time

from aerograb.config import APP_DATA_DIR
from aerograb.tools import _NOWIN

CLIP_SEG = 10                                   # مدة الشريحة بالثواني (الكيفريمز بتتفرض على مضاعفاتها بالظبط)
CLIPS_DIR = os.path.join(APP_DATA_DIR, "clips")
_SEG_RE = re.compile(r"^seg_(\d{5})\.ts$")


def workdir(key):
    return os.path.join(CLIPS_DIR, str(key))


def _meta_path(key):
    return os.path.join(workdir(key), "meta.json")


def read_meta(key):
    try:
        with open(_meta_path(key), encoding="utf-8") as f:
            m = json.load(f)
        return m if isinstance(m, dict) else {}
    except Exception:
        return {}


def write_meta(key, meta):
    os.makedirs(workdir(key), exist_ok=True)
    tmp = _meta_path(key) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f)
    os.replace(tmp, _meta_path(key))


def clear(key):
    """بيمسح شغل الاستكمال بتاع المهمة (عند الإلغاء/الحذف/الاكتمال)."""
    if not key:
        return
    try:
        shutil.rmtree(workdir(key), ignore_errors=True)
    except Exception as e:
        logging.info(f"clipwork.clear failed: {e}")


def sweep(valid_keys, max_age_days=14):
    """بيمسح مجلدات الشغل اللي مفيش مهمة بتستخدمها (أو قديمة جداً)."""
    try:
        names = os.listdir(CLIPS_DIR)
    except Exception:
        return
    now = time.time()
    for n in names:
        p = os.path.join(CLIPS_DIR, n)
        try:
            old = now - os.path.getmtime(p) > max_age_days * 86400
        except Exception:
            old = False
        if n not in valid_keys or old:
            shutil.rmtree(p, ignore_errors=True)


def list_segments(key):
    """أرقام الشرائح الموجودة (مرتبة)."""
    try:
        idx = sorted(int(m.group(1)) for n in os.listdir(workdir(key)) for m in [_SEG_RE.match(n)] if m)
    except Exception:
        idx = []
    return idx


def seg_path(key, i):
    return os.path.join(workdir(key), f"seg_{i:05d}.ts")


def complete_count(key, finished=False):
    """عدد الشرائح المكتملة المتصلة من الأول. الأخيرة ممكن تكون ناقصة (الكتابة اتقطعت) فبنمسحها إلا لو ffmpeg خلّص."""
    idx = list_segments(key)
    n = 0
    while n < len(idx) and idx[n] == n:
        n += 1
    for extra in idx[n:]:                       # شرائح منفصلة مش متصلة: ملهاش لازمة
        try:
            os.remove(seg_path(key, extra))
        except OSError:
            pass
    if n and not finished:                      # آخر شريحة ممكن تكون ناقصة
        try:
            os.remove(seg_path(key, n - 1))
        except OSError:
            pass
        n -= 1
    return n


def concat_segments(ffmpeg, key, count, out_path, has_video):
    """بيضم الشرائح في ملف نهائي (نسخ بدون إعادة ترميز)."""
    lst = os.path.join(workdir(key), "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for i in range(count):
            f.write("file '" + seg_path(key, i).replace("\\", "/").replace("'", "'\\''") + "'\n")
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", lst,
           "-c", "copy", "-bsf:a", "aac_adtstoasc", "-movflags", "+faststart", out_path]
    r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=_NOWIN)
    if r.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        try:
            os.remove(out_path)
        except OSError:
            pass
        raise RuntimeError((r.stderr or "").strip()[-300:] or f"ffmpeg concat failed (code {r.returncode})")
