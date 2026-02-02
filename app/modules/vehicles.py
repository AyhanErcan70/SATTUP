import os
from PyQt6.QtWidgets import (QMessageBox, QFileDialog, QWidget, QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt6.QtCore import QDate, Qt, QRegularExpression
from PyQt6.QtGui import QPixmap, QRegularExpressionValidator
from PyQt6 import uic

from app.core.db_manager import DatabaseManager
from config import get_ui_path

def _normalize_plate(text: str) -> str:
    import re
    t = (text or "").strip().upper()
    t = re.sub(r"\s+", " ", t)
    return t


class VehiclesApp(QWidget):
    def __init__(self, user_data=None, parent=None):
        super().__init__(parent)
        uic.loadUi(get_ui_path("vehicles_window.ui"), self)
        self.setObjectName("main_form")

        self.db = DatabaseManager()
        self.user_data = user_data
        self.current_code = None
        self._photo_path = ""

        if hasattr(self, "txt_arac_kodu"):
            self.txt_arac_kodu.setReadOnly(True)
            self.txt_arac_kodu.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        if hasattr(self, "txt_arac_plaka"):
            self.txt_arac_plaka.setValidator(QRegularExpressionValidator(QRegularExpression(r"[A-Z0-9\s]+")))

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

        if hasattr(self, "lbl_arac_foto"):
            self.lbl_arac_foto.setCursor(Qt.CursorShape.PointingHandCursor)
            self.lbl_arac_foto.mousePressEvent = self._on_photo_label_clicked

        self._init_combos()
        self._init_dates()
        self.load_data()
        self._setup_filters()
        self._assign_next_code()

    def _load_subcontractor_customers(self):
        cmb = getattr(self, "cmb_alt_yuklenici", None)
        if cmb is None:
            return
        try:
            cmb.blockSignals(True)
        except Exception:
            pass
        try:
            cmb.clear()
            cmb.addItem("Seçiniz...", None)
        except Exception:
            return

        items = []
        try:
            conn = self.db.connect()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, COALESCE(title,'')
                FROM customers
                WHERE COALESCE(is_active,1)=1
                  AND (COALESCE(musteri_turu,'') = 'ALT YÜKLENICI' OR COALESCE(musteri_turu,'') = 'ALT YÜKLENİCİ')
                ORDER BY title COLLATE NOCASE
                """
            )
            items = cur.fetchall() or []
            conn.close()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            items = []

        for _id, title in items:
            try:
                cmb.addItem(str(title or ""), int(_id) if _id is not None else None)
            except Exception:
                continue

        try:
            cmb.blockSignals(False)
        except Exception:
            pass

    def _init_dates(self):
        bugun = QDate.currentDate()
        for name in [
            "date_muayene",
            "date_sigorta",
            "date_koltuk",
            "date_kasko",
            "date_calisma_ruhsati",
            "date_guzergah_izin",
        ]:
            w = getattr(self, name, None)
            if w is None:
                continue
            w.setCalendarPopup(True)
            w.setDisplayFormat("dd.MM.yyyy")
            w.setDate(bugun)
            w.setMaximumDate(bugun)

    def _assign_next_code(self):
        if hasattr(self, "txt_arac_kodu"):
            self.txt_arac_kodu.setText(self.db.get_next_vehicle_code())

    def _init_combos(self):
        if hasattr(self, "cmb_arac_turu"):
            self.cmb_arac_turu.clear()
            self.cmb_arac_turu.addItem("Seçiniz...")
            self.cmb_arac_turu.addItem("ŞİRKET ARACI")
            self.cmb_arac_turu.addItem("TAŞERON ARACI")

        if hasattr(self, "cmb_hizmet_turu"):
            self.cmb_hizmet_turu.clear()
            self.cmb_hizmet_turu.addItem("Seçiniz...")
            self.cmb_hizmet_turu.addItem("SERVİS ARACI")
            self.cmb_hizmet_turu.addItem("HİZMET ARACI")
            self.cmb_hizmet_turu.currentIndexChanged.connect(self._update_kategori)

        if hasattr(self, "cmb_kategori"):
            self.cmb_kategori.clear()
            self.cmb_kategori.addItem("Seçiniz...")
            self.cmb_kategori.currentIndexChanged.connect(self._update_marka)

        if hasattr(self, "cmb_marka"):
            self.cmb_marka.clear()
            self.cmb_marka.addItem("Seçiniz...")
            self.cmb_marka.currentIndexChanged.connect(self._update_model)

        if hasattr(self, "cmb_model"):
            self.cmb_model.clear()
            self.cmb_model.addItem("Seçiniz...")

        self._load_subcontractor_customers()
        self._update_kategori()

    def _update_kategori(self):
        hizmet = (self.cmb_hizmet_turu.currentText() or "").strip() if hasattr(self, "cmb_hizmet_turu") else ""
        if not hasattr(self, "cmb_kategori"):
            return

        self.cmb_kategori.blockSignals(True)
        self.cmb_kategori.clear()
        self.cmb_kategori.addItem("Seçiniz...")

        if hizmet == "SERVİS ARACI":
            self.cmb_kategori.addItems(["OTOBÜS", "MİDİBÜS", "MİNİBÜS"])
        elif hizmet == "HİZMET ARACI":
            self.cmb_kategori.addItems(["OTOMOBİL", "KAMYONET", "PICK-UP"])

        self.cmb_kategori.blockSignals(False)
        self._update_marka()

    def _get_constants_values(self, group_name, parent_id=None):
        try:
            return self.db.get_constants(group_name, parent_id=parent_id)
        except Exception:
            return []

    def _update_marka(self):
        if not hasattr(self, "cmb_marka"):
            return
        kategori = (self.cmb_kategori.currentText() or "").strip() if hasattr(self, "cmb_kategori") else ""

        self.cmb_marka.blockSignals(True)
        self.cmb_marka.clear()
        self.cmb_marka.addItem("Seçiniz...")
        for _id, value in self._get_constants_values("arac_marka", parent_id=None):
            # Sabitler modülünde kategoriye göre parent kurulduysa burada parent_id geçilebilir.
            # Şimdilik tüm markaları listeler; sabitler hiyerarşisi kurulunca filtrelenecek.
            self.cmb_marka.addItem(value)
        self.cmb_marka.blockSignals(False)
        self._update_model()

    def _update_model(self):
        if not hasattr(self, "cmb_model"):
            return
        self.cmb_model.blockSignals(True)
        self.cmb_model.clear()
        self.cmb_model.addItem("Seçiniz...")
        for _id, value in self._get_constants_values("arac_model", parent_id=None):
            self.cmb_model.addItem(value)
        self.cmb_model.blockSignals(False)

    def load_data(self):
        if not hasattr(self, "tableView"):
            return

        headers = [
            "KOD",
            "ARAÇ TÜRÜ",
            "HİZMET TÜRÜ",
            "PLAKA",
            "ARAÇ SAHİBİ",
            "KATEGORİ",
            "MARKA",
            "MODEL",
            "YIL",
            "KAPASİTE",
            "DURUM",
        ]
        self.tableView.setColumnCount(len(headers))
        self.tableView.setHorizontalHeaderLabels(headers)
        self.tableView.verticalHeader().setDefaultSectionSize(20)
        self.tableView.verticalHeader().setVisible(False)
        header = self.tableView.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        query = """
            SELECT vehicle_code, arac_turu, hizmet_turu, plate_number, arac_sahibi, kategori, brand, model, yil, capacity, is_active
            FROM vehicles
            ORDER BY id ASC
        """
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()

            self.tableView.setRowCount(len(rows))
            for r, row in enumerate(rows):
                for c, value in enumerate(row):
                    if c == 10:
                        display = "AKTİF" if int(value or 0) == 1 else "PASİF"
                    else:
                        display = str(value) if value is not None else ""
                    item = QTableWidgetItem(display)
                    if c in [0, 1, 2, 8, 9, 10]:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if c == 10 and int(value or 0) == 0:
                        item.setForeground(Qt.GlobalColor.red)
                    self.tableView.setItem(r, c, item)
        except Exception as e:
            print(f"Araç yükleme hatası: {e}")

        self.apply_filters()

    def _setup_filters(self):
        required = ["cmb_arac_turu_f", "cmb_hizmet_turu_f", "cmb_marka_f", "txt_plaka_f"]
        for name in required:
            if not hasattr(self, name):
                return

        self.cmb_arac_turu_f.blockSignals(True)
        self.cmb_arac_turu_f.clear()
        self.cmb_arac_turu_f.addItem("Tümü")
        self.cmb_arac_turu_f.addItem("ŞİRKET ARACI")
        self.cmb_arac_turu_f.addItem("TAŞERON ARACI")
        self.cmb_arac_turu_f.blockSignals(False)

        self.cmb_hizmet_turu_f.blockSignals(True)
        self.cmb_hizmet_turu_f.clear()
        self.cmb_hizmet_turu_f.addItem("Tümü")
        self.cmb_hizmet_turu_f.addItem("SERVİS ARACI")
        self.cmb_hizmet_turu_f.addItem("HİZMET ARACI")
        self.cmb_hizmet_turu_f.blockSignals(False)

        self.cmb_marka_f.blockSignals(True)
        self.cmb_marka_f.clear()
        self.cmb_marka_f.addItem("Tümü")
        self.cmb_marka_f.blockSignals(False)

        self.txt_plaka_f.textChanged.connect(self.apply_filters)
        self.cmb_arac_turu_f.currentIndexChanged.connect(self.apply_filters)
        self.cmb_hizmet_turu_f.currentIndexChanged.connect(self.apply_filters)
        self.cmb_marka_f.currentIndexChanged.connect(self.apply_filters)
        if hasattr(self, "btn_temizle_f"):
            self.btn_temizle_f.clicked.connect(self.clear_filters)

    def clear_filters(self):
        if hasattr(self, "cmb_arac_turu_f"):
            self.cmb_arac_turu_f.setCurrentIndex(0)
        if hasattr(self, "cmb_hizmet_turu_f"):
            self.cmb_hizmet_turu_f.setCurrentIndex(0)
        if hasattr(self, "cmb_marka_f"):
            self.cmb_marka_f.setCurrentIndex(0)
        if hasattr(self, "txt_plaka_f"):
            self.txt_plaka_f.clear()
        self.apply_filters()

    def _normalize_combo_text(self, combo):
        if combo is None:
            return ""
        txt = (combo.currentText() or "").strip()
        if not txt or txt.lower() == "tümü" or txt.lower().startswith("seç"):
            return ""
        return txt

    def apply_filters(self):
        if not hasattr(self, "tableView"):
            return

        arac_turu = self._normalize_combo_text(getattr(self, "cmb_arac_turu_f", None))
        hizmet_turu = self._normalize_combo_text(getattr(self, "cmb_hizmet_turu_f", None))
        marka = self._normalize_combo_text(getattr(self, "cmb_marka_f", None))
        plaka_q = (self.txt_plaka_f.text() or "").strip().upper() if hasattr(self, "txt_plaka_f") else ""

        for row in range(self.tableView.rowCount()):
            row_arac_turu = (self.tableView.item(row, 1).text() if self.tableView.item(row, 1) else "").strip()
            row_hizmet = (self.tableView.item(row, 2).text() if self.tableView.item(row, 2) else "").strip()
            row_marka = (self.tableView.item(row, 6).text() if self.tableView.item(row, 6) else "").strip()
            row_plaka = (self.tableView.item(row, 3).text() if self.tableView.item(row, 3) else "").strip().upper()

            ok = True
            if arac_turu and row_arac_turu != arac_turu:
                ok = False
            if ok and hizmet_turu and row_hizmet != hizmet_turu:
                ok = False
            if ok and marka and row_marka != marka:
                ok = False
            if ok and plaka_q and plaka_q not in row_plaka:
                ok = False

            self.tableView.setRowHidden(row, not ok)

    def _get_selected_vehicle_code(self):
        if not hasattr(self, "tableView"):
            return ""
        items = self.tableView.selectedItems() if hasattr(self.tableView, "selectedItems") else []
        if not items:
            return ""
        row = items[0].row()
        item = self.tableView.item(row, 0)
        return item.text().strip() if item else ""

    def _get_date_str(self, name):
        w = getattr(self, name, None)
        if w is None:
            return ""
        return w.date().toString("yyyy-MM-dd")

    def _set_date(self, name, date_str):
        w = getattr(self, name, None)
        if w is None:
            return
        if not date_str:
            w.setDate(QDate.currentDate())
            return
        d = QDate.fromString(date_str, "yyyy-MM-dd")
        if not d.isValid():
            d = QDate.fromString(date_str, "dd.MM.yyyy")
        if d.isValid():
            w.setDate(d)

    def _collect_form_data(self):
        plate = _normalize_plate(self.txt_arac_plaka.text() if hasattr(self, "txt_arac_plaka") else "")
        yil = (self.txt_yil.text() or "").strip() if hasattr(self, "txt_yil") else ""
        kapasite = (self.txt_kapasite.text() or "").strip() if hasattr(self, "txt_kapasite") else ""
        arac_sahibi = (self.txt_arac_sahibi.text() or "").strip() if hasattr(self, "txt_arac_sahibi") else ""

        supplier_customer_id = None
        cmb_sup = getattr(self, "cmb_alt_yuklenici", None)
        if cmb_sup is not None:
            try:
                supplier_customer_id = cmb_sup.currentData()
            except Exception:
                supplier_customer_id = None

        def to_int(val):
            try:
                return int(val)
            except Exception:
                return None

        return {
            "vehicle_code": (self.txt_arac_kodu.text() or "").strip() if hasattr(self, "txt_arac_kodu") else "",
            "plate_number": plate,
            "arac_sahibi": arac_sahibi,
            "photo_path": (self._photo_path or "").strip(),
            "arac_turu": (self.cmb_arac_turu.currentText() or "").strip() if hasattr(self, "cmb_arac_turu") else "",
            "supplier_customer_id": (int(supplier_customer_id) if supplier_customer_id is not None else None),
            "hizmet_turu": (self.cmb_hizmet_turu.currentText() or "").strip() if hasattr(self, "cmb_hizmet_turu") else "",
            "kategori": (self.cmb_kategori.currentText() or "").strip() if hasattr(self, "cmb_kategori") else "",
            "brand": (self.cmb_marka.currentText() or "").strip() if hasattr(self, "cmb_marka") else "",
            "model": (self.cmb_model.currentText() or "").strip() if hasattr(self, "cmb_model") else "",
            "yil": to_int(yil) if yil else None,
            "capacity": to_int(kapasite) if kapasite else None,
            "muayene_tarihi": self._get_date_str("date_muayene"),
            "sigorta_tarihi": self._get_date_str("date_sigorta"),
            "koltuk_tarihi": self._get_date_str("date_koltuk"),
            "kasko_tarihi": self._get_date_str("date_kasko"),
            "calisma_ruhsati_tarihi": self._get_date_str("date_calisma_ruhsati"),
            "guzergah_izin_tarihi": self._get_date_str("date_guzergah_izin"),
            "arac_takip": 1 if (self.chk_arac_takip.isChecked() if hasattr(self, "chk_arac_takip") else False) else 0,
            "arac_cam": 1 if (self.chk_arac_cam.isChecked() if hasattr(self, "chk_arac_cam") else False) else 0,
        }

    def save(self):
        if not hasattr(self, "txt_arac_plaka"):
            return

        data = self._collect_form_data()
        if not data.get("vehicle_code"):
            self._assign_next_code()
            data["vehicle_code"] = (self.txt_arac_kodu.text() or "").strip()

        if not data.get("plate_number"):
            QMessageBox.warning(self, "Eksik Bilgi", "Plaka No boş bırakılamaz!")
            self.txt_arac_plaka.setFocus()
            return

        if self.db.check_vehicle_plate_exists(data["plate_number"], current_code=self.current_code):
            QMessageBox.warning(self, "Uyarı", "Bu plaka başka bir kayıtta kullanılıyor!")
            self.txt_arac_plaka.setFocus()
            return

        yil_text = (self.txt_yil.text() or "").strip() if hasattr(self, "txt_yil") else ""
        if yil_text and (not yil_text.isdigit() or len(yil_text) != 4):
            QMessageBox.warning(self, "Uyarı", "Yıl 4 haneli olmalıdır.")
            self.txt_yil.setFocus()
            return

        is_update = self.current_code is not None
        ok = self.db.save_vehicle(data, is_update=is_update)
        if ok:
            QMessageBox.information(self, "Başarılı", "İşlem başarıyla tamamlandı.")
            self.load_data()
            self.clear_form()
        else:
            QMessageBox.critical(self, "Hata", "Kayıt işlemi başarısız.")

    def clear_form(self):
        self.current_code = None
        self._photo_path = ""
        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.setText("Kaydet")

        if hasattr(self, "txt_arac_plaka"):
            self.txt_arac_plaka.clear()
        if hasattr(self, "txt_yil"):
            self.txt_yil.clear()
        if hasattr(self, "txt_kapasite"):
            self.txt_kapasite.clear()
        if hasattr(self, "txt_arac_sahibi"):
            self.txt_arac_sahibi.clear()

        if hasattr(self, "cmb_alt_yuklenici"):
            try:
                self.cmb_alt_yuklenici.setCurrentIndex(0)
            except Exception:
                pass

        if hasattr(self, "cmb_arac_turu"):
            self.cmb_arac_turu.setCurrentIndex(0)
        if hasattr(self, "cmb_hizmet_turu"):
            self.cmb_hizmet_turu.setCurrentIndex(0)
        self._update_kategori()
        if hasattr(self, "chk_arac_takip"):
            self.chk_arac_takip.setChecked(False)
        if hasattr(self, "chk_arac_cam"):
            self.chk_arac_cam.setChecked(False)
        self._init_dates()
        self._assign_next_code()
        if hasattr(self, "lbl_arac_foto"):
            self.lbl_arac_foto.setPixmap(QPixmap())
            self.lbl_arac_foto.setText("Araç Foto Yükle...")
        if hasattr(self, "txt_arac_plaka"):
            self.txt_arac_plaka.setFocus()

    def select_record(self, item):
        if item is None:
            return

        row = item.row()
        code_item = self.tableView.item(row, 0) if hasattr(self, "tableView") else None
        code = code_item.text().strip() if code_item else ""
        if not code:
            return
        data = self.db.get_vehicle_details_by_code(code)
        if not data:
            return
        self.current_code = code
        if hasattr(self, "txt_arac_kodu"):
            self.txt_arac_kodu.setText(code)
        if hasattr(self, "txt_arac_plaka"):
            self.txt_arac_plaka.setText(str(data.get("plate_number") or ""))

        if hasattr(self, "txt_arac_sahibi"):
            self.txt_arac_sahibi.setText(str(data.get("arac_sahibi") or ""))

        if hasattr(self, "cmb_alt_yuklenici"):
            try:
                sid = data.get("supplier_customer_id")
                if sid is None or str(sid).strip() == "":
                    self.cmb_alt_yuklenici.setCurrentIndex(0)
                else:
                    idx = self.cmb_alt_yuklenici.findData(int(sid))
                    self.cmb_alt_yuklenici.setCurrentIndex(idx if idx >= 0 else 0)
            except Exception:
                try:
                    self.cmb_alt_yuklenici.setCurrentIndex(0)
                except Exception:
                    pass

        self._photo_path = str(data.get("photo_path") or "").strip()
        self._refresh_photo_label()

        def set_combo(combo, text):
            if combo is None:
                return
            text = (text or "").strip()
            if not text:
                combo.setCurrentIndex(0)
                return
            idx = combo.findText(text, Qt.MatchFlag.MatchFixedString)
            combo.setCurrentIndex(idx if idx >= 0 else 0)

        if hasattr(self, "cmb_arac_turu"):
            set_combo(self.cmb_arac_turu, data.get("arac_turu"))
        if hasattr(self, "cmb_hizmet_turu"):
            set_combo(self.cmb_hizmet_turu, data.get("hizmet_turu"))
            self._update_kategori()
        if hasattr(self, "cmb_kategori"):
            set_combo(self.cmb_kategori, data.get("kategori"))
            self._update_marka()
        if hasattr(self, "cmb_marka"):
            set_combo(self.cmb_marka, data.get("brand"))
            self._update_model()
        if hasattr(self, "cmb_model"):
            set_combo(self.cmb_model, data.get("model"))

        if hasattr(self, "txt_yil"):
            self.txt_yil.setText(str(data.get("yil") or ""))
        if hasattr(self, "txt_kapasite"):
            self.txt_kapasite.setText(str(data.get("capacity") or ""))

        self._set_date("date_muayene", data.get("muayene_tarihi"))
        self._set_date("date_sigorta", data.get("sigorta_tarihi"))
        self._set_date("date_koltuk", data.get("koltuk_tarihi"))
        self._set_date("date_kasko", data.get("kasko_tarihi"))
        self._set_date("date_calisma_ruhsati", data.get("calisma_ruhsati_tarihi"))
        self._set_date("date_guzergah_izin", data.get("guzergah_izin_tarihi"))

        if hasattr(self, "chk_arac_takip"):
            self.chk_arac_takip.setChecked(int(data.get("arac_takip") or 0) == 1)
        if hasattr(self, "chk_arac_cam"):
            self.chk_arac_cam.setChecked(int(data.get("arac_cam") or 0) == 1)

        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.setText("Güncelle")

    def _on_photo_label_clicked(self, event):
        # Foto seçimi: label tıklanınca dosya seçtir
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Araç Fotoğrafı Seç",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not file_path:
            return

        self._photo_path = file_path
        self._refresh_photo_label()

    def _refresh_photo_label(self):
        if not hasattr(self, "lbl_arac_foto"):
            return
        if not self._photo_path or not os.path.exists(self._photo_path):
            self.lbl_arac_foto.setPixmap(QPixmap())
            self.lbl_arac_foto.setText("Araç Foto Yükle...")
            return

        pix = QPixmap(self._photo_path)
        if pix.isNull():
            self.lbl_arac_foto.setPixmap(QPixmap())
            self.lbl_arac_foto.setText("Araç Foto Yükle...")
            return

        self.lbl_arac_foto.setText("")
        self.lbl_arac_foto.setPixmap(
            pix.scaled(
                self.lbl_arac_foto.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def toggle_active_selected(self):
        code = self._get_selected_vehicle_code()
        if not code:
            QMessageBox.warning(self, "Uyarı", "Lütfen tablodan bir araç seçin.")
        if not self.db.toggle_vehicle_active_status(code):
            QMessageBox.critical(self, "Hata", "Aktif/Pasif durumu güncellenemedi.")
            return
        self.load_data()

    def delete_selected(self):
        role = (self.user_data or {}).get("role") if isinstance(self.user_data, dict) else None
        if role != "admin":
            QMessageBox.warning(self, "Yetki Yok", "Bu işlemi yapmak için admin yetkisi gereklidir.")
            return
        code = self._get_selected_vehicle_code()
        if not code:
            QMessageBox.warning(self, "Uyarı", "Lütfen tablodan bir araç seçin.")
            return
        soru = QMessageBox.question(
            self,
            "Onay",
            f"{code} kodlu araç silinsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if soru != QMessageBox.StandardButton.Yes:
            return
        if not self.db.delete_vehicle_by_code(code):
            QMessageBox.critical(self, "Hata", "Silme işlemi başarısız.")
            return
        self.load_data()
        self.clear_form()

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
        create_pdf(export_table, report_title="Araç Listesi", username="Admin", parent=self)

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
        create_excel(export_table, report_title="Araç Listesi", username="Admin", parent=self)