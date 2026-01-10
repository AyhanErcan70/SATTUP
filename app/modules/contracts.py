from PyQt6 import uic
from PyQt6.QtCore import QDate, Qt, QRegularExpression
from PyQt6.QtGui import QIntValidator, QRegularExpressionValidator
from PyQt6.QtWidgets import QWidget, QMessageBox, QTableWidgetItem, QHeaderView
from app.core.db_manager import DatabaseManager
from config import get_ui_path
from app.utils.style_utils import clear_all_styles
import json

class ContractsApp(QWidget):
    def __init__(self, user_data=None, parent=None):
        super().__init__(parent)
        uic.loadUi(get_ui_path("contracts_window.ui"), self)
        clear_all_styles(self)
        self.db = DatabaseManager()
        self.user_data = user_data or {}
        self.current_number = None
        if hasattr(self, "txt_sozlesme_kodu"):
            self.txt_sozlesme_kodu.setReadOnly(True)
            self.txt_sozlesme_kodu.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if hasattr(self, "txt_arac_adedi"):
            self.txt_arac_adedi.setValidator(QIntValidator(0, 999))
        if hasattr(self, "txt_toplam_tutar"):
            self.txt_toplam_tutar.setValidator(QRegularExpressionValidator(QRegularExpression(r"^[0-9]+([\\.,][0-9]{1,2})?$")))
        if hasattr(self, "txt_kdv_orani"):
            self.txt_kdv_orani.setValidator(QIntValidator(0, 100))
        self._init_dates()
        self._init_combos()
        self._init_price_table()
        self._setup_connections()
        self._assign_next_number()
        self.load_table()

    def _get_price_table(self):
        if hasattr(self, "table_fiyatlar"):
            return getattr(self, "table_fiyatlar")
        if hasattr(self, "table_fiyat"):
            return getattr(self, "table_fiyat")
        if hasattr(self, "tableWidget"):
            return getattr(self, "tableWidget")
        return None

    def _get_btn_fiyat_ekle(self):
        if hasattr(self, "btn_fiyat_ekle"):
            return getattr(self, "btn_fiyat_ekle")
        if hasattr(self, "toolButton"):
            return getattr(self, "toolButton")
        return None

    def _get_btn_fiyat_sil(self):
        if hasattr(self, "btn_fiyat_sil"):
            return getattr(self, "btn_fiyat_sil")
        if hasattr(self, "toolButton_2"):
            return getattr(self, "toolButton_2")
        return None

    def _get_contracts_table(self):
        if hasattr(self, "tbl_sozlesmeler"):
            return getattr(self, "tbl_sozlesmeler")
        if hasattr(self, "table_View"):
            return getattr(self, "table_View")
        return None

    def _init_price_table(self):
        tbl = self._get_price_table()
        if tbl is None:
            return

        headers = ["GÜZERGAH", "GİDİŞ GELİŞ", "KM", "FİYAT"]
        tbl.setColumnCount(len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.verticalHeader().setVisible(False)
        tbl.setAlternatingRowColors(True)
        tbl.setSelectionBehavior(tbl.SelectionBehavior.SelectRows)
        tbl.setSelectionMode(tbl.SelectionMode.ExtendedSelection)

        h = tbl.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        # Kullanıcı fiyatı tablo üzerinden belirleyecek -> toplam otomatik hesaplanır
        if hasattr(self, "txt_toplam_tutar"):
            try:
                self.txt_toplam_tutar.setReadOnly(True)
            except Exception:
                pass

        # Varsayılan ilk satır
        if tbl.rowCount() == 0:
            self._price_add_row()

        self._recalc_price_total()

    def _init_dates(self):
        for name in ["date_baslangic", "date_bitis"]:
            w = getattr(self, name, None)
            if w is None:
                continue
            w.setCalendarPopup(True)
            w.setDisplayFormat("dd.MM.yyyy")
            w.setDate(QDate.currentDate())

    def _init_combos(self):
        if hasattr(self, "cmb_hizmet_tipi"):
            self.cmb_hizmet_tipi.clear()
            self.cmb_hizmet_tipi.addItem("Seçiniz...")
            self.cmb_hizmet_tipi.addItems(["OKUL", "PERSONEL", "DİĞER"])
        if hasattr(self, "cmb_ucret_tipi"):
            self.cmb_ucret_tipi.clear()
            self.cmb_ucret_tipi.addItem("Seçiniz...")
            self.cmb_ucret_tipi.addItems(["AYLIK", "GÜNLÜK", "SEFER BAŞI"])
        if hasattr(self, "cmb_musteri"):
            self.cmb_musteri.clear()
            self._load_customers()

    def _load_customers(self):
        items = []
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute("SELECT id, COALESCE(title, '') FROM customers WHERE is_active = 1 ORDER BY title")
            items = cursor.fetchall()
            conn.close()
        except Exception:
            items = []
        for _id, title in items:
            self.cmb_musteri.addItem(title or "", _id)

    def _setup_connections(self):
        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.clicked.connect(self.save)
        if hasattr(self, "btn_temizle"):
            self.btn_temizle.clicked.connect(self.clear_form)
        if hasattr(self, "txt_toplam_tutar"):
            self.txt_toplam_tutar.textChanged.connect(self._update_kdv_total)
        if hasattr(self, "txt_kdv_orani"):
            self.txt_kdv_orani.textChanged.connect(self._update_kdv_total)

        btn_add = self._get_btn_fiyat_ekle()
        if btn_add is not None:
            btn_add.clicked.connect(self._price_add_row)
        btn_del = self._get_btn_fiyat_sil()
        if btn_del is not None:
            btn_del.clicked.connect(self._price_delete_row)

        tbl = self._get_price_table()
        if tbl is not None:
            tbl.cellChanged.connect(self._recalc_price_total)

        list_tbl = self._get_contracts_table()
        if list_tbl is not None:
            list_tbl.doubleClicked.connect(self.select_contract)

    def _format_date_tr(self, iso_date: str) -> str:
        s = (iso_date or "").strip()
        if not s:
            return ""
        try:
            d = QDate.fromString(s, "yyyy-MM-dd")
            if d.isValid():
                return d.toString("dd.MM.yyyy")
        except Exception:
            pass
        return s

    def _set_date_from_iso(self, widget_name: str, iso_date: str):
        w = getattr(self, widget_name, None)
        if w is None:
            return
        s = (iso_date or "").strip()
        if not s:
            return
        d = QDate.fromString(s, "yyyy-MM-dd")
        if d.isValid():
            w.setDate(d)

    def _load_price_table_from_json(self, price_matrix_json: str):
        tbl = self._get_price_table()
        if tbl is None:
            return
        try:
            rows = json.loads(price_matrix_json) if price_matrix_json else []
            if not isinstance(rows, list):
                rows = []
        except Exception:
            rows = []

        tbl.blockSignals(True)
        tbl.setRowCount(0)
        for r in rows:
            tbl.insertRow(tbl.rowCount())
            rr = tbl.rowCount() - 1
            guz = str((r or {}).get("guzergah") or "")
            gidis = str((r or {}).get("gidis_gelis") or "")
            km = (r or {}).get("km")
            fiyat = (r or {}).get("fiyat")
            values = [
                guz,
                gidis,
                ("" if km is None else str(km)),
                ("" if fiyat is None else self._format_money_tr(float(fiyat or 0.0))),
            ]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c in (2, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tbl.setItem(rr, c, item)
        tbl.blockSignals(False)
        if tbl.rowCount() == 0:
            self._price_add_row()
        self._recalc_price_total()

    def select_contract(self, index):
        tbl = self._get_contracts_table()
        if tbl is None:
            return
        try:
            row = index.row()
        except Exception:
            return

        code_item = tbl.item(row, 0)
        contract_number = (code_item.text().strip() if code_item else "")
        if not contract_number:
            return

        details = self.db.get_contract_details_by_number(contract_number)
        if not details:
            return

        self.current_number = contract_number
        if hasattr(self, "txt_sozlesme_kodu"):
            self.txt_sozlesme_kodu.setText(contract_number)

        # Müşteri
        cust_id = details.get("customer_id")
        if hasattr(self, "cmb_musteri"):
            for i in range(self.cmb_musteri.count()):
                if self.cmb_musteri.itemData(i) == cust_id:
                    self.cmb_musteri.setCurrentIndex(i)
                    break

        # Hizmet tipi / ücret tipi
        if hasattr(self, "cmb_hizmet_tipi") and details.get("contract_type") is not None:
            self.cmb_hizmet_tipi.setCurrentText(str(details.get("contract_type") or ""))
        if hasattr(self, "cmb_ucret_tipi") and details.get("ucret_tipi") is not None:
            self.cmb_ucret_tipi.setCurrentText(str(details.get("ucret_tipi") or ""))

        # Tarihler
        self._set_date_from_iso("date_baslangic", str(details.get("start_date") or ""))
        self._set_date_from_iso("date_bitis", str(details.get("end_date") or ""))

        # Diğer alanlar
        if hasattr(self, "txt_arac_adedi"):
            self.txt_arac_adedi.setText(str(details.get("arac_adedi") or ""))
        if hasattr(self, "chk_esnek_sefer"):
            self.chk_esnek_sefer.setChecked(bool(int(details.get("esnek_sefer") or 0)))
        if hasattr(self, "radio_uzama_var") and hasattr(self, "radio_uzama_yok"):
            uz = int(details.get("uzatma") or 0)
            self.radio_uzama_var.setChecked(uz == 1)
            self.radio_uzama_yok.setChecked(uz != 1)
        if hasattr(self, "txt_kdv_orani"):
            k = details.get("kdv_orani")
            self.txt_kdv_orani.setText("" if k is None else str(int(float(k) or 0)))

        # Fiyat matrisi varsa yükle, yoksa toplam tutarı göster
        pm = details.get("price_matrix_json")
        if pm:
            self._load_price_table_from_json(pm)
        else:
            if hasattr(self, "txt_toplam_tutar"):
                self.txt_toplam_tutar.setText(self._format_money_tr(float(details.get("toplam_tutar") or 0.0)))
            self._recalc_price_total()

        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.setText("GÜNCELLE")

    def _parse_money(self, s: str) -> float:
        s = (s or "").strip()
        if not s:
            return 0.0

        # Türkçe format desteği: 1.234,56 -> 1234.56
        s = s.replace(" ", "")
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        try:
            return float(s)
        except Exception:
            return 0.0

    def _format_money_tr(self, v: float) -> str:
        try:
            return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return ""

    def _price_add_row(self):
        tbl = self._get_price_table()
        if tbl is None:
            return

        r = tbl.rowCount()
        tbl.blockSignals(True)
        tbl.insertRow(r)
        for c in range(tbl.columnCount()):
            item = QTableWidgetItem("")
            if c in (2, 3):
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tbl.setItem(r, c, item)
        tbl.blockSignals(False)
        self._recalc_price_total()

    def _price_delete_row(self):
        tbl = self._get_price_table()
        if tbl is None:
            return

        selected = set()
        for it in tbl.selectedItems():
            selected.add(it.row())
        rows = sorted(selected, reverse=True)
        if not rows and tbl.rowCount() > 0:
            rows = [tbl.rowCount() - 1]

        tbl.blockSignals(True)
        for r in rows:
            if 0 <= r < tbl.rowCount():
                tbl.removeRow(r)
        tbl.blockSignals(False)

        self._recalc_price_total()

    def _recalc_price_total(self):
        tbl = self._get_price_table()
        if tbl is None or not hasattr(self, "txt_toplam_tutar"):
            return

        total = 0.0
        for r in range(tbl.rowCount()):
            price_item = tbl.item(r, 3)
            total += self._parse_money(price_item.text() if price_item else "")

        self.txt_toplam_tutar.blockSignals(True)
        self.txt_toplam_tutar.setText(self._format_money_tr(total))
        self.txt_toplam_tutar.blockSignals(False)
        self._update_kdv_total()

    def _collect_price_matrix(self):
        tbl = self._get_price_table()
        if tbl is None:
            return []

        rows = []
        for r in range(tbl.rowCount()):
            guz = (tbl.item(r, 0).text().strip() if tbl.item(r, 0) else "")
            gidis = (tbl.item(r, 1).text().strip() if tbl.item(r, 1) else "")
            km_txt = (tbl.item(r, 2).text().strip() if tbl.item(r, 2) else "")
            fiyat_txt = (tbl.item(r, 3).text().strip() if tbl.item(r, 3) else "")

            if not any([guz, gidis, km_txt, fiyat_txt]):
                continue

            row = {
                "guzergah": guz,
                "gidis_gelis": gidis,
                "km": self._parse_money(km_txt),
                "fiyat": self._parse_money(fiyat_txt),
            }
            rows.append(row)
        return rows

    def _assign_next_number(self):
        if hasattr(self, "txt_sozlesme_kodu"):
            self.txt_sozlesme_kodu.setText(self.db.get_next_contract_number())

    def _update_kdv_total(self):
        t = (self.txt_toplam_tutar.text() or "").replace(",", ".") if hasattr(self, "txt_toplam_tutar") else ""
        k = (self.txt_kdv_orani.text() or "") if hasattr(self, "txt_kdv_orani") else ""
        try:
            tutar = float(t) if t else 0.0
            kdv = int(k) if k else 0
            d = tutar * (1 + kdv / 100.0)
            if hasattr(self, "lbl_kdv_dahil_tutar"):
                self.lbl_kdv_dahil_tutar.setText(f"{d:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        except Exception:
            if hasattr(self, "lbl_kdv_dahil_tutar"):
                self.lbl_kdv_dahil_tutar.setText("")

    def _get_date_str(self, name):
        w = getattr(self, name, None)
        if w is None:
            return ""
        return w.date().toString("yyyy-MM-dd")

    def _collect_form_data(self):
        cust_id = self.cmb_musteri.currentData() if hasattr(self, "cmb_musteri") else None
        toplam_txt = (self.txt_toplam_tutar.text() if hasattr(self, "txt_toplam_tutar") else "") or ""
        data = {
            "customer_id": int(cust_id) if cust_id is not None else None,
            "contract_number": (self.txt_sozlesme_kodu.text() or "").strip() if hasattr(self, "txt_sozlesme_kodu") else "",
            "start_date": self._get_date_str("date_baslangic"),
            "end_date": self._get_date_str("date_bitis"),
            "contract_type": (self.cmb_hizmet_tipi.currentText() or "").strip() if hasattr(self, "cmb_hizmet_tipi") else "",
            "is_active": 1,
            "uzatma": 1 if (self.radio_uzama_var.isChecked() if hasattr(self, "radio_uzama_var") else False) else 0,
            "arac_adedi": int(self.txt_arac_adedi.text()) if hasattr(self, "txt_arac_adedi") and (self.txt_arac_adedi.text() or "").isdigit() else None,
            "esnek_sefer": 1 if (self.chk_esnek_sefer.isChecked() if hasattr(self, "chk_esnek_sefer") else False) else 0,
            "ucret_tipi": (self.cmb_ucret_tipi.currentText() or "").strip() if hasattr(self, "cmb_ucret_tipi") else "",
            "toplam_tutar": self._parse_money(toplam_txt),
            "kdv_orani": float(self.txt_kdv_orani.text()) if hasattr(self, "txt_kdv_orani") and (self.txt_kdv_orani.text() or "").isdigit() else 0.0,
        }

        # Fiyat matrisi: contracts tablosundaki price_matrix_json alanına yazılır
        matrix = self._collect_price_matrix()
        if matrix:
            data["price_matrix_json"] = json.dumps(matrix, ensure_ascii=False)
            # Toplam tutarı tabloda hesaplananla senkron tut
            data["toplam_tutar"] = sum(float(x.get("fiyat") or 0.0) for x in matrix)
        return data

    def save(self):
        data = self._collect_form_data()
        if not data.get("customer_id"):
            QMessageBox.warning(self, "Uyarı", "Müşteri seçimi gerekir.")
            return
        if not data.get("contract_number"):
            self._assign_next_number()
            data["contract_number"] = (self.txt_sozlesme_kodu.text() or "").strip()
        is_update = self.current_number is not None
        ok = self.db.save_contract(data, is_update=is_update)
        if ok:
            QMessageBox.information(self, "Başarılı", "Kayıt tamamlandı.")
            self.load_table()
            self.clear_form()
        else:
            QMessageBox.critical(self, "Hata", "Kayıt başarısız.")

    def clear_form(self):
        self.current_number = None
        if hasattr(self, "txt_sozlesme_kodu"):
            self._assign_next_number()
        if hasattr(self, "cmb_musteri"):
            self.cmb_musteri.setCurrentIndex(0)
        if hasattr(self, "cmb_hizmet_tipi"):
            self.cmb_hizmet_tipi.setCurrentIndex(0)
        if hasattr(self, "txt_arac_adedi"):
            self.txt_arac_adedi.clear()
        if hasattr(self, "chk_esnek_sefer"):
            self.chk_esnek_sefer.setChecked(False)
        if hasattr(self, "cmb_ucret_tipi"):
            self.cmb_ucret_tipi.setCurrentIndex(0)
        if hasattr(self, "txt_toplam_tutar"):
            self.txt_toplam_tutar.clear()
        if hasattr(self, "txt_kdv_orani"):
            self.txt_kdv_orani.clear()
        tbl = self._get_price_table()
        if tbl is not None:
            tbl.blockSignals(True)
            tbl.setRowCount(0)
            tbl.blockSignals(False)
            self._price_add_row()
        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.setText("KAYDET")
        self._update_kdv_total()

    def load_table(self):
        tbl = self._get_contracts_table()
        if tbl is None:
            return

        headers = [
            "SÖZLEŞME KODU",
            "MÜŞTERİ (CARİ)",
            "SÖZLEŞME BAŞLANGIÇ TARİHİ",
            "BİTİŞ TARİHİ",
            "TOPLAM TUTAR",
            "DURUM",
        ]
        tbl.setColumnCount(len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.verticalHeader().setVisible(False)
        header = tbl.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        # Kolon genişlikleri (yaklaşık karakter genişliği -> px)
        # 1. sütun (kod) ~7 hane
        header.resizeSection(0, 90)
        # 3-4. sütunlar (tarih) ~10 hane
        header.resizeSection(2, 110)
        header.resizeSection(3, 110)
        # 5. sütun (toplam) ~12 hane
        header.resizeSection(4, 120)
        # 6. sütun (durum) ~5 hane
        header.resizeSection(5, 80)

        # 2. sütun (müşteri) kalan alanı kaplasın
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        tbl.setAlternatingRowColors(True)
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    c.contract_number,
                    COALESCE(cu.title, ''),
                    COALESCE(c.start_date, ''),
                    COALESCE(c.end_date, ''),
                    COALESCE(c.toplam_tutar, 0),
                    COALESCE(c.is_active, 1)
                FROM contracts c
                LEFT JOIN customers cu ON cu.id = c.customer_id
                ORDER BY c.id ASC
                """
            )
            rows = cursor.fetchall()
            conn.close()

            tbl.setRowCount(len(rows))
            for r, row in enumerate(rows):
                contract_no, customer_title, start_date, end_date, toplam_tutar, is_active = row
                values = [
                    contract_no,
                    customer_title,
                    self._format_date_tr(str(start_date or "")),
                    self._format_date_tr(str(end_date or "")),
                    self._format_money_tr(float(toplam_tutar or 0.0)),
                    "AKTİF" if int(is_active or 0) == 1 else "PASİF",
                ]
                for c, value in enumerate(values):
                    item = QTableWidgetItem(str(value) if value is not None else "")
                    if c in [0, 5]:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if c == 4:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    tbl.setItem(r, c, item)
        except Exception:
            tbl.setRowCount(0)
