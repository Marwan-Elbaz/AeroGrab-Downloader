# -*- coding: utf-8 -*-
import base64
import re
import io
from PIL import Image
from PIL import ImageDraw
import customtkinter as ctk
from aerograb.common import log_error
from aerograb.config import IS_WINDOWS, UI_FONT
from aerograb.icons_data import _ICON_B64
from aerograb.icons_extra import EXTRA_ICONS

_ICON_B64.update(EXTRA_ICONS)


_ICON_NAVY = {"bolt", "caret_down", "caret_up", "info", "file", "drive", "link", "plug",
              "alarm", "floppy", "gears", "globe", "puzzle", "toolbox", "update", "video",
              "comment", "cookie", "copyright", "export", "github", "language", "search", "share", "youtube",
              "bell", "gauge", "palette"}     # غامقة: بتتفتّح في الثيم الغامق

_ICON_GRAY = {"settings_gear"}     # رمادي فاتح: بيتغمّق في الثيم الفاتح عشان يبان

_ICON_LIGHT = (205, 214, 226)

_ICON_FILL_HOLES = set()     # الرموز جوه الدواير (تشغيل/إيقاف/إلغاء...) بتفضل شفافة عشان تمشي مع الثيم الفاتح والغامق

_icon_pil_src = {}

_icon_pil_cache = {}



def _draw_icon(name):
    """أيقونات صغيرة مرسومة بالكود (مفيش لها نسخة جاهزة): folder / check."""
    S = 96
    big = Image.new("RGBA", (S * 3, S * 3), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    if name == "folder":
        d.rounded_rectangle((20 * 3, 30 * 3, 86 * 3, 78 * 3), radius=9 * 3, fill=(242, 184, 75, 255))
        d.rounded_rectangle((10 * 3, 18 * 3, 44 * 3, 42 * 3), radius=7 * 3, fill=(224, 160, 48, 255))
        d.rounded_rectangle((10 * 3, 32 * 3, 86 * 3, 78 * 3), radius=9 * 3, fill=(247, 200, 90, 255))
    elif name == "check":
        # دايرة خضرا العلامة (✓) جواها مفرّغة (شفافة) زي باقي الأيقونات (تشغيل/إيقاف/إلغاء...) فتمشي مع الثيمين
        alpha = Image.new("L", big.size, 0)
        ad = ImageDraw.Draw(alpha)
        ad.ellipse((6 * 3, 6 * 3, 90 * 3, 90 * 3), fill=255)
        ad.line([(26 * 3, 50 * 3), (41 * 3, 65 * 3), (70 * 3, 32 * 3)], fill=0, width=10 * 3, joint="curve")
        for cx, cy in ((26, 50), (70, 32)):
            ad.ellipse(((cx - 5) * 3, (cy - 5) * 3, (cx + 5) * 3, (cy + 5) * 3), fill=0)
        big = Image.new("RGBA", big.size, (44, 201, 133, 255))
        big.putalpha(alpha)
    return big.resize((S, S), Image.LANCZOS)



def _fill_holes_white(img):
    from PIL import ImageFilter
    w, h = img.size
    mask = img.getchannel("A").point(lambda v: 255 if v > 20 else 0)
    padded = Image.new("L", (w + 4, h + 4), 0)          # إطار فاضي عشان الخارج كله يبقى متصل (الدايرة بتلمس الحواف)
    padded.paste(mask, (2, 2))
    ImageDraw.floodfill(padded, (0, 0), 128)
    outside = padded.crop((2, 2, w + 2, h + 2))
    holes = outside.point(lambda v: 255 if v == 0 else 0).filter(ImageFilter.MaxFilter(3))
    base = Image.new("RGBA", img.size, (0, 0, 0, 0))
    base.paste(Image.new("RGBA", img.size, (255, 255, 255, 255)), mask=holes)
    return Image.alpha_composite(base, img)



def icon_pil(name, px, dark=None, dim=False):
    """أيقونة PIL بالمقاس المطلوب. dark=None = الثيم الحالي. dim = أهدى (للأزرار غير المفعّلة)."""
    if dark is None:
        dark = ctk.get_appearance_mode() == "Dark"
    key = (name, px, bool(dark), dim)
    im = _icon_pil_cache.get(key)
    if im is not None:
        return im
    src = _icon_pil_src.get(name)
    if src is None:
        if name in _ICON_B64:
            src = Image.open(io.BytesIO(base64.b64decode("".join(_ICON_B64[name])))).convert("RGBA")
        else:
            src = _draw_icon(name)
        if name in _ICON_FILL_HOLES:
            src = _fill_holes_white(src)
        _icon_pil_src[name] = src
    im = src.resize((px, px), Image.LANCZOS)
    if dark and name in _ICON_NAVY:
        a = im.getchannel("A")
        im = Image.new("RGBA", im.size, _ICON_LIGHT + (255,))
        im.putalpha(a)
    if not dark and name in _ICON_GRAY:
        a = im.getchannel("A")
        im = Image.new("RGBA", im.size, (84, 94, 108, 255))
        im.putalpha(a)
    if dim:
        a = im.getchannel("A").point(lambda v: int(v * 0.45))
        im.putalpha(a)
    if len(_icon_pil_cache) > 400:
        _icon_pil_cache.clear()
    _icon_pil_cache[key] = im
    return im



_ctk_icon_cache = {}



def icon_ctk(name, px=18):
    """CTkImage (بيتبدّل لوحده مع الثيم) لاستخدامه في الأزرار والـ Labels."""
    key = (name, px)
    im = _ctk_icon_cache.get(key)
    if im is None:
        try:
            im = ctk.CTkImage(light_image=icon_pil(name, px * 3, dark=False), dark_image=icon_pil(name, px * 3, dark=True), size=(px, px))
        except Exception as e:
            log_error("icon_ctk", e)
            im = None
        _ctk_icon_cache[key] = im
    return im




# ----------------------------------------------------------------------------- Card view (Canvas واحد + رسم للكروت الظاهرة بس = خفيف)
CARD_MIN_W, CARD_H, CARD_GAP = 340, 164, 12

EMOJI_FONT = "Segoe UI Emoji" if IS_WINDOWS else UI_FONT

STAT_META = {"act": ("download", "Active"), "queue": ("hourglass", "Queued"), "done": ("tick", "Completed"), "fail": ("warn", "Failed")}

STATE_OF = {"completed": "done", "downloading": "act", "starting": "act", "merging": "merge", "queued": "queue",
            "paused": "pause", "error": "err", "canceled": "err", "deleted": "err"}

CHIP_TEXT = {"completed": "Completed", "downloading": "Downloading", "starting": "Connecting", "merging": "Merging",
             "queued": "Queued", "paused": "Paused", "error": "Failed", "canceled": "Canceled", "deleted": "File deleted"}

CHIP_ICON = {"completed": "check", "downloading": "download", "starting": "plug", "merging": "bolt", "queued": "hourglass",
             "paused": "pause", "error": "warn", "canceled": "remove", "deleted": "remove"}

CARD_PAL = {
    "Dark": {
        "canvas": "#101114", "title": "#f1f3f5", "muted": "#98a2ad", "trough": "#2a2f37",
        "btn": "#1b212a", "btn_h": "#2b3644", "bar_bg": "#16181c", "bar_trough": "#262a31", "bar_text": "#ffffff",
        "states": {
            "done": dict(fill="#0f1c16", border="#1f6f4d", acc="#2cc985", chip="#143527", chip_t="#58e0a2"),
            "act": dict(fill="#0e1822", border="#1c5a82", acc="#35b6ff", chip="#10304a", chip_t="#62c6ff"),
            "merge": dict(fill="#1d1710", border="#8a5a14", acc="#ff9800", chip="#3a2a10", chip_t="#ffb74d"),
            "pause": dict(fill="#0f1621", border="#25507a", acc="#3b8fe8", chip="#112a46", chip_t="#6ab0ff"),
            "queue": dict(fill="#15181d", border="#2e343d", acc="#7b8794", chip="#222830", chip_t="#aab4bf"),
            "err": dict(fill="#1e1115", border="#7a2d35", acc="#e5484d", chip="#3a181d", chip_t="#ff7b80"),
        }},
    "Light": {
        "canvas": "#eef0f3", "title": "#1a1d21", "muted": "#6b7480", "trough": "#d8dde3",
        "btn": "#e4e8ed", "btn_h": "#d3d9e0", "bar_bg": "#ffffff", "bar_trough": "#dde1e6", "bar_text": "#10231a",
        "states": {
            "done": dict(fill="#eaf7f0", border="#8dd2b0", acc="#1fa56f", chip="#cdeede", chip_t="#117a4d"),
            "act": dict(fill="#eaf4fb", border="#8cc3e6", acc="#1e90d6", chip="#cfe6f6", chip_t="#17679c"),
            "merge": dict(fill="#fdf3e3", border="#e8bf7c", acc="#e68600", chip="#fbe3bd", chip_t="#a35f00"),
            "pause": dict(fill="#eaf0fa", border="#97b6e3", acc="#2f77d1", chip="#d2e0f6", chip_t="#235ca8"),
            "queue": dict(fill="#f4f5f7", border="#ccd1d8", acc="#7b8794", chip="#e3e6ea", chip_t="#59636e"),
            "err": dict(fill="#fbeced", border="#e5a1a6", acc="#d6393f", chip="#f6d3d5", chip_t="#a52329"),
        }},
}



def _pal():
    return CARD_PAL["Dark" if ctk.get_appearance_mode() == "Dark" else "Light"]



def _mix(c1, c2, a):
    """بيمزج لونين hex (a = نسبة اللون التاني)."""
    try:
        p1 = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
        p2 = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
        return "#%02x%02x%02x" % tuple(int(x * (1 - a) + y * a) for x, y in zip(p1, p2))
    except Exception:
        return c1



def _aa_round(w, h, r, fill, border=None, bw=0, scale=3):
    """مستطيل بحواف دايرية ناعمة (anti-aliased) كصورة شفافة."""
    w, h = max(2, int(w)), max(2, int(h))
    big = Image.new("RGBA", (w * scale, h * scale), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    if border and bw:
        d.rounded_rectangle((0, 0, w * scale - 1, h * scale - 1), radius=r * scale, fill=border)
        d.rounded_rectangle((bw * scale, bw * scale, w * scale - 1 - bw * scale, h * scale - 1 - bw * scale),
                            radius=max(1, r - bw) * scale, fill=fill)
    else:
        d.rounded_rectangle((0, 0, w * scale - 1, h * scale - 1), radius=r * scale, fill=fill)
    return big.resize((w, h), Image.LANCZOS)



def _aa_corners(img, radius, scale=3):
    img = img.convert("RGBA")
    w, h = img.size
    mask = Image.new("L", (w * scale, h * scale), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w * scale - 1, h * scale - 1), radius=radius * scale, fill=255)
    img.putalpha(mask.resize((w, h), Image.LANCZOS))
    return img



def _ellipsize(font, text, maxw):
    text = str(text or "").replace("\n", " ")
    if maxw <= 10 or font.measure(text) <= maxw:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.measure(text[:mid] + "…") <= maxw:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + "…"



def _parse_size(text):
    m = re.match(r"\s*([\d.]+)\s*(B|KB|MB|GB)\b", str(text or ""))
    if not m:
        return 0.0
    return float(m.group(1)) * {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3}[m.group(2)]



_prio = {"iid": None, "held": {}, "pending": {}}      # held/pending: تحميلات اتوقفت مؤقتاً وهترجع (قيمتها = عدد المحاولات)
