from PyQt6 import uic
from PyQt6.QtCore import Qt, QDate, QRegularExpression
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QWidget,
    QMessageBox,
    QTableWidgetItem,
    QHeaderView,
    QDialog,
    QVBoxLayout,
    QCheckBox,
    QPushButton,
    QScrollArea,
)

from app.core.db_manager import DatabaseManager
from config import get_ui_path


class RepairsApp(QWidget):
    def __init__(self, user_data=None, db_manager=None, parent=None):
        super().__init__(parent)
        uic.loadUi(get_ui_path("repairs_window.ui"), self)
        self.setObjectName("main_form")

        self.user_data = user_data or {}
        self.db = db_manager if db_manager else DatabaseManager()
        self.secili_bakim_id = None
        self._islem_checkboxes = []

        self._setup_ui()
        self._setup_connections()
        self._load_combos()
        self._load_table()
        self.table_bakim.verticalHeader().setDefaultSectionSize(20)
        self.table_bakim.verticalHeader().setVisible(False)

    def _setup_ui(self):
        if hasattr(self, "table_bakim"):
            self.table_bakim.setColumnCount(7)
            self.table_bakim.setHorizontalHeaderLabels(
                ["ID", "Plaka", "Tarih", "KM", "Maliyet", "Firma", "Durum"]
            )
            self.table_bakim.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        if hasattr(self, "txt_islemler"):
            self.txt_islemler.setReadOnly(True)
            self.txt_islemler.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        if hasattr(self, "txt_maliyet"):
            # 1000,00 formatı. Binlik ayırıcı yok, kuruş için virgül.
            rx = QRegularExpression(r"^\d+(,\d{0,2})?$")
            self.txt_maliyet.setValidator(QRegularExpressionValidator(rx, self))

        if hasattr(self, "date_bakim"):
            self.date_bakim.setDate(QDate.currentDate())

        if hasattr(self, "date_sonraki_bakim"):
            self.date_sonraki_bakim.setDate(QDate.currentDate())

    def _setup_connections(self):
        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.clicked.connect(self._save_data)
        if hasattr(self, "btn_muhasebe"):
            self.btn_muhasebe.clicked.connect(self._save_data)
        if hasattr(self, "btn_yeni"):
            self.btn_yeni.clicked.connect(self._clear_form)
        if hasattr(self, "btn_sil"):
            self.btn_sil.clicked.connect(self._delete_data)
        if hasattr(self, "btn_islemler"):
            self.btn_islemler.clicked.connect(self._open_islemler_popup)
        if hasattr(self, "table_bakim"):
            self.table_bakim.itemDoubleClicked.connect(self._on_row_selected)
        if hasattr(self, "txt_maliyet"):
            self.txt_maliyet.editingFinished.connect(self._format_maliyet)

    def _get_constants_values(self, group_name, parent_id=None):
        try:
            return self.db.get_constants(group_name, parent_id=parent_id)
        except Exception:
            return []

    def _load_combos(self):
        # Araç listesi
        if hasattr(self, "cmb_arac"):
            self.cmb_arac.blockSignals(True)
            self.cmb_arac.clear()
            self.cmb_arac.addItem("Seçiniz...", None)
            for vehicle_code, plate in self.db.get_araclar_list(only_active=True):
                self.cmb_arac.addItem(str(plate), vehicle_code)
            self.cmb_arac.blockSignals(False)

        # Bakım türleri (Sabitler: group_name = bakim_turu)
        if hasattr(self, "cmb_bakim_turu"):
            self.cmb_bakim_turu.blockSignals(True)
            self.cmb_bakim_turu.clear()
            self.cmb_bakim_turu.addItem("Seçiniz...", None)
            data = self._get_constants_values("bakim_turu")
            for _id, value in data:
                self.cmb_bakim_turu.addItem(value, _id)
            self.cmb_bakim_turu.blockSignals(False)

        # Firma adları (Sabitler: group_name = bakim_firma)
        if hasattr(self, "cmb_firma_adi"):
            self.cmb_firma_adi.blockSignals(True)
            self.cmb_firma_adi.clear()
            self.cmb_firma_adi.addItem("Seçiniz...", None)
            data = self._get_constants_values("bakim_firma")
            for _id, value in data:
                self.cmb_firma_adi.addItem(value, _id)
            self.cmb_firma_adi.blockSignals(False)

    def _load_table(self):
        if not hasattr(self, "table_bakim"):
            return
        self.table_bakim.setRowCount(0)
        rows = self.db.get_bakim_listesi()
        for r, row_data in enumerate(rows):
            self.table_bakim.insertRow(r)
            for c, value in enumerate(row_data):
                item = QTableWidgetItem(str(value))
                if c == 6 and str(value) == "Beklemede":
                    item.setForeground(Qt.GlobalColor.red)
                self.table_bakim.setItem(r, c, item)

    def _format_maliyet(self):
        if not hasattr(self, "txt_maliyet"):
            return
        raw = (self.txt_maliyet.text() or "").strip()
        if not raw:
            return
        normalized = raw.replace(".", "").replace(",", ".")
        try:
            val = float(normalized)
        except Exception:
            return
        self.txt_maliyet.setText(f"{val:.2f}".replace(".", ","))

    def _clear_form(self):
        self.secili_bakim_id = None
        if hasattr(self, "cmb_arac"):
            self.cmb_arac.setCurrentIndex(0)
        if hasattr(self, "cmb_bakim_turu"):
            self.cmb_bakim_turu.setCurrentIndex(0)
        if hasattr(self, "cmb_firma_adi"):
            self.cmb_firma_adi.setCurrentIndex(0)
        if hasattr(self, "txt_bakim_km"):
            self.txt_bakim_km.clear()
        if hasattr(self, "txt_islemler"):
            self.txt_islemler.clear()
        if hasattr(self, "txt_maliyet"):
            self.txt_maliyet.clear()
        if hasattr(self, "txt_fis_no"):
            self.txt_fis_no.clear()
        if hasattr(self, "date_bakim"):
            self.date_bakim.setDate(QDate.currentDate())
        if hasattr(self, "date_sonraki_bakim"):
            self.date_sonraki_bakim.setDate(QDate.currentDate())
        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.setText("KAYDET")

    def _open_islemler_popup(self):
        popup = QDialog(self)
        popup.setWindowTitle("Yapılan İşlemleri Seçin")
        popup.setMinimumWidth(300)

        layout = QVBoxLayout()
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # Sabitler: group_name = bakim_islemleri
        const_islemler = [value for _id, value in self._get_constants_values("bakim_islemleri")]
        if const_islemler:
            islem_listesi = const_islemler
        else:
            # Fallback: legacy liste
            islem_listesi = [
                "Motor Yağı Değişimi",
                "Yağ Filtresi",
                "Hava Filtresi",
                "Polen Filtresi",
                "Mazot Filtresi",
                "Ön Fren Balatası",
                "Arka Fren Balatası",
                "Antifriz Kontrolü",
                "Silecek Değişimi",
                "Şanzıman Yağı",
                "Baskı Balata",
                "Triger Seti",
            ]

        mevcut_islemler = []
        if hasattr(self, "txt_islemler"):
            mevcut_islemler = (self.txt_islemler.toPlainText() or "").split(", ")

        self._islem_checkboxes = []
        for islem in islem_listesi:
            cb = QCheckBox(islem)
            if islem in mevcut_islemler:
                cb.setChecked(True)
            scroll_layout.addWidget(cb)
            self._islem_checkboxes.append(cb)

        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

        btn_tamam = QPushButton("SEÇİLENLERİ AKTAR")
        btn_tamam.clicked.connect(lambda: self._islemleri_aktar(popup))
        layout.addWidget(btn_tamam)

        popup.setLayout(layout)
        popup.exec()

    def _islemleri_aktar(self, dialog):
        secilenler = [cb.text() for cb in self._islem_checkboxes if cb.isChecked()]
        if hasattr(self, "txt_islemler"):
            self.txt_islemler.setPlainText(", ".join(secilenler))
        dialog.accept()

    def _save_data(self):
        # Mevcut bir kayıt seçiliyse ve zaten muhasebeleşmişse tekrar muhasebeleştirme engeli
        if self.secili_bakim_id and hasattr(self, "btn_muhasebe"):
            sender = self.sender().objectName() if self.sender() else ""
            if sender == "btn_muhasebe":
                kayit = self.db.get_bakim_by_id(self.secili_bakim_id)
                if kayit and int(kayit.get("muhasebe_durum") or 0) == 1:
                    QMessageBox.warning(
                        self,
                        "Bilgi",
                        "Bu kayıt zaten muhasebeleşmiş. Tekrar aktarım yapılamaz.",
                    )
                    return

        if not hasattr(self, "cmb_arac") or self.cmb_arac.currentIndex() == 0:
            QMessageBox.warning(self, "Hata", "Araç bilgisi zorunludur!")
            return
        if not hasattr(self, "txt_bakim_km") or not self.txt_bakim_km.text().strip():
            QMessageBox.warning(self, "Hata", "Kilometre bilgisi zorunludur!")
            return

        maliyet_raw = (self.txt_maliyet.text() if hasattr(self, "txt_maliyet") else "") or ""
        maliyet_num = 0.0
        if maliyet_raw.strip():
            try:
                maliyet_num = float(maliyet_raw.replace(".", "").replace(",", "."))
            except Exception:
                maliyet_num = 0.0

        sender_name = self.sender().objectName() if self.sender() else ""
        muhasebe_durumu = 1 if sender_name == "btn_muhasebe" else 0

        bakim_turu = self.cmb_bakim_turu.currentText() if hasattr(self, "cmb_bakim_turu") else ""
        if bakim_turu == "Seçiniz...":
            bakim_turu = ""

        firma_adi = self.cmb_firma_adi.currentText() if hasattr(self, "cmb_firma_adi") else ""
        if firma_adi == "Seçiniz...":
            firma_adi = ""

        data = {
            "id": self.secili_bakim_id,
            "arac_kodu": self.cmb_arac.currentData(),
            "bakim_tarihi": self.date_bakim.date().toString("yyyy-MM-dd") if hasattr(self, "date_bakim") else "",
            "bakim_km": self.txt_bakim_km.text().strip(),
            "bakim_turu": bakim_turu,
            "firma_adi": firma_adi,
            "yapilan_islemler": self.txt_islemler.toPlainText() if hasattr(self, "txt_islemler") else "",
            "maliyet": maliyet_num,
            "fis_no": self.txt_fis_no.text().strip() if hasattr(self, "txt_fis_no") else "",
            "sonraki_bakim_tarihi": self.date_sonraki_bakim.date().toString("yyyy-MM-dd")
            if hasattr(self, "date_sonraki_bakim")
            else "",
            "muhasebe_durum": muhasebe_durumu,
        }

        ok = self.db.save_bakim(data)
        if not ok:
            QMessageBox.critical(self, "Hata", "Kayıt sırasında bir hata oluştu.")
            return

        msg = "Bakım muhasebeleşerek kaydedildi." if muhasebe_durumu == 1 else "Bakım kaydedildi."
        QMessageBox.information(self, "Başarılı", msg)
        self._load_table()
        self._clear_form()

    def _on_row_selected(self, item):
        if not item or not hasattr(self, "table_bakim"):
            return
        row = item.row()
        id_item = self.table_bakim.item(row, 0)
        if not id_item:
            return
        try:
            bakim_id = int(id_item.text())
        except Exception:
            return

        kayit = self.db.get_bakim_by_id(bakim_id)
        if not kayit:
            return

        self.secili_bakim_id = bakim_id

        if hasattr(self, "cmb_arac"):
            index = self.cmb_arac.findData(kayit.get("vehicle_code"))
            self.cmb_arac.setCurrentIndex(index if index >= 0 else 0)
        if hasattr(self, "date_bakim") and kayit.get("bakim_tarihi"):
            self.date_bakim.setDate(QDate.fromString(kayit.get("bakim_tarihi"), "yyyy-MM-dd"))
        if hasattr(self, "txt_bakim_km"):
            self.txt_bakim_km.setText(str(kayit.get("bakim_km") or ""))
        if hasattr(self, "cmb_bakim_turu") and kayit.get("bakim_turu"):
            self.cmb_bakim_turu.setCurrentText(kayit.get("bakim_turu"))
        if hasattr(self, "cmb_firma_adi") and kayit.get("firma_adi"):
            self.cmb_firma_adi.setCurrentText(kayit.get("firma_adi"))
        if hasattr(self, "txt_islemler"):
            self.txt_islemler.setPlainText(kayit.get("yapilan_islemler") or "")
        if hasattr(self, "txt_maliyet"):
            try:
                self.txt_maliyet.setText(f"{float(kayit.get('maliyet') or 0):.2f}".replace(".", ","))
            except Exception:
                self.txt_maliyet.setText("")
        if hasattr(self, "txt_fis_no"):
            self.txt_fis_no.setText(kayit.get("fis_no") or "")
        if hasattr(self, "date_sonraki_bakim") and kayit.get("sonraki_bakim_tarihi"):
            self.date_sonraki_bakim.setDate(
                QDate.fromString(kayit.get("sonraki_bakim_tarihi"), "yyyy-MM-dd")
            )

        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.setText("GÜNCELLE")

    def _delete_data(self):
        if not self.secili_bakim_id:
            QMessageBox.warning(self, "Seçim Yok", "Lütfen silmek istediğiniz kaydı tablodan seçin.")
            return

        soru = QMessageBox.question(
            self,
            "Onay",
            "Bu bakım kaydını silmek istediğinize emin misiniz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if soru != QMessageBox.StandardButton.Yes:
            return

        if self.db.delete_bakim(self.secili_bakim_id):
            self._load_table()
            self._clear_form()
            QMessageBox.information(self, "Bilgi", "Kayıt silindi.")
        else:
            QMessageBox.critical(self, "Hata", "Silme sırasında bir hata oluştu.")
