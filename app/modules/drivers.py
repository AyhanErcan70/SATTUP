from PyQt6 import uic
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import QWidget, QMessageBox, QListWidgetItem

from app.core.db_manager import DatabaseManager
from config import get_ui_path


class DriversApp(QWidget):
    def __init__(self, user_data=None, db_manager=None, parent=None):
        super().__init__(parent)
        uic.loadUi(get_ui_path("drivers_window.ui"), self)
        self.setObjectName("main_form")

        self.user_data = user_data or {}
        self.db = db_manager if db_manager else DatabaseManager()
        self._selected_personel_kodu = None

        self._init_ui()
        self._init_combos()
        self._connect_signals()
        self._load_drivers_list()

    def _init_ui(self):
        for attr in [
            "txt_personel_kodu",
            "txt_personel_turu",
            "txt_ad_soyad",
            "txt_tckn",
            "txt_gsm",
            "txt_kan_grubu",
        ]:
            if hasattr(self, attr):
                getattr(self, attr).setReadOnly(True)

        for attr in ["date_ehliyet_tarihi", "date_src_tarihi", "date_psikoteknik_tarihi"]:
            if hasattr(self, attr):
                w = getattr(self, attr)
                w.setDisplayFormat("dd.MM.yyyy")
                w.setCalendarPopup(True)
                w.setDate(QDate.currentDate())

    def _init_combos(self):
        if hasattr(self, "cmb_ehliyet_sinifi"):
            self.cmb_ehliyet_sinifi.clear()
            self.cmb_ehliyet_sinifi.addItems(
                ["Seçiniz...", "B", "BE", "C1", "C1E", "C", "CE", "D1", "D1E", "D", "DE"]
            )

        if hasattr(self, "cmb_src"):
            self.cmb_src.clear()
            self.cmb_src.addItems(["Seçiniz...", "SRC 1", "SRC 2", "SRC 3", "SRC 4", "SRC 5"])

    def _connect_signals(self):
        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.clicked.connect(self._save_documents)
        if hasattr(self, "btn_yeni"):
            self.btn_yeni.clicked.connect(self._clear_document_fields)
        if hasattr(self, "btn_sil"):
            self.btn_sil.clicked.connect(self._delete_documents)
        if hasattr(self, "txt_ara"):
            self.txt_ara.textChanged.connect(self._filter_list)
        if hasattr(self, "list_suruculer"):
            self.list_suruculer.itemClicked.connect(self._driver_selected)

    def _load_drivers_list(self):
        if not hasattr(self, "list_suruculer"):
            return

        self.list_suruculer.clear()
        for kod, ad in self.db.get_sofor_listesi():
            item = QListWidgetItem(f"{ad} ({kod})")
            item.setData(Qt.ItemDataRole.UserRole, kod)
            self.list_suruculer.addItem(item)

    def _filter_list(self):
        if not hasattr(self, "list_suruculer"):
            return

        text = self.txt_ara.text().replace("i", "İ").replace("ı", "I").upper()
        for i in range(self.list_suruculer.count()):
            item = self.list_suruculer.item(i)
            item_text = item.text().replace("i", "İ").replace("ı", "I").upper()
            item.setHidden(text not in item_text)

    def _driver_selected(self, item):
        self._selected_personel_kodu = item.data(Qt.ItemDataRole.UserRole)

        p_data = self.db.get_personel_details(self._selected_personel_kodu)
        if p_data:
            self.txt_personel_kodu.setText(str(p_data.get("personel_kodu", "")))
            self.txt_personel_turu.setText(str(p_data.get("personel_turu", "")))
            self.txt_ad_soyad.setText(str(p_data.get("ad_soyad", "")))
            self.txt_tckn.setText(str(p_data.get("tckn", "")))
            self.txt_gsm.setText(str(p_data.get("gsm", "")))
            self.txt_kan_grubu.setText(str(p_data.get("kan_grubu", "")))

        s_data = self.db.get_surucu_belgeleri(self._selected_personel_kodu)
        if s_data:
            if hasattr(self, "cmb_ehliyet_sinifi"):
                self.cmb_ehliyet_sinifi.setCurrentText(s_data.get("ehliyet_sinifi") or "Seçiniz...")
            self._set_date(self.date_ehliyet_tarihi, s_data.get("ehliyet_tarihi"))

            if hasattr(self, "radio_src_var") and hasattr(self, "radio_src_yok"):
                self.radio_src_var.setChecked(int(s_data.get("src_durumu") or 0) == 1)
                self.radio_src_yok.setChecked(int(s_data.get("src_durumu") or 0) == 0)
            if hasattr(self, "cmb_src"):
                self.cmb_src.setCurrentText(s_data.get("src_turu") or "Seçiniz...")
            self._set_date(self.date_src_tarihi, s_data.get("src_tarihi"))

            if hasattr(self, "radio_psikoteknik_var") and hasattr(self, "radio_psikoteknik_yok"):
                self.radio_psikoteknik_var.setChecked(int(s_data.get("psikoteknik_durumu") or 0) == 1)
                self.radio_psikoteknik_yok.setChecked(int(s_data.get("psikoteknik_durumu") or 0) == 0)
            self._set_date(self.date_psikoteknik_tarihi, s_data.get("psikoteknik_tarihi"))

            if hasattr(self, "radio_sertifika_var") and hasattr(self, "radio_sertifika_yok"):
                self.radio_sertifika_var.setChecked(int(s_data.get("sertifika_durumu") or 0) == 1)
                self.radio_sertifika_yok.setChecked(int(s_data.get("sertifika_durumu") or 0) == 0)
            if hasattr(self, "txt_sertifikalar"):
                self.txt_sertifikalar.setPlainText(s_data.get("sertifika_metni") or "")
        else:
            self._clear_document_fields()

    def _clear_document_fields(self):
        if hasattr(self, "cmb_ehliyet_sinifi"):
            self.cmb_ehliyet_sinifi.setCurrentIndex(0)
        if hasattr(self, "cmb_src"):
            self.cmb_src.setCurrentIndex(0)

        for attr in [
            "radio_src_var",
            "radio_src_yok",
            "radio_psikoteknik_var",
            "radio_psikoteknik_yok",
            "radio_sertifika_var",
            "radio_sertifika_yok",
        ]:
            if hasattr(self, attr):
                r = getattr(self, attr)
                r.setAutoExclusive(False)
                r.setChecked(False)
                r.setAutoExclusive(True)

        if hasattr(self, "txt_sertifikalar"):
            self.txt_sertifikalar.clear()

        for attr in ["date_ehliyet_tarihi", "date_src_tarihi", "date_psikoteknik_tarihi"]:
            if hasattr(self, attr):
                getattr(self, attr).setDate(QDate.currentDate())

    def _set_date(self, widget, date_str):
        if not widget:
            return
        if date_str:
            d = QDate.fromString(date_str, "yyyy-MM-dd")
            if d.isValid():
                widget.setDate(d)

    def _save_documents(self):
        p_kodu = (self.txt_personel_kodu.text() or "").strip() if hasattr(self, "txt_personel_kodu") else ""
        if not p_kodu:
            QMessageBox.warning(self, "Hata", "Lütfen listeden bir şoför seçiniz!")
            return

        data = {
            "personel_kodu": p_kodu,
            "ehliyet_sinifi": self.cmb_ehliyet_sinifi.currentText() if hasattr(self, "cmb_ehliyet_sinifi") else None,
            "ehliyet_tarihi": self.date_ehliyet_tarihi.date().toString("yyyy-MM-dd") if hasattr(self, "date_ehliyet_tarihi") else None,
            "src_durumu": 1 if hasattr(self, "radio_src_var") and self.radio_src_var.isChecked() else 0,
            "src_turu": self.cmb_src.currentText() if hasattr(self, "cmb_src") else None,
            "src_tarihi": self.date_src_tarihi.date().toString("yyyy-MM-dd") if hasattr(self, "date_src_tarihi") else None,
            "psikoteknik_durumu": 1 if hasattr(self, "radio_psikoteknik_var") and self.radio_psikoteknik_var.isChecked() else 0,
            "psikoteknik_tarihi": self.date_psikoteknik_tarihi.date().toString("yyyy-MM-dd") if hasattr(self, "date_psikoteknik_tarihi") else None,
            "sertifika_durumu": 1 if hasattr(self, "radio_sertifika_var") and self.radio_sertifika_var.isChecked() else 0,
            "sertifika_metni": self.txt_sertifikalar.toPlainText() if hasattr(self, "txt_sertifikalar") else "",
            "resim_yolu": "",
        }

        if self.db.save_surucu_belgeleri(data):
            QMessageBox.information(self, "Başarılı", "Sürücü belgeleri kaydedildi.")
        else:
            QMessageBox.critical(self, "Hata", "Kayıt sırasında hata oluştu.")

    def _delete_documents(self):
        p_kodu = (self.txt_personel_kodu.text() or "").strip() if hasattr(self, "txt_personel_kodu") else ""
        if not p_kodu:
            QMessageBox.warning(self, "Hata", "Lütfen listeden bir şoför seçiniz!")
            return

        reply = QMessageBox.question(
            self,
            "Onay",
            "Bu şoföre ait belge/yeterlilik kayıtları silinsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if self.db.delete_surucu_belgeleri(p_kodu):
            QMessageBox.information(self, "Başarılı", "Belgeler silindi.")
            self._clear_document_fields()
        else:
            QMessageBox.warning(self, "Bilgi", "Silinecek belge kaydı bulunamadı.")
