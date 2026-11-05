# -*- coding: utf-8 -*-
"""التحقق من سلامة الملف بالـ checksum (MD5 / SHA-1 / SHA-256 / SHA-512)."""
import hashlib
import re

ALGOS = {"SHA-256": "sha256", "SHA-1": "sha1", "MD5": "md5", "SHA-512": "sha512"}
_LEN_TO_ALGO = {32: "md5", 40: "sha1", 64: "sha256", 128: "sha512"}
_HEX = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32,128}(?![0-9a-fA-F])")


def extract_hash(text):
    """بيطلّع الـ hash من نص منسوخ بأي شكل: 'abc...', 'SHA256: abc...', 'abc...  file.iso', 'abc... *file.iso'.
    بيرجّع (hash بحروف صغيرة, اسم الخوارزمية) أو ('', '') لو مفيش hash صالح."""
    for m in _HEX.finditer(text or ""):
        h = m.group(0).lower()
        if len(h) in _LEN_TO_ALGO:
            return h, _LEN_TO_ALGO[len(h)]
    return "", ""


def compute(path, algo, on_progress=None, should_stop=None, chunk=1 << 20):
    """بيحسب الـ hash للملف على دفعات. on_progress(done_bytes, total_bytes). بيرجّع hex أو None لو اتلغى."""
    import os
    h = hashlib.new(algo)
    total = os.path.getsize(path)
    done = 0
    with open(path, "rb") as f:
        while True:
            if should_stop and should_stop():
                return None
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
            done += len(b)
            if on_progress:
                on_progress(done, total)
    return h.hexdigest()
