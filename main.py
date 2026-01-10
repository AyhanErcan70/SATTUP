import sys
import os
import config
# 1. Bytecode (.pycache) oluşumunu engelle
sys.dont_write_bytecode = True

# 2. Modülleri bulabilmek için 'app' klasörünü sistem yoluna ekle
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from config import BASE_DIR
from PyQt6.QtWidgets import QApplication
from app.core.db_manager import DatabaseManager
from app.modules.auth import AuthApp
from app.modules.main_menu import MainMenuApp

def main():
    db = DatabaseManager()

    app = QApplication(sys.argv)
    style_path = os.path.join(BASE_DIR, "ui", "styles", "main_style.qss")
    if os.path.exists(style_path):
        with open(style_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    login_window = AuthApp()
    
    # exec() sonucu QDialog.DialogCode.Accepted (1) ise devam et
    if login_window.exec():
        print("Giriş Başarılı! Ana menü yükleniyor...")
        main_window = MainMenuApp(user_data=getattr(login_window, "user_data", None)) 
        main_window.showMaximized()
        sys.exit(app.exec())
    
    # Programdan tamamen çıkış yap ve terminali serbest bırak
    app.quit() 

if __name__ == "__main__":
    main()