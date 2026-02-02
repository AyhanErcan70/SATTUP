from PyQt6.QtWidgets import QWidget, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy
from PyQt6.QtCore import Qt, QRegularExpression
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6 import uic

from app.core.db_manager import DatabaseManager
from config import get_ui_path


def tr_upper(text):
    text = text.replace('i', 'İ').replace('ı', 'I')
    return text.upper()


class CustomersApp(QWidget):
    def __init__(self, user_data=None, parent=None):
        super().__init__(parent)
        uic.loadUi(get_ui_path("customers_window.ui"), self)
        self.setObjectName("main_form")
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        except Exception:
            pass
        try:
            if hasattr(self, "top_frame") and self.top_frame is not None:
                self.top_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        except Exception:
            pass
        self.db = DatabaseManager()
        self.user_data = user_data

        self.current_code = None

        if hasattr(self, "txt_email"):
            self.txt_email.setValidator(QRegularExpressionValidator(QRegularExpression(r"[a-zA-Z0-9@._-]+")))
            self.txt_email.textChanged.connect(lambda text: self.txt_email.setText(text.lower()))

        self.fields = {
            "cmb_musteri_turu": "musteri_turu",
            "cmb_kisilik": "kisilik",
            "cmb_sektor": "sektor",
            "txt_firma": "title",
            "txt_vergi_tckn": "tax_number",
            "txt_vergi_dairesi": "vergi_dairesi",
            "txt_yetkili": "yetkili",
            "txt_gorevi": "gorevi",
            "txt_telefon": "phone",
            "txt_email": "email",
            "cmb_il": "il",
            "cmb_ilce": "ilce",
            "txt_adres1": "adres1",
            "txt_adres2": "adres2",
            "txt_bakiye": "bakiye",
            "txt_iban": "iban",
        }

        for field_name in self.fields.keys():
            widget = getattr(self, field_name, None)
            if widget is None:
                continue
            if hasattr(widget, "textChanged"):
                if (
                    "email" not in field_name.lower()
                    and "telefon" not in field_name.lower()
                    and "iban" not in field_name.lower()
                    and "bakiye" not in field_name.lower()
                ):
                    widget.textChanged.connect(lambda text, w=widget: w.setText(tr_upper(text)))

        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.clicked.connect(self.save)
        if hasattr(self, "btn_yeni"):
            self.btn_yeni.clicked.connect(self.clear_form)
        if hasattr(self, "btn_sil"):
            self.btn_sil.clicked.connect(self.delete_selected)
        if hasattr(self, "btn_aktifpasif"):
            self.btn_aktifpasif.clicked.connect(self.toggle_active_selected)
        if hasattr(self, "btn_pdfye_aktar"):
            self.btn_pdfye_aktar.clicked.connect(self.export_pdf)
        if hasattr(self, "btn_excele_aktar"):
            self.btn_excele_aktar.clicked.connect(self.export_excel)
        if hasattr(self, "tableView"):
            self.tableView.doubleClicked.connect(self.select_record)

        self._init_combos()

        if hasattr(self, "cmb_kisilik"):
            self.cmb_kisilik.currentIndexChanged.connect(self._update_kisilik_ui)

        self.load_data()
        self._setup_filters()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table_size_changed()
        self._assign_next_code()

        self._update_kisilik_ui()

    def _update_kisilik_ui(self):
        kisilik = (self.cmb_kisilik.currentText() or "").strip() if hasattr(self, "cmb_kisilik") else ""
        is_gercek = kisilik == "Gerçek Kişi"

        if hasattr(self, "lbl_vergi_tckn"):
            self.lbl_vergi_tckn.setText("TCKN" if is_gercek else "Vergi No")

        if hasattr(self, "txt_vergi_dairesi"):
            self.txt_vergi_dairesi.setEnabled(not is_gercek)
            if is_gercek:
                self.txt_vergi_dairesi.clear()

    def _assign_next_code(self):
        if hasattr(self, "txt_musteri_kodu"):
            self.txt_musteri_kodu.setText(self.db.get_next_customer_code())

    def _init_combos(self):
        if hasattr(self, "cmb_musteri_turu"):
            self.cmb_musteri_turu.clear()
            self.cmb_musteri_turu.addItem("Seçiniz...", None)
            self.cmb_musteri_turu.addItem("MÜŞTERİ", "MÜŞTERİ")
            self.cmb_musteri_turu.addItem("ALT YÜKLENICI", "ALT YÜKLENICI")

        if hasattr(self, "cmb_kisilik"):
            self.cmb_kisilik.clear()
            self.cmb_kisilik.addItem("Seçiniz...", None)
            self.cmb_kisilik.addItem("GERÇEK KİŞİ", "GERÇEK KİŞİ")
            self.cmb_kisilik.addItem("TÜZEL KİŞİ", "TÜZEL KİŞİ")

        if hasattr(self, "cmb_sektor"):
            self.cmb_sektor.clear()
            self.cmb_sektor.addItem("Seçiniz...", None)
            self.cmb_sektor.addItem("ÖZEL SEKTÖR", "ÖZEL SEKTÖR")
            self.cmb_sektor.addItem("KAMU", "KAMU")

        # İl/İlçe sabit tablosundan
        if hasattr(self, "cmb_il"):
            self.cmb_il.clear()
            self.cmb_il.addItem("Seçiniz...", None)
            try:
                for _id, value in self.db.get_constants("il"):
                    self.cmb_il.addItem(value, _id)
            except Exception:
                pass
            self.cmb_il.currentIndexChanged.connect(self.fill_districts)

        if hasattr(self, "cmb_ilce"):
            self.cmb_ilce.clear()
            self.cmb_ilce.addItem("Seçiniz...", None)

    def fill_districts(self):
        if not hasattr(self, "cmb_il") or not hasattr(self, "cmb_ilce"):
            return
        self.cmb_ilce.blockSignals(True)
        self.cmb_ilce.clear()
        self.cmb_ilce.addItem("Seçiniz...", None)
        il_id = self.cmb_il.currentData()
        if il_id:
            try:
                for _id, value in self.db.get_constants("ilce", parent_id=il_id):
                    self.cmb_ilce.addItem(value, _id)
            except Exception:
                pass
        self.cmb_ilce.blockSignals(False)

    def load_data(self):
        headers = ["MÜŞ.KODU", "MÜŞ.TÜRÜ", "KİŞİLİK", "FİRMA/UNVAN", "VERGİ/TCKN", "İL", "İLÇE", "TELEFON", "E-POSTA", "DURUM"]
        if not hasattr(self, "tableView"):
            return

        try:
            self.tableView.setAlternatingRowColors(True)
        except Exception:
            pass

        self.tableView.setColumnCount(len(headers))
        self.tableView.setHorizontalHeaderLabels(headers)
        self.tableView.verticalHeader().setDefaultSectionSize(20)
        self.tableView.verticalHeader().setVisible(False)

        header = self.tableView.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        # header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)

        query = """
            SELECT customer_code, musteri_turu, kisilik, title, tax_number, il, ilce, phone, email, is_active
            FROM customers
            ORDER BY id ASC
        """

        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(query)
            data = cursor.fetchall()
            conn.close()

            self.tableView.setRowCount(len(data))
            for row_idx, row_val in enumerate(data):
                for col_idx, value in enumerate(row_val):
                    if col_idx == 9:
                        display_text = "AKTİF" if value == 1 else "PASİF"
                    else:
                        display_text = str(value) if value is not None else ""

                    item = QTableWidgetItem(display_text)
                    if col_idx in [0, 1, 2, 4, 5, 6, 7, 9]:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if col_idx == 9 and value == 0:
                        item.setForeground(Qt.GlobalColor.red)
                    self.tableView.setItem(row_idx, col_idx, item)
        except Exception as e:
            print(f"Müşteri yükleme hatası: {e}")

        if hasattr(self, "apply_filters"):
            self.apply_filters()

    def _normalize_combo_text(self, combo):
        if combo is None:
            return ""
        txt = (combo.currentText() or "").strip()
        if not txt or txt.lower().startswith("seç") or txt.lower() == "tümü":
            return ""
        return txt

    def _setup_filters(self):
        required = [
            "cmb_musteri_turu_f",
            "cmb_kisilik_f",
            "cmb_durum_f",
            "txt_firma_f",
            "txt_vergi_tckn_f",
        ]
        for name in required:
            if not hasattr(self, name):
                return

        # Combo içerikleri
        self.cmb_musteri_turu_f.blockSignals(True)
        self.cmb_musteri_turu_f.clear()
        self.cmb_musteri_turu_f.addItem("TÜMÜ")
        self.cmb_musteri_turu_f.addItem("MÜŞTERİ")
        self.cmb_musteri_turu_f.addItem("ALT YÜKLENICI")
        self.cmb_musteri_turu_f.blockSignals(False)

        self.cmb_kisilik_f.blockSignals(True)
        self.cmb_kisilik_f.clear()
        self.cmb_kisilik_f.addItem("TÜMÜ")
        self.cmb_kisilik_f.addItem("GERÇEK KİŞİ")
        self.cmb_kisilik_f.addItem("TÜZEL KİŞİ")
        self.cmb_kisilik_f.blockSignals(False)

        self.cmb_durum_f.blockSignals(True)
        self.cmb_durum_f.clear()
        self.cmb_durum_f.addItem("TÜMÜ")
        self.cmb_durum_f.addItem("AKTİF")
        self.cmb_durum_f.addItem("PASİF")
        self.cmb_durum_f.blockSignals(False)

        self.txt_firma_f.textChanged.connect(self.apply_filters)
        self.txt_vergi_tckn_f.textChanged.connect(self.apply_filters)
        self.cmb_musteri_turu_f.currentIndexChanged.connect(self.apply_filters)
        self.cmb_kisilik_f.currentIndexChanged.connect(self.apply_filters)
        self.cmb_durum_f.currentIndexChanged.connect(self.apply_filters)
        if hasattr(self, "btn_temizle_f"):
            self.btn_temizle_f.clicked.connect(self.clear_filters)

    def clear_filters(self):
        if hasattr(self, "txt_firma_f"):
            self.txt_firma_f.clear()
        if hasattr(self, "txt_vergi_tckn_f"):
            self.txt_vergi_tckn_f.clear()
        if hasattr(self, "cmb_musteri_turu_f"):
            self.cmb_musteri_turu_f.setCurrentIndex(0)
        if hasattr(self, "cmb_kisilik_f"):
            self.cmb_kisilik_f.setCurrentIndex(0)
        if hasattr(self, "cmb_durum_f"):
            self.cmb_durum_f.setCurrentIndex(0)
        self.apply_filters()

    def apply_filters(self):
        if not hasattr(self, "tableView"):
            return

        musteri_turu = self._normalize_combo_text(getattr(self, "cmb_musteri_turu_f", None))
        kisilik = self._normalize_combo_text(getattr(self, "cmb_kisilik_f", None))
        durum = self._normalize_combo_text(getattr(self, "cmb_durum_f", None))
        firma_q = (self.txt_firma_f.text() or "").strip().lower() if hasattr(self, "txt_firma_f") else ""
        vergi_q = (self.txt_vergi_tckn_f.text() or "").strip() if hasattr(self, "txt_vergi_tckn_f") else ""

        for row in range(self.tableView.rowCount()):
            row_tur = (self.tableView.item(row, 1).text() if self.tableView.item(row, 1) else "").strip()
            row_kis = (self.tableView.item(row, 2).text() if self.tableView.item(row, 2) else "").strip()
            row_firma = (self.tableView.item(row, 3).text() if self.tableView.item(row, 3) else "").strip().lower()
            row_vergi = (self.tableView.item(row, 4).text() if self.tableView.item(row, 4) else "").strip()
            row_durum = (self.tableView.item(row, 9).text() if self.tableView.item(row, 9) else "").strip()

            ok = True
            if musteri_turu and row_tur != musteri_turu:
                ok = False
            if ok and kisilik and row_kis != kisilik:
                ok = False
            if ok and durum and row_durum != durum:
                ok = False
            if ok and firma_q and firma_q not in row_firma:
                ok = False
            if ok and vergi_q and vergi_q not in row_vergi:
                ok = False

            self.tableView.setRowHidden(row, not ok)

    def _only_digits(self, value: str) -> str:
        import re
        return re.sub(r"\D", "", value or "")

    def _get_selected_customer_code(self):
        if not hasattr(self, "tableView"):
            return ""
        selected_items = self.tableView.selectedItems() if hasattr(self.tableView, "selectedItems") else []
        if not selected_items:
            return ""
        row = selected_items[0].row()
        item = self.tableView.item(row, 0) if hasattr(self.tableView, "item") else None
        return item.text().strip() if item else ""

    def export_pdf(self):
        try:
            from app.utils.pdf_utils import create_pdf
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"PDF modülü yüklenemedi:\n{str(e)}")
            return

        if not hasattr(self, "tableView"):
            QMessageBox.warning(self, "Uyarı", "Tablo bulunamadı!")
            return

        export_table = QTableWidget()
        export_table.setColumnCount(self.tableView.columnCount())

        headers = []
        for c in range(self.tableView.columnCount()):
            h = self.tableView.horizontalHeaderItem(c)
            headers.append(h.text() if h else "")
        export_table.setHorizontalHeaderLabels(headers)

        visible_rows = [r for r in range(self.tableView.rowCount()) if not self.tableView.isRowHidden(r)]
        export_table.setRowCount(len(visible_rows))

        for out_r, src_r in enumerate(visible_rows):
            for c in range(self.tableView.columnCount()):
                item = self.tableView.item(src_r, c)
                export_table.setItem(out_r, c, QTableWidgetItem(item.text() if item else ""))

        create_pdf(export_table, report_title="Müşteri Listesi", username="Admin", parent=self)

    def export_excel(self):
        try:
            from app.utils.excel_utils import create_excel
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Excel modülü yüklenemedi:\n{str(e)}")
            return

        if not hasattr(self, "tableView"):
            QMessageBox.warning(self, "Uyarı", "Tablo bulunamadı!")
            return

        export_table = QTableWidget()
        export_table.setColumnCount(self.tableView.columnCount())

        headers = []
        for c in range(self.tableView.columnCount()):
            h = self.tableView.horizontalHeaderItem(c)
            headers.append(h.text() if h else "")
        export_table.setHorizontalHeaderLabels(headers)

        visible_rows = [r for r in range(self.tableView.rowCount()) if not self.tableView.isRowHidden(r)]
        export_table.setRowCount(len(visible_rows))

        for out_r, src_r in enumerate(visible_rows):
            for c in range(self.tableView.columnCount()):
                item = self.tableView.item(src_r, c)
                export_table.setItem(out_r, c, QTableWidgetItem(item.text() if item else ""))

        create_excel(export_table, report_title="Müşteri Listesi", username="Admin", parent=self)

    def toggle_active_selected(self):
        code = self._get_selected_customer_code()
        if not code:
            QMessageBox.warning(self, "Uyarı", "Lütfen tablodan bir müşteri seçin.")
            return
        if not self.db.toggle_customer_active_status(code):
            QMessageBox.critical(self, "Hata", "Aktif/Pasif durumu güncellenemedi.")
            return
        self.load_data()

    def delete_selected(self):
        role = (self.user_data or {}).get("role") if isinstance(self.user_data, dict) else None
        if role != "admin":
            QMessageBox.warning(self, "Yetki Yok", "Bu işlemi yapmak için admin yetkisi gereklidir.")
            return

        code = self._get_selected_customer_code()
        if not code:
            QMessageBox.warning(self, "Uyarı", "Lütfen tablodan bir müşteri seçin.")
            return

        soru = QMessageBox.question(
            self,
            "Onay",
            f"{code} kodlu müşteri silinsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if soru != QMessageBox.StandardButton.Yes:
            return

        if not self.db.delete_customer_by_code(code):
            QMessageBox.critical(self, "Hata", "Silme işlemi başarısız.")
            return
        self.load_data()
        self.clear_form()

    def _collect_form_data(self):
        data = {}
        for ui_obj, db_col in self.fields.items():
            widget = getattr(self, ui_obj, None)
            if widget is None:
                continue

            if ui_obj.startswith("cmb_"):
                txt = (widget.currentText() or "").strip()
                data[db_col] = "" if (not txt or txt.lower().startswith("seç")) else txt
            else:
                val = (widget.text() or "").strip()
                if ui_obj == "txt_bakiye":
                    try:
                        data[db_col] = float(val.replace(",", ".")) if val else 0.0
                    except Exception:
                        data[db_col] = 0.0
                elif ui_obj == "txt_iban":
                    # TR maskeli -> sadece rakamları sakla
                    digits = self._only_digits(val)
                    data[db_col] = digits
                else:
                    data[db_col] = val

        # legacy columns
        if "tax_office" not in data:
            data["tax_office"] = data.get("vergi_dairesi", "")
        if "address" not in data:
            addr = " ".join([data.get("adres1", ""), data.get("adres2", "")]).strip()
            data["address"] = addr
        return data

    def save(self):
        if not hasattr(self, "txt_musteri_kodu"):
            return

        code = (self.txt_musteri_kodu.text() or "").strip()
        title = (self.txt_firma.text() or "").strip() if hasattr(self, "txt_firma") else ""
        tax_number = (self.txt_vergi_tckn.text() or "").strip() if hasattr(self, "txt_vergi_tckn") else ""

        if not title:
            QMessageBox.warning(self, "Eksik Bilgi", "Firma Adı/Unvanı boş bırakılamaz!")
            if hasattr(self, "txt_firma"):
                self.txt_firma.setFocus()
            return

        if not tax_number:
            QMessageBox.warning(self, "Eksik Bilgi", "Vergi No/TCKN boş bırakılamaz!")
            if hasattr(self, "txt_vergi_tckn"):
                self.txt_vergi_tckn.setFocus()
            return

        current_code = self.current_code if self.current_code else None
        if self.db.check_customer_tax_number_exists(tax_number, current_code=current_code):
            QMessageBox.warning(self, "Uyarı", "Bu Vergi No/TCKN başka bir kayıtta kullanılıyor!")
            if hasattr(self, "txt_vergi_tckn"):
                self.txt_vergi_tckn.setFocus()
            return

        data = self._collect_form_data()
        data["customer_code"] = code

        is_update = self.current_code is not None
        ok = self.db.save_customer(data, is_update=is_update)
        if ok:
            QMessageBox.information(self, "Başarılı", "İşlem başarıyla tamamlandı.")
            self.load_data()
            self.clear_form()
        else:
            QMessageBox.critical(self, "Hata", "Kayıt işlemi başarısız.")

    def clear_form(self):
        self.current_code = None
        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.setText("KAYDET")

        for ui_obj in self.fields.keys():
            widget = getattr(self, ui_obj, None)
            if widget is None:
                continue
            if ui_obj.startswith("cmb_"):
                widget.setCurrentIndex(0)
            else:
                widget.clear()

        if hasattr(self, "cmb_ilce"):
            self.cmb_ilce.clear()
            self.cmb_ilce.addItem("Seçiniz...", None)

        self._assign_next_code()
        if hasattr(self, "txt_firma"):
            self.txt_firma.setFocus()

    def select_record(self, item):
        if item is None:
            return
        row = item.row()
        code_item = self.tableView.item(row, 0) if hasattr(self, "tableView") else None
        code = code_item.text().strip() if code_item else ""
        if not code:
            return

        data = self.db.get_customer_details_by_code(code)
        if not data:
            return

        self.current_code = code
        if hasattr(self, "txt_musteri_kodu"):
            self.txt_musteri_kodu.setText(code)

        # form doldur
        def set_combo_by_text(combo, text):
            if combo is None:
                return
            text = (text or "").strip()
            if not text:
                combo.setCurrentIndex(0)
                return
            idx = combo.findText(text, Qt.MatchFlag.MatchFixedString)
            combo.setCurrentIndex(idx if idx >= 0 else 0)

        if hasattr(self, "cmb_musteri_turu"):
            set_combo_by_text(self.cmb_musteri_turu, data.get("musteri_turu"))
        if hasattr(self, "cmb_kisilik"):
            set_combo_by_text(self.cmb_kisilik, data.get("kisilik"))
            self._update_kisilik_ui()
        if hasattr(self, "cmb_sektor"):
            set_combo_by_text(self.cmb_sektor, data.get("sektor"))

        if hasattr(self, "txt_firma"):
            self.txt_firma.setText(str(data.get("title") or ""))
        if hasattr(self, "txt_vergi_tckn"):
            self.txt_vergi_tckn.setText(str(data.get("tax_number") or ""))
        if hasattr(self, "txt_vergi_dairesi"):
            self.txt_vergi_dairesi.setText(str(data.get("vergi_dairesi") or data.get("tax_office") or ""))
        if hasattr(self, "txt_yetkili"):
            self.txt_yetkili.setText(str(data.get("yetkili") or ""))
        if hasattr(self, "txt_gorevi"):
            self.txt_gorevi.setText(str(data.get("gorevi") or ""))
        if hasattr(self, "txt_telefon"):
            self.txt_telefon.setText(str(data.get("phone") or ""))
        if hasattr(self, "txt_email"):
            self.txt_email.setText(str(data.get("email") or ""))

        if hasattr(self, "cmb_il"):
            il_txt = str(data.get("il") or "").strip()
            idx = self.cmb_il.findText(il_txt, Qt.MatchFlag.MatchFixedString)
            self.cmb_il.setCurrentIndex(idx if idx >= 0 else 0)
            self.fill_districts()
        if hasattr(self, "cmb_ilce"):
            ilce_txt = str(data.get("ilce") or "").strip()
            idx = self.cmb_ilce.findText(ilce_txt, Qt.MatchFlag.MatchFixedString)
            self.cmb_ilce.setCurrentIndex(idx if idx >= 0 else 0)

        if hasattr(self, "txt_adres1"):
            self.txt_adres1.setText(str(data.get("adres1") or ""))
        if hasattr(self, "txt_adres2"):
            self.txt_adres2.setText(str(data.get("adres2") or ""))

        if hasattr(self, "txt_bakiye"):
            self.txt_bakiye.setText(str(data.get("bakiye") if data.get("bakiye") is not None else ""))
        if hasattr(self, "txt_iban"):
            iban_digits = self._only_digits(str(data.get("iban") or ""))
            self.txt_iban.setText(f"TR{iban_digits}" if iban_digits else "")

        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.setText("GÜNCELLE")
    def table_size_changed(self):
        self.tableView.setColumnWidth(0, 80)
        self.tableView.setColumnWidth(1, 80)
        self.tableView.setColumnWidth(2, 80)
        self.tableView.setColumnWidth(3, 650)
        self.tableView.setColumnWidth(4, 100)
        self.tableView.setColumnWidth(5, 100)
        self.tableView.setColumnWidth(6, 100)
        self.tableView.setColumnWidth(7, 120)
        self.tableView.setColumnWidth(8, 180)
        self.tableView.setColumnWidth(9, 60)
        