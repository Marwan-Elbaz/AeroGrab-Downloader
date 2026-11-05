# -*- coding: utf-8 -*-
"""إعدادات التقاط التحميلات من المتصفح (الإضافة بتقراها من البرنامج عن طريق /get_settings)."""
from aerograb.common import get_setting
from aerograb.config import APP_VERSION

# نفس القايمة الافتراضية اللي كانت ثابتة جوه الإضافة
DEFAULT_EXTENSIONS = [
    "zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso", "img",
    "exe", "msi", "apk", "dmg", "pkg", "deb", "rpm",
    "mp4", "mkv", "avi", "mov", "flv", "wmv", "webm", "m4v", "mpg", "mpeg", "3gp",
    "mp3", "wav", "flac", "m4a", "aac", "ogg", "opus", "wma",
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
]
DOC_EXTENSIONS = ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx"]
MENU_ITEMS = [("link", "Download link"), ("media", "Download this video/audio"), ("image", "Download this image"),
              ("sel", "Download links in selection"), ("page", "Download the video on this page"),
              ("all", "Download all links on this page (Link Grabber)")]
BYPASS_KEYS = ["none", "alt", "ctrl", "shift"]


def parse_extensions(text):
    """'zip, .rar  7z' -> ['zip','rar','7z'] (بدون تكرار)."""
    out, seen = [], set()
    for tok in str(text or "").replace(";", ",").replace("\n", ",").replace(" ", ",").split(","):
        tok = tok.strip().lower().lstrip(".*")
        if tok and tok.isalnum() and len(tok) <= 6 and tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


def program_language():
    """لغة البرنامج الحالية (ar / en) عشان الإضافة تتكلم بنفس اللغة."""
    from aerograb import i18n
    code = get_setting("language", "")
    return code if code in i18n.LANGUAGES else i18n.detect_system_language()


def capture_config():
    exts = get_setting("capture_exts", None)
    if not isinstance(exts, list) or not exts:
        exts = list(DEFAULT_EXTENSIONS)
    menu = get_setting("browser_menu", {}) or {}
    return {
        "version": APP_VERSION,
        "lang": program_language(),
        "enabled": bool(get_setting("capture_enabled", True)),
        "extensions": exts,
        "doc_extensions": DOC_EXTENSIONS,
        "min_doc_mb": float(get_setting("min_doc_mb", 1)),
        "min_binary_mb": float(get_setting("min_binary_mb", 5)),
        "capture_media_mime": bool(get_setting("capture_media_mime", True)),
        "require_click": bool(get_setting("capture_require_click", True)),
        "bypass_key": get_setting("bypass_key", "alt") if get_setting("bypass_key", "alt") in BYPASS_KEYS else "alt",
        "menu": {k: bool(menu.get(k, True)) for k, _ in MENU_ITEMS},
    }
