# -*- coding: utf-8 -*-
import os
import hashlib
import urllib.request, urllib.parse, urllib.error
import threading
import logging, logging.handlers
import io
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from PIL import ImageOps
from aerograb.config import APP_DATA_DIR, USER_AGENT
from aerograb.fmt import is_valid_url
from aerograb.netutil import _urlopen


THUMB_DIR = os.path.join(APP_DATA_DIR, "thumbs")

_thumb_mem = {}            # url -> PIL.Image  (أو False لو فشل)

_thumb_pending = set()

_thumb_shown = {"k": None}

KIND_STYLE = {"video": ("#8e44ad", "VIDEO"), "audio": ("#e67e22", "AUDIO"), "archive": ("#e0a010", "ARCHIVE"),
              "app": ("#2980b9", "PROGRAM"), "doc": ("#c0392b", "DOCUMENT"), "file": ("#607d8b", "FILE"),
              "idle": ("#2cc985", "")}



def _font(size):
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()



def _round_corners(img, radius):
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.size[0] - 1, img.size[1] - 1), radius=radius, fill=255)
    img.putalpha(mask)
    return img



def make_type_icon(kind, ext, size=(320, 180)):
    key = (kind, ext)
    if key in _icon_pil_cache:
        return _icon_pil_cache[key]
    w, h = size
    color, label = KIND_STYLE.get(kind, KIND_STYLE["file"])
    img = Image.new("RGBA", size, color)
    d = ImageDraw.Draw(img)
    shade = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(shade).rectangle((0, int(h * 0.68), w, h), fill=(0, 0, 0, 55))
    img = Image.alpha_composite(img, shade)
    d = ImageDraw.Draw(img)
    if kind == "idle":
        cx, cy = w // 2, h // 2 - 4                       # سهم تحميل
        d.rectangle((cx - 13, cy - 46, cx + 13, cy + 8), fill="white")
        d.polygon([(cx - 40, cy + 4), (cx + 40, cy + 4), (cx, cy + 46)], fill="white")
        d.rounded_rectangle((cx - 50, cy + 56, cx + 50, cy + 64), radius=4, fill="white")
    else:
        big = ext or label[:4]
        f = _font(78 if len(big) <= 3 else 60 if len(big) == 4 else 48)
        d.text((w / 2, h * 0.40), big, font=f, fill="white", anchor="mm")
        d.text((w / 2, h * 0.83), label, font=_font(26), fill=(255, 255, 255, 215), anchor="mm")
    img = _round_corners(img, 22)
    _icon_pil_cache[key] = img
    return img



def _prune_thumbs(keep=400):
    try:
        files = [os.path.join(THUMB_DIR, f) for f in os.listdir(THUMB_DIR)]
        if len(files) > keep:
            files.sort(key=os.path.getmtime)
            for f in files[: len(files) - keep]:
                os.remove(f)
    except Exception:
        pass



def _load_thumb_async(url):
    if url in _thumb_pending or url in _thumb_mem or not is_valid_url(url):
        return
    _thumb_pending.add(url)

    def work():
        pil = None
        try:
            os.makedirs(THUMB_DIR, exist_ok=True)
            p = os.path.join(THUMB_DIR, hashlib.sha1(url.encode("utf-8")).hexdigest()[:20] + ".jpg")
            if os.path.exists(p):
                pil = Image.open(p).convert("RGB")
            else:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with _urlopen(req, timeout=8) as r:
                    raw = r.read(3_000_000)
                pil = ImageOps.fit(Image.open(io.BytesIO(raw)).convert("RGB"), (320, 180))
                pil.save(p, "JPEG", quality=85)
                _prune_thumbs()
            pil = _round_corners(ImageOps.fit(pil, (320, 180)), 22)
        except Exception as e:
            logging.info(f"thumbnail unavailable ({url}): {e}")
            pil = None
        _thumb_mem[url] = pil or False
        _thumb_pending.discard(url)

    threading.Thread(target=work, daemon=True).start()



GREEN, GREEN_H = "#2cc985", "#21a06a"


# ----------------------------------------------------------------------------
# استيرادات متبادلة مع وحدات تانية (بتتحط في الآخر عشان تتفادى مشاكل الاستيراد الدائري)
from aerograb.views.icons import _icon_pil_cache  # noqa: E402
