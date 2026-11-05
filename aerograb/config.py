# -*- coding: utf-8 -*-
import os
import sys


APP_NAME = "AeroGrab"

APP_VERSION = "4.1"

# نسخة ملفات إضافة المتصفح المتوافقة مع البرنامج (extension/manifest.json). الإضافة بتتثبّت يدوي فمش بتتحدّث مع البرنامج،
# فبنقارن بالرقم ده مش بـ APP_VERSION عشان تحديث البرنامج ميطلعش تحذير غلط. غيّره بس لو عدّلت الإضافة نفسها.
EXTENSION_VERSION = "4.1"

PORT = 9999


# لو البرنامج متبنّي بدون كونسول (--noconsole) بيبقى stdout/stderr = None وبعض المكتبات بتنهار
for _n in ("stdout", "stderr"):
    if getattr(sys, _n, None) is None:
        setattr(sys, _n, open(os.devnull, "w"))


IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
    import winreg
else:
    winreg = None


HOME = os.path.expanduser("~")

APP_DATA_DIR = os.path.join(HOME, ".aerograb")
_LEGACY_DATA_DIR = os.path.join(HOME, ".idm_modern_pro")        # مجلد النسخ القديمة (IDM Modern Pro)
if not os.path.exists(APP_DATA_DIR) and os.path.isdir(_LEGACY_DATA_DIR):
    try:
        os.rename(_LEGACY_DATA_DIR, APP_DATA_DIR)               # بننقل الإعدادات والسجل القديم للاسم الجديد
    except OSError:
        APP_DATA_DIR = _LEGACY_DATA_DIR                         # لو النسخة القديمة شغالة: نكمّل على مجلدها دلوقتي

try:
    os.makedirs(APP_DATA_DIR, exist_ok=True)
except Exception:
    pass

YTDLP_CACHE_DIR = os.path.join(APP_DATA_DIR, "ytdlp_latest")

YTDLP_VERSION_FILE = os.path.join(APP_DATA_DIR, "ytdlp_version.txt")

IPC_TOKEN_FILE = os.path.join(APP_DATA_DIR, "ipc_token")

LOG_FILE = os.path.join(HOME, "idm_pro_log.txt")

SETTINGS_FILE = os.path.join(HOME, "idm_pro_settings.json")

HISTORY_FILE = os.path.join(HOME, "idm_pro_history.json")


FROZEN = bool(getattr(sys, "frozen", False))

# الحزمة جوه مجلد idm/ فالمجلد الرئيسي للبرنامج هو اللي فوقه
BASE_DIR = os.path.dirname(os.path.abspath(sys.executable)) if FROZEN else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RESOURCE_DIRS = [BASE_DIR] + ([sys._MEIPASS] if getattr(sys, "_MEIPASS", None) else [])

COOKIES_PATH = os.path.join(BASE_DIR, "cookies.txt")

# ربط node/deno/ffmpeg اللي جنب البرنامج
os.environ["PATH"] = os.pathsep.join(RESOURCE_DIRS) + os.pathsep + os.environ.get("PATH", "")


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

UI_FONT = "Segoe UI" if IS_WINDOWS else "Arial"

# السكريبت الرئيسي (بيتستخدم في التشغيل مع الويندوز وتسجيل بروتوكول idmpro://)
MAIN_SCRIPT = os.path.join(BASE_DIR, "main.py")

