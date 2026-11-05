# -*- coding: utf-8 -*-
"""
مكان الأجزاء غير المكتملة من تحميل الفيديو (ملفات .part و .fNNN وملفات الدمج المؤقتة).

كانت بتتكتب جنب الملف النهائي في مجلد التحميل، فالمستخدم ممكن يمسحها بالغلط وهو بينضّف المجلد.
دلوقتي yt-dlp بيشتغل في مجلد مؤقت تابع للبرنامج (~/.aerograb/parts/<مفتاح المهمة>) وبينقل الملف النهائي
لمجلد التحميل أول ما يخلص. مجلد التحميل مفيهوش غير الملفات الكاملة.
"""
import logging
import os
import re
import shutil
from aerograb.config import APP_DATA_DIR

PARTS_DIR = os.path.join(APP_DATA_DIR, "parts")

_LEFTOVER = re.compile(r"(\.(part|ytdl|temp|seg)(\.|$)|\.f\d[\w-]*\.\w+$)", re.IGNORECASE)


def workdir(key):
    """مجلد المهمة (ما بيتعملش إلا لما yt-dlp يحتاجه). المفتاح ثابت للمهمة حتى بعد إعادة تشغيل البرنامج."""
    return os.path.join(PARTS_DIR, str(key))


def clear(key):
    """بيمسح أجزاء المهمة (إلغاء / حذف / اكتمال)."""
    if not key:
        return
    try:
        shutil.rmtree(workdir(key), ignore_errors=True)
    except Exception as e:
        logging.info(f"partsdir.clear failed: {e}")


def sweep(valid_keys):
    """بيمسح مجلدات الأجزاء اللي مفيش مهمة بتستخدمها (مثلاً بعد حذف المهمة من السجل)."""
    try:
        names = os.listdir(PARTS_DIR)
    except Exception:
        return
    for n in names:
        if n not in valid_keys:
            shutil.rmtree(os.path.join(PARTS_DIR, n), ignore_errors=True)


def total_bytes():
    total = 0
    for root_d, _dirs, files in os.walk(PARTS_DIR):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root_d, f))
            except OSError:
                pass
    return total


def has_legacy_parts(final_path):
    """تحميل اتبدأ بنسخة قديمة: أجزاؤه لسه جنب الملف النهائي. بنكمّله هناك عشان ميبدأش من الصفر."""
    if not final_path:
        return False
    folder, name = os.path.split(final_path)
    stem = os.path.splitext(re.sub(r"(\.part|\.ytdl|\.temp|\.seg)+$", "", name, flags=re.I))[0]
    stem = re.sub(r"\.f\d[\w-]*$", "", stem).lower()
    try:
        for fname in os.listdir(folder):
            rest = fname[len(stem):]
            if fname.lower().startswith(stem) and rest.startswith(".") and _LEFTOVER.search(rest):
                return True
    except Exception:
        pass
    return False
