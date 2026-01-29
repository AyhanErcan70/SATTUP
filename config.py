import os
import sys
import shutil

# 1. Bytecode (.pycache) oluşumunu geliştirme aşamasında engelle
sys.dont_write_bytecode = True

# 2. Ana Dizin Tanımlama (C:\ASIL)
try:
    _FROZEN = bool(getattr(sys, "frozen", False))
except Exception:
    _FROZEN = False

try:
    _EXE_DIR = os.path.dirname(sys.executable) if _FROZEN else os.path.dirname(os.path.abspath(__file__))
except Exception:
    _EXE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    _RESOURCE_DIR = getattr(sys, "_MEIPASS", _EXE_DIR) if _FROZEN else _EXE_DIR
except Exception:
    _RESOURCE_DIR = _EXE_DIR

def _is_dir_writable(dir_path: str) -> bool:
    try:
        os.makedirs(dir_path, exist_ok=True)
    except Exception:
        return False
    try:
        test_path = os.path.join(dir_path, "__write_test.tmp")
        with open(test_path, "w", encoding="utf-8") as f:
            f.write("ok")
        try:
            os.remove(test_path)
        except Exception:
            pass
        return True
    except Exception:
        return False

def _local_appdata_dir() -> str:
    try:
        p = (os.environ.get("LOCALAPPDATA") or "").strip()
        if p:
            return p
    except Exception:
        pass

    try:
        return os.path.join(os.path.expanduser("~"), "AppData", "Local")
    except Exception:
        return _EXE_DIR

BASE_DIR = _RESOURCE_DIR

# 3. Alt Dizin Yolları
APP_DIR = os.path.join(BASE_DIR, "app")
UI_DIR = os.path.join(BASE_DIR, "ui")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

# DB her zaman yazılabilir bir yerde olsun
if _FROZEN:
    _portable_db_dir = os.path.join(_EXE_DIR, "database")
    _appdata_db_dir = os.path.join(_local_appdata_dir(), "SATTUP", "database")
    DATABASE_DIR = _portable_db_dir if _is_dir_writable(_portable_db_dir) else _appdata_db_dir
else:
    DATABASE_DIR = os.path.join(BASE_DIR, "database")

# 4. Kritik Dosya Yolları
_ENV_DB_PATH = (os.environ.get("SATTUP_DB_PATH") or "").strip()
DB_PATH = _ENV_DB_PATH if _ENV_DB_PATH else os.path.join(DATABASE_DIR, "asil_system.db")

if not _ENV_DB_PATH:
    try:
        os.makedirs(DATABASE_DIR, exist_ok=True)
    except Exception:
        pass

    if _FROZEN:
        try:
            if not os.path.exists(DB_PATH):
                bundled_db = os.path.join(_RESOURCE_DIR, "database", "asil_system.db")
                if os.path.exists(bundled_db):
                    shutil.copy2(bundled_db, DB_PATH)
        except Exception:
            pass

UI_FILES_PATH = os.path.join(UI_DIR, "ui_files")
ICONS_PATH = os.path.join(UI_DIR, "icons")

# 5. UI Dosyaları İçin Yardımcı Fonksiyon
def get_ui_path(file_name):
    """Verilen .ui dosyasının tam yolunu döndürür"""
    return os.path.join(UI_FILES_PATH, file_name)