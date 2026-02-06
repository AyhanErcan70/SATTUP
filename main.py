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
from app.modules.main_menu import MainMenuApp

# Register Qt resources early so Designer stylesheets using ":/..." paths always work.
import ui.icons.context_rc


def main():
    db = DatabaseManager()

    app = QApplication(sys.argv)

    user_data = {}
    main_window = MainMenuApp(user_data=user_data, start_passive=True, offline_timeout_ms=120000)
    main_window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()