# -*- coding: utf-8 -*-
"""
AeroGrab
مدير تنزيلات سريع + السيرفر المحلي اللي بتكلمه إضافة المتصفح.
"""
import sys
import urllib.request, urllib.parse, urllib.error
import threading
import multiprocessing
import re
from aerograb.common import log_error, show_native_message
from aerograb.config import APP_NAME, LOG_FILE, PORT
from aerograb.fmt import is_valid_url
from aerograb.limits import get_default_quality_safe
from aerograb.state import gui_lock, pending_urls, show_gui_event
from aerograb.system import register_protocol, setup_startup
from aerograb.server import check_single_instance, forward_to_running_instance, start_local_server


# ----------------------------------------------------------------------------- Entry point
def parse_protocol_arg(arg):
    """aerograb://<url مشفر>||<quality>   أو   aerograb://start   (idmpro:// القديم لسه مقبول)"""
    raw = re.sub(r"^(aerograb|idmpro):(//)?", "", arg, flags=re.IGNORECASE).rstrip("/")
    if not raw or raw.lower() == "start":
        return None, None
    parts = raw.split("||")
    url = urllib.parse.unquote(parts[0])
    quality = urllib.parse.unquote(parts[1]).strip("/ ") if len(parts) > 1 and parts[1] else None
    return (url if is_valid_url(url) else None), quality



def main():
    multiprocessing.freeze_support()
    argv = sys.argv[1:]
    is_background = "--background" in argv
    restarted = "--restarted" in argv
    passed_url = passed_quality = None
    for arg in argv:
        if arg.lower().startswith(("aerograb:", "idmpro:")):
            passed_url, passed_quality = parse_protocol_arg(arg)
            if passed_url is None:
                is_background = False       # aerograb://start = المستخدم عايز البرنامج يفتح

    if not check_single_instance(retry_seconds=10 if restarted else 0):
        if not forward_to_running_instance(passed_url, passed_quality):
            show_native_message(APP_NAME, f"Could not start or reach {APP_NAME}.\n"
                                          f"Port {PORT} may be used by another program.\nSee: {LOG_FILE}")
        sys.exit(0)

    setup_startup()
    register_protocol()
    threading.Thread(target=start_local_server, daemon=True).start()

    if is_background and not passed_url:
        show_gui_event.wait()           # نستنى أول طلب من المتصفح قبل ما نحمّل الواجهة التقيلة

    with gui_lock:
        items = list(pending_urls)
        pending_urls.clear()
    if passed_url:
        items.insert(0, {"url": passed_url, "quality": passed_quality or get_default_quality_safe(), "referer": ""})
    try:
        from aerograb.views.window import main_gui   # استيراد كسول: الواجهة متتحمّلش في وضع الخلفية
        main_gui(initial_items=items)
    except Exception as e:
        log_error("main_gui fatal", e)
        show_native_message(APP_NAME, f"Unexpected error:\n{e}\n\nSee: {LOG_FILE}")
        raise



if __name__ == "__main__":
    main()
