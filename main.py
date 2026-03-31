import sys
import os
import hashlib
import subprocess
import config

# 1. Bytecode (.pycache) oluşumunu engelle
sys.dont_write_bytecode = True
# 2. Modülleri bulabilmek için 'app' klasörünü sistem yoluna ekle
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

os.environ.setdefault(
    "QT_LOGGING_RULES",
    "qt.multimedia.ffmpeg=false;qt.multimedia.*=false;qt.qpa.*=false",
)

from config import BASE_DIR
from PyQt6.QtWidgets import QApplication, QDialog
from PyQt6.QtCore import qInstallMessageHandler
from app.core.db_manager import DatabaseManager
from app.modules.main_menu import MainMenuApp

# Lisans ekranını içe aktar (Dosya adın farklıysa 'licence_ui' kısmını değiştir)
from app.modules.licence_manager import SattupLicence 

# Register Qt resources early
import ui.icons.context_rc

def _qt_message_handler(msg_type, context, message):
    try:
        msg = str(message or "")
    except Exception:
        msg = ""
    if "QFont::setPointSize: Point size <= 0" in msg:
        return
    if "QGradient::setColorAt: Color position must be specified" in msg:
        return
    if "QObject::disconnect: wildcard call disconnects from destroyed signal" in msg:
        return
    if "QFFmpeg::" in msg and "QObject::disconnect" in msg:
        return
    if msg.startswith("qt.multimedia.ffmpeg") or msg.startswith("Using Qt multimedia"):
        return
    if msg.startswith("Input #") or msg.startswith("Stream #"):
        return
    try:
        sys.stderr.write(msg + "\n")
    except Exception:
        pass

qInstallMessageHandler(_qt_message_handler)

# --- LİSANS YARDIMCI FONKSİYONLARI ---

def get_hwid():
    """Bilgisayarın benzersiz donanım kimliğini (UUID) döndürür."""
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "(Get-CimInstance Win32_ComputerSystemProduct).UUID",
        ]
        uuid = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        uuid = (uuid or "").strip()
        if uuid:
            return hashlib.sha256(uuid.encode()).hexdigest()[:16]
    except Exception:
        pass

    try:
        cmd2 = "wmic csproduct get uuid"
        uuid2 = subprocess.check_output(cmd2, shell=True, text=True, stderr=subprocess.DEVNULL)
        uuid2 = (uuid2 or "").strip()
        if uuid2:
            return hashlib.sha256(uuid2.encode()).hexdigest()[:16]
    except Exception:
        pass

    return "default_hwid_12345"

def get_license_path():
    """Lisans dosyasının AppData altındaki gizli yolunu oluşturur."""
    app_data = os.getenv('APPDATA') # C:\Users\Kullanıcı\AppData\Roaming
    target_dir = os.path.join(app_data, "SATTUP")
    
    # Eğer klasör yoksa (ilk çalıştırmada) otomatik oluşturur
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
        
    return os.path.join(target_dir, ".sys_config.bin")

# Kullanırken:
def is_licensed():
    lic_path = get_license_path()
    if not os.path.exists(lic_path):
        return False

    try:
        with open(lic_path, "r") as f:
            saved_key = f.read().strip()
        return saved_key == get_hwid()
    except:
        return False

# --- ANA PROGRAM ---

def main():
    db = DatabaseManager()
    app = QApplication(sys.argv)

    # --- LİSANS BEKÇİSİ ---
    if not is_licensed():
        lic_dialog = SattupLicence()
        # Eğer kullanıcı doğru şifreyi girip 'AKTİVE ET' (accept) dediyse:
        if lic_dialog.exec() == QDialog.DialogCode.Accepted:
            # HWID'yi dosyaya yaz ve kalıcı lisans oluştur
            lic_path = get_license_path()
            with open(lic_path, "w") as f:
                f.write(get_hwid())
        else:
            # Lisans ekranı kapatıldı veya iptal edildi, programdan çık
            return 

    # --- ANA PENCERE BAŞLATMA ---
    user_data = {}
    main_window = MainMenuApp(user_data=user_data, start_passive=True, offline_timeout_ms=120000)
    main_window.showMaximized()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()