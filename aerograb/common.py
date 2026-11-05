# -*- coding: utf-8 -*-
import os
import json
import threading
import logging, logging.handlers
import traceback
import secrets
from aerograb.config import BASE_DIR, IPC_TOKEN_FILE, IS_WINDOWS, LOG_FILE, RESOURCE_DIRS, SETTINGS_FILE


def resource_path(name):
    for d in RESOURCE_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return os.path.join(BASE_DIR, name)



# ----------------------------------------------------------------------------- Logging
_handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8")

_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))

logging.getLogger().addHandler(_handler)

logging.getLogger().setLevel(logging.INFO)



def log_error(context, exc):
    logging.error(f"{context}: {exc}\n{traceback.format_exc()}")



class YtLogger:
    """logger لـ yt-dlp بدل الطباعة على stderr."""
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): logging.info(f"yt-dlp warning: {msg}")
    def error(self, msg): logging.info(f"yt-dlp error: {msg}")



def show_native_message(title, text):
    """رسالة تظهر حتى قبل ما Tkinter يتحمّل."""
    try:
        if IS_WINDOWS:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)
            return
    except Exception:
        pass
    print(f"{title}: {text}")



# ----------------------------------------------------------------------------- Settings / IO
_io_lock = threading.Lock()

_settings_lock = threading.Lock()



def _atomic_write_json(path, data):
    with _io_lock:
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
        except Exception as e:
            log_error("atomic_write_json", e)



def _load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log_error(f"load {path}", e)
    return default



_settings = _load_json(SETTINGS_FILE, {})

if not isinstance(_settings, dict):
    _settings = {}



def get_setting(key, default=None):
    with _settings_lock:
        return _settings.get(key, default)



def save_settings(key, value):
    with _settings_lock:
        _settings[key] = value
        snapshot = dict(_settings)
    _atomic_write_json(SETTINGS_FILE, snapshot)



def get_ipc_token():
    """سر محلي بيستخدمه النسخة التانية من البرنامج عشان تكلم النسخة الشغالة."""
    try:
        with open(IPC_TOKEN_FILE, "r", encoding="utf-8") as f:
            tok = f.read().strip()
            if tok:
                return tok
    except Exception:
        pass
    tok = secrets.token_hex(16)
    try:
        with open(IPC_TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(tok)
    except Exception as e:
        log_error("ipc_token", e)
    return tok
