import os
import sys

# 1. Bytecode (.pycache) oluşumunu geliştirme aşamasında engelle
sys.dont_write_bytecode = True

# 2. Ana Dizin Tanımlama (C:\ASIL)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 3. Alt Dizin Yolları
APP_DIR = os.path.join(BASE_DIR, "app")
UI_DIR = os.path.join(BASE_DIR, "ui")
DATABASE_DIR = os.path.join(BASE_DIR, "database")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

# 4. Kritik Dosya Yolları
_ENV_DB_PATH = (os.environ.get("SATTUP_DB_PATH") or "").strip()
DB_PATH = _ENV_DB_PATH if _ENV_DB_PATH else os.path.join(DATABASE_DIR, "asil_system.db")

if not _ENV_DB_PATH:
    try:
        os.makedirs(DATABASE_DIR, exist_ok=True)
    except Exception:
        pass
UI_FILES_PATH = os.path.join(UI_DIR, "ui_files")
ICONS_PATH = os.path.join(UI_DIR, "icons")

# 5. UI Dosyaları İçin Yardımcı Fonksiyon
def get_ui_path(file_name):
    """Verilen .ui dosyasının tam yolunu döndürür"""
    return os.path.join(UI_FILES_PATH, file_name)