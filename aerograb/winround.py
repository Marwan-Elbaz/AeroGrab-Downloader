# -*- coding: utf-8 -*-
"""
حواف منحنية للنوافذ بدون إطار (قايمة الكليك يمين) على ويندوز.

الطريقة القديمة (لون شفاف -transparentcolor) كانت بتفشل عند ناس كتير فتطلع الحواف مربعة، فبنستخدم حاجة أضمن:
  - ويندوز 11: حواف منحنية من النظام نفسه (ناعمة + ظل + لون الإطار) عن طريق DwmSetWindowAttribute.
  - ويندوز 10: قصّ النافذة بمنطقة منحنية (SetWindowRgn).
بره ويندوز بترجع None والنافذة بتفضل مربعة.
"""
import sys


def _hwnd(win):
    import ctypes
    wid = win.winfo_id()
    return ctypes.windll.user32.GetParent(wid) or wid


def round_window(win, width, height, radius, border_hex=None):
    """width/height/radius بالبكسل الفعلي. بترجع "dwm" أو "region" أو None."""
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes
        hwnd = _hwnd(win)
        dwm = ctypes.windll.dwmapi
        pref = ctypes.c_int(2)                                    # DWMWCP_ROUND
        if dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), 4) == 0:          # DWMWA_WINDOW_CORNER_PREFERENCE (ويندوز 11)
            if border_hex:
                r, g, b = (int(border_hex[i:i + 2], 16) for i in (1, 3, 5))
                col = ctypes.c_uint(r | (g << 8) | (b << 16))                         # COLORREF = 0x00BBGGRR
                dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(col), 4)             # DWMWA_BORDER_COLOR
            return "dwm"
    except Exception:
        pass
    try:
        import ctypes
        hwnd = _hwnd(win)
        rgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, int(width) + 1, int(height) + 1, int(radius) * 2, int(radius) * 2)
        if ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True):
            return "region"
    except Exception:
        pass
    return None
