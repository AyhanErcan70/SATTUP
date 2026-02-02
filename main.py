import sys
import os
import config
# 1. Bytecode (.pycache) oluşumunu engelle
sys.dont_write_bytecode = True

# 2. Modülleri bulabilmek için 'app' klasörünü sistem yoluna ekle
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from config import BASE_DIR
from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication, QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout
from app.core.db_manager import DatabaseManager
from app.modules.main_menu import MainMenuApp

# Register Qt resources early so Designer stylesheets using ":/..." paths always work.
import ui.icons.context_rc


class PeriodSelectDialog(QDialog):
    def __init__(self, parent=None, initial_month: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Dönem Seçimi")
        self._selected = None

        self.cmb_year = QComboBox()
        self.cmb_month = QComboBox()

        for y in range(2025, 2031):
            self.cmb_year.addItem(str(y), y)

        self._months = [
            ("OCAK", 1),
            ("ŞUBAT", 2),
            ("MART", 3),
            ("NİSAN", 4),
            ("MAYIS", 5),
            ("HAZİRAN", 6),
            ("TEMMUZ", 7),
            ("AĞUSTOS", 8),
            ("EYLÜL", 9),
            ("EKİM", 10),
            ("KASIM", 11),
            ("ARALIK", 12),
        ]
        for name, m in self._months:
            self.cmb_month.addItem(name, m)

        d = QDate.currentDate()
        init_y = int(d.year())
        init_m = int(d.month())
        if initial_month:
            try:
                y_str, m_str = str(initial_month).split("-", 1)
                init_y = int(y_str)
                init_m = int(m_str)
            except Exception:
                pass

        yi = self.cmb_year.findData(init_y)
        if yi >= 0:
            self.cmb_year.setCurrentIndex(yi)
        mi = self.cmb_month.findData(init_m)
        if mi >= 0:
            self.cmb_month.setCurrentIndex(mi)

        btn_ok = QPushButton("Devam")
        btn_cancel = QPushButton("İptal")
        btn_ok.clicked.connect(self._on_ok)
        btn_cancel.clicked.connect(self.reject)

        lay = QVBoxLayout()
        lay.addWidget(QLabel("Lütfen dönem seçiniz (Ay/Yıl):"))

        row = QHBoxLayout()
        row.addWidget(QLabel("Yıl:"))
        row.addWidget(self.cmb_year)
        row.addWidget(QLabel("Ay:"))
        row.addWidget(self.cmb_month)
        lay.addLayout(row)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        lay.addLayout(btns)

        self.setLayout(lay)

    def _on_ok(self):
        y = int(self.cmb_year.currentData() or 0)
        m = int(self.cmb_month.currentData() or 0)
        if y <= 0 or m <= 0:
            QMessageBox.warning(self, "Uyarı", "Lütfen ay ve yıl seçiniz.")
            return
        self._selected = f"{y:04d}-{m:02d}"
        self.accept()

    def selected_month(self) -> str | None:
        return self._selected


def _prev_month_key(month_key: str) -> str | None:
    try:
        y_str, m_str = str(month_key).split("-", 1)
        y = int(y_str)
        m = int(m_str)
        if m <= 1:
            return f"{y - 1:04d}-12"
        return f"{y:04d}-{m - 1:02d}"
    except Exception:
        return None


def main():
    db = DatabaseManager()

    app = QApplication(sys.argv)

    user_data = {}
    main_window = MainMenuApp(user_data=user_data, start_passive=True, offline_timeout_ms=120000)
    main_window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()