from PyQt6.QtWidgets import QWidget, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy, QLineEdit, QComboBox, QLayout, QFileDialog
from PyQt6.QtCore import Qt, QRegularExpression, QSize
from PyQt6 import uic
from PyQt6.QtGui import QIntValidator, QRegularExpressionValidator, QPixmap
from app.core.db_manager import DatabaseManager
import ui.icons.resource_rc

from config import get_ui_path, BASE_DIR
import os
import re
import shutil

def tr_upper(text):
    """Türkçe karakterleri (i-İ, ı-I) doğru şekilde büyük harfe çevirir."""
    text = text.replace('i', 'İ').replace('ı', 'I')
    return text.upper()

class EmployeesApp(QWidget):

    def __init__(self, user_data=None, parent=None): # Ebeveyn kuralı gereği parent=None ekledik
        super().__init__(parent)
        uic.loadUi(get_ui_path("personel.ui"), self)
        self._relax_ui_constraints()
        self.db = DatabaseManager()

        self.user_data = user_data

        self.photo_path = ""
        self._loaded_tckn = ""
        if hasattr(self, "lbl_photo"):
            self.lbl_photo.setCursor(Qt.CursorShape.PointingHandCursor)
            self.lbl_photo.mousePressEvent = self._on_photo_clicked

        self.txt_tckn.setValidator(QRegularExpressionValidator(QRegularExpression(r"^\d{11}$")))
        self.txt_tckn.setMaxLength(11)
        email_regex = QRegularExpression(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}")
        self.txt_email.setValidator(QRegularExpressionValidator(QRegularExpression(r"[a-zA-Z0-9@._-]+")))
        self.txt_email.textChanged.connect(lambda text: self.txt_email.setText(text.lower()))
        # NOT: txt_iban alanında inputMask varsa (örn. TR ile başlayan veya boşluk içeren),
        # sadece rakam validator'ı tüm girişi bloke edebilir. Bu yüzden validator kullanmıyoruz.
        # Bu harita, Ayşe Teyze'nin misafirlerini doğru koltuklara oturtur
        self.fields = {
            "txt_ad_soyad": "ad_soyad",
            "txt_tckn": "tckn",
            "txt_gsm": "gsm",
            "txt_email": "email",
            "txt_anne_adi": "anne_adi",
            "txt_baba_adi": "baba_adi",
            "txt_dogum_yeri": "dogum_yeri",
            "txt_adres1": "adres1",
            "txt_adres2": "adres2",
            "txt_iban": "iban",
            "txt_notlar1": "notlar1",
            "txt_notlar2": "notlar2",
            "cmb_kan_grubu": "kan_grubu",
            "cmb_personel_turu": "personel_turu",
            "cmb_gorevi": "gorevi",
            "cmb_il": "il",
            "cmb_ilce": "ilce",
            "cmb_banka_adi": "banka_adi"
        }
        self.current_kodu = None
        for field_name in self.fields.keys():
            widget = getattr(self, field_name)
            if isinstance(widget, QLineEdit):
                # Eğer bu input 'zorunluluktan dolayı hariç' (örneğin email veya şifre) değilse:
                # Ayrıca inputMask kullanılan alanlarda (gsm/iban gibi) setText ile imleç sona atlamasın.
                if (
                    "email" not in field_name.lower()
                    and "password" not in field_name.lower()
                    and "gsm" not in field_name.lower()
                    and "iban" not in field_name.lower()
                ):
                    widget.textChanged.connect(lambda text, w=widget: w.setText(tr_upper(text)))
        self.btn_kaydet.clicked.connect(self.save) # İşte eksik olan parça!
        self.btn_yeni.clicked.connect(self.clear_form)
        # self.btn_sil.clicked.connect(self.delete)

        if hasattr(self, "btn_pdfye_aktar"):
            self.btn_pdfye_aktar.clicked.connect(self.export_pdf)
        if hasattr(self, "btn_excele_aktar"):
            self.btn_excele_aktar.clicked.connect(self.export_excel)
        if hasattr(self, "btn_aktifpasif"):
            self.btn_aktifpasif.clicked.connect(self.toggle_active_selected)
        if hasattr(self, "btn_sil"):
            self.btn_sil.clicked.connect(self.delete_selected)
        self.tableView.doubleClicked.connect(self.select_record)
        
        self.txt_personel_kodu.setReadOnly(True) # Sadece okunabilir
        self.txt_personel_kodu.setFocusPolicy(Qt.FocusPolicy.NoFocus) # Tab ile bile girilemez
        self.txt_personel_kodu.setStyleSheet("background: transparent; border: none; font-family: Minalis Demo; font-size: 12pt; font-weight: bold; color: #ffff7f;")
        self.get_next_personel_kod()
        
        self.fill_combos()
        self.load_data()
        self._setup_filters()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _on_photo_clicked(self, event):
        if event is not None and hasattr(event, "button") and event.button() != Qt.MouseButton.LeftButton:
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Personel Fotoğrafı Seç",
            "",
            "Resimler (*.png *.jpg *.jpeg *.bmp *.webp);;Tüm Dosyalar (*)",
        )
        if not file_path:
            return

        stored_path = self._store_employee_photo(file_path)
        if not stored_path:
            return

        self.photo_path = stored_path
        self._set_photo_preview(self._resolve_photo_path(stored_path))

    def _resolve_photo_path(self, stored_path: str) -> str:
        if not stored_path:
            return ""
        if os.path.isabs(stored_path):
            return stored_path
        return os.path.normpath(os.path.join(BASE_DIR, stored_path))

    def _store_employee_photo(self, src_path: str) -> str:
        if not src_path:
            return ""

        try:
            if not os.path.exists(src_path):
                QMessageBox.warning(self, "Hata", "Seçilen fotoğraf dosyası bulunamadı.")
                return ""

            abs_src = os.path.abspath(src_path)
            assets_photos_dir = os.path.join(BASE_DIR, "assets", "photos")
            os.makedirs(assets_photos_dir, exist_ok=True)

            abs_assets_photos_dir = os.path.abspath(assets_photos_dir)
            try:
                in_assets = os.path.commonpath([abs_src, abs_assets_photos_dir]) == abs_assets_photos_dir
            except ValueError:
                in_assets = False

            if in_assets:
                rel_existing = os.path.relpath(abs_src, BASE_DIR)
                return rel_existing.replace("\\", "/")

            ext = os.path.splitext(src_path)[1] or ".jpg"
            kodu = (self.current_kodu or "").strip() or (self.txt_personel_kodu.text().strip() if hasattr(self, "txt_personel_kodu") else "")
            base_name = re.sub(r"[^A-Za-z0-9_-]", "_", kodu) if kodu else "employee"

            file_name = f"{base_name}{ext.lower()}"
            dest_path = os.path.join(assets_photos_dir, file_name)

            i = 1
            while os.path.exists(dest_path):
                file_name = f"{base_name}_{i}{ext.lower()}"
                dest_path = os.path.join(assets_photos_dir, file_name)
                i += 1

            shutil.copy2(src_path, dest_path)
            rel_path = os.path.relpath(dest_path, BASE_DIR)
            return rel_path.replace("\\", "/")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Fotoğraf kaydedilirken hata oluştu:\n{str(e)}")
            return ""

    def _set_photo_preview(self, file_path: str):
        if not hasattr(self, "lbl_photo"):
            return

        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            return

        target_size = self.lbl_photo.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            target_size = QSize(150, 200)

        scaled = pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        self.lbl_photo.setStyleSheet("")
        self.lbl_photo.setPixmap(scaled)
        self.lbl_photo.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def _relax_ui_constraints(self):
        layout = self.layout()
        if layout is not None:
            layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

        for w in self.findChildren(QWidget):
            try:
                if getattr(w, "objectName", None) and w.objectName() == "lbl_photo":
                    w.setMinimumWidth(150)
                    w.setMaximumWidth(150)
                    continue

                min_w = w.minimumWidth()
                max_w = w.maximumWidth()
                if min_w > 0 and max_w == min_w and max_w < 16777215:
                    w.setMaximumWidth(16777215)
                    sp = w.sizePolicy()
                    sp.setHorizontalPolicy(QSizePolicy.Policy.Preferred)
                    w.setSizePolicy(sp)

                # Çok sayıda widget'ın minimumWidth değeri birikince formun minimumSizeHint'i şişiyor.
                # Bu da ana pencereyi 1366px ekranda 1426px gibi minimuma zorlayıp taşma yaratıyor.
                # Burada minimumWidth kısıtlarını gevşetiyoruz.
                if w.minimumWidth() > 0:
                    w.setMinimumWidth(0)
                if w.minimumHeight() > 0:
                    w.setMinimumHeight(0)

                sp2 = w.sizePolicy()
                if sp2.horizontalPolicy() in (QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum):
                    sp2.setHorizontalPolicy(QSizePolicy.Policy.Preferred)
                    w.setSizePolicy(sp2)
            except Exception:
                continue

    def minimumSizeHint(self):
        return QSize(0, 0)

    def sizeHint(self):
        return QSize(0, 0)

    def load_data(self):
        """Tabloyu kurumsal renklere boyar, sütun genişliklerini sabitler ve verileri yükler"""
        # 1. Başlık ve Temel Ayarlar
        headers = ["KOD", "TÜR", "TCKN", "ADI SOYADI", "GÖREVİ", "TELEFON", "e-POSTA", "KAN GR.", "DURUMU"]
        
        self.tableView.setColumnCount(len(headers))
        self.tableView.setHorizontalHeaderLabels(headers)
        
        # Sol taraftaki sıra numaralarını (1, 2, 3...) gizle
        self.tableView.verticalHeader().setVisible(False)
        
        # 2. Kurumsal Header Tasarımı (#162D6D Arkaplan, Beyaz Bold Metin)
        header_style = """
            QHeaderView::section {
                background-color: #162D6D;
                color: white;
                font-weight: bold;
                padding: 4px;
                border: 1px solid #0D1C44;
            }
        """
        self.tableView.horizontalHeader().setStyleSheet(header_style)
        
        # 3. Senin Belirlediğin Milimetrik Sütun Genişlikleri
        header = self.tableView.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive) # Elle müdahaleye açık
        # Zebra Stil (Ardışık satır renkleri)
        self.tableView.setAlternatingRowColors(True)
        self.tableView.setStyleSheet("""
            QTableView {
                                    
                alternate-background-color: #C2C2C2; /* Açık gri zebra rengi */
                background-color: white;
                selection-background-color: #a4e4ff; /* Seçilen satır lacivert */
                selection-color: white;
                gridline-color: #000000; /* Hücre çizgileri hafifletildi */
                
            }
        """)

        # Header Tasarımı (Beyaz/Hafif Gri Border ve Radius)
        header_style = """
            QHeaderView::section {
                background-color: #162D6D;
                color: white;
                font-weight: bold;
                padding: 4px;
                border: 1px solid #ffffff; /* Beyaz ince border */
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                border-bottom-left-radius: 4px;
            }
        """
        self.tableView.horizontalHeader().setStyleSheet(header_style)
        
        # --- GÜNCEL GENİŞLİKLER (İsteğine göre revize edildi) ---
        header = self.tableView.horizontalHeader()
        # TCKN 100->90'a düştü, Kan Grubu 60->70'e çıktı (+10 fazlalık eklendi)
        widths = {0: 80, 1: 120, 2: 90, 4: 100, 5: 110, 7: 70, 8: 60}
        for col, width in widths.items():
            header.resizeSection(col, width)
            
        # Ad Soyad (3) ve E-Mail (6) kalan alanı kaplasın (E-Mail daha fazla alabilir)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)

        # 4. Verileri Çek ve Yerleştir
        query = """
            SELECT personel_kodu, personel_turu, tckn, ad_soyad, gorevi, gsm, email, kan_grubu, is_active 
            FROM employees ORDER BY rowid ASC
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
                    # Aktif/Pasif metin dönüşümü
                    if col_idx == 8:
                        display_text = "AKTİF" if value == 1 else "PASİF"
                    elif col_idx == 5:
                        # GSM her zaman maskeli görünsün (DB'de rakam da olsa maskeye çevir)
                        display_text = self._format_gsm(str(value) if value else "")
                    else:
                        display_text = str(value) if value else ""
                    
                    item = QTableWidgetItem(display_text)
                    
                    # Hücre içindeki yazıyı ortala (Kan grubu ve Durum için iyi olur)
                    if col_idx in [0, 7, 8]:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        
                    # Pasif personelleri belirtmek için kırmızı font
                    if col_idx == 8 and value == 0:
                        item.setForeground(Qt.GlobalColor.red)
                        
                    self.tableView.setItem(row_idx, col_idx, item)
                    
        except Exception as e:
            print(f"Yükleme Hatası: {e}")

        self.tableView.verticalHeader().setDefaultSectionSize(20) # Satır yüksekliğini 25px yapar
        self.tableView.verticalHeader().setVisible(False) # En soldaki numara sütununu gizler (opsiyonel)

        # Tablo yeniden dolduktan sonra filtre aktifse tekrar uygula
        if hasattr(self, "apply_filters"):
            self.apply_filters()

    def fill_combos(self):
        """Sabitler tablosundaki verileri ComboBox nesnelerine profesyonelce doldurur."""
        # Gruplar (db) ve senin personel.ui dosyasındaki ComboBox isimlerin
        combo_map = {
            "personel_turu": self.cmb_personel_turu,
            "gorev": self.cmb_gorevi,
            "banka": self.cmb_banka_adi,
            "kan_grubu": self.cmb_kan_grubu,
            "il": self.cmb_il
        }

        for group_name, combo_obj in combo_map.items():
            combo_obj.clear()
            # Veritabanından (constants tablosundan) veriyi çekiyoruz
            data = self.db.get_constants(group_name) 
            
            # Boş bir seçenek ekleyelim ki kullanıcı seçmeye zorlansın
            combo_obj.addItem("Seçiniz...", None)
            
            for id_val, value in data:
                # addItem(GörünenMetin, ArkaPlandakiVeri) -> id_val çok kritik!
                combo_obj.addItem(value, id_val)

        # İL seçilince İLÇE kutusunu tetikleyecek sinyali bağlıyoruz
        self.cmb_il.currentIndexChanged.connect(self.fill_districts)

    def fill_districts(self):
        """Seçili ile göre ilçeleri filtreler"""
        self.cmb_ilce.clear()
        
        # Seçili olan ilin ID'sini (arka plandaki verisini) alıyoruz
        il_id = self.cmb_il.currentData()
        
        if il_id:
            # Sadece bu il_id'sine bağlı ilçeleri çekiyoruz
            districts = self.db.get_constants("ilce", parent_id=il_id) 
            self.cmb_ilce.addItem("Seçiniz...", None)
            for d_id, d_val in districts:
                self.cmb_ilce.addItem(d_val, d_id)

    def _setup_filters(self):
        required = [
            "cmb_personel_turu_f",
            "cmb_durum_f",
            "cmb_gorevi_f",
            "txt_ad_soyad_f",
            "txt_tckn_f",
        ]
        for name in required:
            if not hasattr(self, name):
                return

        self.cmb_personel_turu_f.setEnabled(True)
        self.cmb_durum_f.setEnabled(True)
        self.cmb_gorevi_f.setEnabled(True)
        self.txt_ad_soyad_f.setEnabled(True)
        self.txt_tckn_f.setEnabled(True)

        self.txt_ad_soyad_f.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.txt_tckn_f.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # TCKN filtre kutusu sadece rakam alsın ama kısmi girişe izin versin
        self.txt_tckn_f.setValidator(QRegularExpressionValidator(QRegularExpression(r"^\d*$")))
        self.txt_tckn_f.setMaxLength(11)

        self._fill_filter_combos()

        # Live filtreleme: yazdıkça / seçtikçe
        self.txt_ad_soyad_f.textChanged.connect(self.apply_filters)
        self.txt_tckn_f.textChanged.connect(self.apply_filters)
        self.cmb_personel_turu_f.currentIndexChanged.connect(self.apply_filters)
        self.cmb_durum_f.currentIndexChanged.connect(self.apply_filters)
        self.cmb_gorevi_f.currentIndexChanged.connect(self.apply_filters)

        if hasattr(self, "btn_temizle_f"):
            self.btn_temizle_f.clicked.connect(self.clear_filters)

    def _fill_filter_combos(self):
        # Personel Türü
        self.cmb_personel_turu_f.blockSignals(True)
        self.cmb_personel_turu_f.clear()
        self.cmb_personel_turu_f.addItem("Tümü")
        if hasattr(self, "cmb_personel_turu"):
            for i in range(self.cmb_personel_turu.count()):
                txt = (self.cmb_personel_turu.itemText(i) or "").strip()
                if not txt or txt.lower().startswith("seç"):
                    continue
                if self.cmb_personel_turu_f.findText(txt, Qt.MatchFlag.MatchFixedString) < 0:
                    self.cmb_personel_turu_f.addItem(txt)
        self.cmb_personel_turu_f.blockSignals(False)

        # Görevi
        self.cmb_gorevi_f.blockSignals(True)
        self.cmb_gorevi_f.clear()
        self.cmb_gorevi_f.addItem("Tümü")
        if hasattr(self, "cmb_gorevi"):
            for i in range(self.cmb_gorevi.count()):
                txt = (self.cmb_gorevi.itemText(i) or "").strip()
                if not txt or txt.lower().startswith("seç"):
                    continue
                if self.cmb_gorevi_f.findText(txt, Qt.MatchFlag.MatchFixedString) < 0:
                    self.cmb_gorevi_f.addItem(txt)
        self.cmb_gorevi_f.blockSignals(False)

        # Durum
        self.cmb_durum_f.blockSignals(True)
        self.cmb_durum_f.clear()
        self.cmb_durum_f.addItem("Tümü")
        self.cmb_durum_f.addItem("AKTİF")
        self.cmb_durum_f.addItem("PASİF")
        self.cmb_durum_f.blockSignals(False)

    def clear_filters(self):
        if hasattr(self, "txt_ad_soyad_f"):
            self.txt_ad_soyad_f.clear()
        if hasattr(self, "txt_tckn_f"):
            self.txt_tckn_f.clear()
        if hasattr(self, "cmb_personel_turu_f"):
            self.cmb_personel_turu_f.setCurrentIndex(0)
        if hasattr(self, "cmb_gorevi_f"):
            self.cmb_gorevi_f.setCurrentIndex(0)
        if hasattr(self, "cmb_durum_f"):
            self.cmb_durum_f.setCurrentIndex(0)
        self.apply_filters()

    def apply_filters(self):
        if not hasattr(self, "tableView") or not hasattr(self.tableView, "rowCount"):
            return

        personel_turu = (self.cmb_personel_turu_f.currentText() or "").strip() if hasattr(self, "cmb_personel_turu_f") else ""
        gorevi = (self.cmb_gorevi_f.currentText() or "").strip() if hasattr(self, "cmb_gorevi_f") else ""
        durum = (self.cmb_durum_f.currentText() or "").strip() if hasattr(self, "cmb_durum_f") else ""
        ad_soyad_q = (self.txt_ad_soyad_f.text() or "").strip().lower() if hasattr(self, "txt_ad_soyad_f") else ""
        tckn_q = (self.txt_tckn_f.text() or "").strip() if hasattr(self, "txt_tckn_f") else ""

        for row in range(self.tableView.rowCount()):
            tur = (self.tableView.item(row, 1).text() if self.tableView.item(row, 1) else "").strip()
            tckn = (self.tableView.item(row, 2).text() if self.tableView.item(row, 2) else "").strip()
            ad_soyad = (self.tableView.item(row, 3).text() if self.tableView.item(row, 3) else "").strip().lower()
            gorev = (self.tableView.item(row, 4).text() if self.tableView.item(row, 4) else "").strip()
            row_durum = (self.tableView.item(row, 8).text() if self.tableView.item(row, 8) else "").strip()

            ok = True
            if personel_turu and personel_turu != "Tümü" and tur != personel_turu:
                ok = False
            if ok and gorevi and gorevi != "Tümü" and gorev != gorevi:
                ok = False
            if ok and durum and durum != "Tümü" and row_durum != durum:
                ok = False
            if ok and ad_soyad_q and ad_soyad_q not in ad_soyad:
                ok = False
            if ok and tckn_q and tckn_q not in tckn:
                ok = False

            self.tableView.setRowHidden(row, not ok)

    def is_valid_tckn(self, tckn):
        """TC Kimlik Numarası algoritma kontrolü yapar"""
        if len(tckn) != 11 or not tckn.isdigit() or tckn[0] == '0':
            return False
        
        digits = [int(d) for d in tckn]
        
        # 1. Kural: 1, 3, 5, 7, 9. hanelerin toplamının 7 katından, 
        # 2, 4, 6, 8. hanelerin toplamı çıkartıldığında, 
        # sonucun 10'a bölümünden kalan 10. haneyi vermelidir.
        sum_odd = sum(digits[0:9:2])
        sum_even = sum(digits[1:8:2])
        if (sum_odd * 7 - sum_even) % 10 != digits[9]:
            return False
        
        # 2. Kural: İlk 10 hanenin toplamının 10'a bölümünden kalan 11. haneyi vermelidir.
        if sum(digits[0:10]) % 10 != digits[10]:
            return False
        
        return True

    def is_valid_email(self, email):
        """Email formatının doğruluğunu kontrol eder"""
        pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        import re
        return re.match(pattern, email) is not None
    
    def _only_digits(self, value: str) -> str:
        return re.sub(r"\D", "", value or "")

    def _format_gsm(self, value: str) -> str:
        digits = self._only_digits(value)
        if len(digits) != 10:
            return value or ""
        return f"({digits[0:3]}) {digits[3:6]} {digits[6:8]} {digits[8:10]}"

    def export_pdf(self):
        try:
            from app.utils.pdf_utils import create_pdf
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"PDF modülü yüklenemedi:\n{str(e)}")
            return

        if not hasattr(self, "tableView") or not hasattr(self.tableView, "rowCount"):
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

        create_pdf(export_table, report_title="Personel Listesi", username="Admin", parent=self)

    def export_excel(self):
        try:
            from app.utils.excel_utils import create_excel
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Excel modülü yüklenemedi:\n{str(e)}")
            return

        if not hasattr(self, "tableView") or not hasattr(self.tableView, "rowCount"):
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

        create_excel(export_table, report_title="Personel Listesi", username="Admin", parent=self)

    def _get_selected_personel_kodu(self):
        if not hasattr(self, "tableView"):
            return ""
        selected_items = self.tableView.selectedItems() if hasattr(self.tableView, "selectedItems") else []
        if not selected_items:
            return ""
        row = selected_items[0].row()
        item = self.tableView.item(row, 0) if hasattr(self.tableView, "item") else None
        return (item.text().strip() if item else "")

    def toggle_active_selected(self):
        kodu = self._get_selected_personel_kodu()
        if not kodu:
            QMessageBox.warning(self, "Uyarı", "Lütfen tablodan bir personel seçin.")
            return

        ok = self.db.toggle_employee_active_status(kodu)
        if not ok:
            QMessageBox.critical(self, "Hata", "Aktif/Pasif durumu güncellenemedi.")
            return

        self.load_data()

    def delete_selected(self):
        role = (self.user_data or {}).get("role") if isinstance(self.user_data, dict) else None
        if role != "admin":
            QMessageBox.warning(self, "Yetki Yok", "Bu işlemi yapmak için admin yetkisi gereklidir.")
            return

        kodu = self._get_selected_personel_kodu()
        if not kodu:
            QMessageBox.warning(self, "Uyarı", "Lütfen tablodan bir personel seçin.")
            return

        soru = QMessageBox.question(
            self,
            "Onay",
            f"{kodu} kodlu personel silinsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if soru != QMessageBox.StandardButton.Yes:
            return

        if not self.db.delete_employee(kodu):
            QMessageBox.critical(self, "Hata", "Silme işlemi başarısız.")
            return

        self.load_data()
        if hasattr(self, "clear_form"):
            self.clear_form()

    def save(self):
        # 0. Stil Temizliği: Önce tüm kutuların rengini normale döndür
        for ui_obj in self.fields.keys():
            getattr(self, ui_obj).setStyleSheet("")

        # 1. Değerleri al
        ad_soyad = self.txt_ad_soyad.text().strip()
        tckn = self.txt_tckn.text().strip()
        gsm_digits = self._only_digits(self.txt_gsm.text())
        gsm_masked = self._format_gsm(self.txt_gsm.text().strip())
        email = self.txt_email.text().strip()
        iban_digits = self._only_digits(self.txt_iban.text())

        # 2. Zorunlu Alan Kontrolü
        if not ad_soyad or not tckn:
            QMessageBox.warning(self, "Eksik Bilgi", "Ad Soyad ve TCKN alanları boş bırakılamaz!")
            if not ad_soyad: 
                self.txt_ad_soyad.setFocus()
                self.txt_ad_soyad.setStyleSheet("background-color: #ffcccc;")
            else: 
                self.txt_tckn.setFocus()
                self.txt_tckn.setStyleSheet("background-color: #ffcccc;")
            return

        # 3. TCKN Algoritma Doğruluğu
        if not self.is_valid_tckn(tckn):
            QMessageBox.warning(self, "TCKN Hatası", "Girdiğiniz TC Kimlik Numarası geçersizdir!")
            self.txt_tckn.clear()
            self.txt_tckn.setFocus()
            self.txt_tckn.setStyleSheet("background-color: #ffcccc;")
            return

        # 4. Email Format Kontrolü (Sadece doluysa)
        if email and not self.is_valid_email(email):
            QMessageBox.warning(self, "Email Hatası", "Lütfen geçerli bir e-posta adresi giriniz!")
            self.txt_email.clear()
            self.txt_email.setFocus()
            self.txt_email.setStyleSheet("background-color: #ffcccc;")
            return

        # 5. Veritabanı Mükerrer TCKN Kontrolü
        is_update = self.current_kodu is not None
        same_tckn_as_loaded = bool(is_update and (self._loaded_tckn or "").strip() == (tckn or "").strip())
        if (not same_tckn_as_loaded) and self.db.check_tckn_exists(tckn, self.current_kodu):
            QMessageBox.warning(self, "Hata", "Bu TCKN başka bir personelde kayıtlı!")
            self.txt_tckn.clear()
            self.txt_tckn.setFocus()
            self.txt_tckn.setStyleSheet("background-color: #ffcccc;")
            return

        # 6. Veritabanı Mükerrer IBAN Kontrolü
        if iban_digits and self.db.check_iban_exists(iban_digits, self.current_kodu):
            QMessageBox.warning(self, "Hata", "Bu IBAN başka bir personelde kayıtlı!")
            self.txt_iban.clear()
            self.txt_iban.setFocus()
            self.txt_iban.setStyleSheet("background-color: #ffcccc;")
            return

        # 6.1 GSM / IBAN Uzunluk Kontrolü (Maskeli input -> sadece rakam sayılır)
        if gsm_digits and len(gsm_digits) != 10:
            QMessageBox.warning(self, "GSM Hatası", "Telefon numarası 10 haneli olmalıdır!")
            self.txt_gsm.setFocus()
            self.txt_gsm.setStyleSheet("background-color: #ffcccc;")
            return

        if iban_digits and len(iban_digits) != 24:
            QMessageBox.warning(self, "IBAN Hatası", "IBAN (TR hariç) 24 haneli olmalıdır!")
            self.txt_iban.setFocus()
            self.txt_iban.setStyleSheet("background-color: #ffcccc;")
            return

        # --- Her şey tamamsa kayıt başlasın ---
        
        # 7. Formdaki verileri topla
        data = {}
        for ui_obj, db_col in self.fields.items():
            widget = getattr(self, ui_obj)
            if isinstance(widget, QLineEdit):
                # Email ise küçük harf yap, değilse trimle
                if "email" in ui_obj.lower():
                    data[db_col] = widget.text().strip().lower()
                elif "gsm" in ui_obj.lower():
                    data[db_col] = gsm_masked
                elif "iban" in ui_obj.lower():
                    data[db_col] = iban_digits
                else:
                    data[db_col] = widget.text().strip()
            elif isinstance(widget, QComboBox):
                # DB kolonları TEXT olduğu için görünen metni kaydediyoruz
                data[db_col] = widget.currentText().strip() if widget.currentIndex() > 0 else ""
        
        # 8. Özel alanları ekle
        data['personel_kodu'] = self.txt_personel_kodu.text()
        data['dogum_tarihi'] = self.date_dogum_tarihi.date().toString("dd.MM.yyyy")
        data['photo_path'] = self.photo_path

        # 9. Veritabanına kaydet (Update/Insert kararını otomatik verir)
        if self.db.save_employee(data, is_update=is_update):
            QMessageBox.information(self, "Başarılı", "İşlem başarıyla tamamlandı.")
            self.load_data()
            self.clear_form()
            
    def clear_form(self):
        """Formu temizler ve sistemi YENİ KAYIT moduna hazırlar"""
        # 1. Değişkenleri sıfırla
        self.current_kodu = None
        self._loaded_tckn = ""
        
        # 2. Butonu eski haline getir
        self.btn_kaydet.setText("KAYDET")
        self.btn_kaydet.setStyleSheet("") # Varsa eski stilini ver
        
        # 3. Haritadaki tüm inputları temizle
        for ui_obj in self.fields.keys():
            widget = getattr(self, ui_obj)
            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(0)

        # Fotoğrafı sıfırla
        self.photo_path = ""
        if hasattr(self, "lbl_photo"):
            self.lbl_photo.setPixmap(QPixmap(":/resim/Photo.png"))
            self.lbl_photo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 4. KRİTİK NOKTA: Sıradaki Yeni Kodu Al
        self.get_next_personel_kod() 
        
        # 5. Focus ayarla
        self.txt_ad_soyad.setFocus()
            
    def get_next_personel_kod(self):
        """Eski kayıtları kontrol eder ve PER0001 formatında havada asılı kodu üretir"""
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute("SELECT personel_kodu FROM employees ORDER BY rowid DESC LIMIT 1")
            result = cursor.fetchone()
            conn.close()

            if result and result[0]:
                numbers = re.findall(r"\d+", result[0])
                current_num = int(numbers[0]) if numbers else 0
                next_code = f"PER{(current_num + 1):04d}"
            else:
                next_code = "PER0001"

            self.txt_personel_kodu.setText(next_code)
        except Exception as e:
            print(f"Kod üretim hatası: {e}")
            self.txt_personel_kodu.setText("PER0001")

    def select_record(self, item):
        """Tablodan seçilen personelin bilgilerini Ayşe Teyze'nin salonuna doldurur"""
        row = item.row()
        p_kodu = ""

        # tableView bir QTableWidget ise item(row,col) çalışır
        if hasattr(self.tableView, "item") and callable(getattr(self.tableView, "item")):
            first_item = self.tableView.item(row, 0)
            p_kodu = first_item.text().strip() if first_item else ""
        else:
            # tableView bir QTableView ise model üzerinden data al
            model = self.tableView.model()
            if model is not None:
                idx = model.index(row, 0)
                p_kodu = (idx.data() or "").strip()

        if not p_kodu:
            return

        personel = self.db.get_employee_details(p_kodu)
        if not personel:
            return

        self.current_kodu = p_kodu
        self._loaded_tckn = str(personel.get("tckn") or "").strip()

        # Widget -> DB kolon haritası üzerinden doldur
        for ui_obj, db_col in self.fields.items():
            if ui_obj == "txt_personel_kodu":
                continue
            if not hasattr(self, ui_obj):
                continue
            widget = getattr(self, ui_obj)
            val = personel.get(db_col, "")
            if isinstance(widget, QLineEdit):
                if "gsm" in ui_obj.lower():
                    widget.setText(self._only_digits(str(val)))
                elif "iban" in ui_obj.lower():
                    iban_db = self._only_digits(str(val))
                    widget.setText(f"TR{iban_db}" if iban_db else "")
                else:
                    widget.setText(str(val) if val is not None else "")
            elif isinstance(widget, QComboBox):
                widget.setCurrentText(str(val) if val is not None else "")

        self.txt_personel_kodu.setText(str(personel.get("personel_kodu", "")))

        from PyQt6.QtCore import QDate
        dogum_tarihi = personel.get("dogum_tarihi")
        if dogum_tarihi:
            tarih = QDate.fromString(dogum_tarihi, "dd.MM.yyyy")
            if tarih.isValid():
                self.date_dogum_tarihi.setDate(tarih)

        self.btn_kaydet.setText("GÜNCELLE")
        self.btn_kaydet.setStyleSheet("background-color: #e67e22; color: white; font-weight: bold;")

        # Fotoğraf
        self.photo_path = personel.get("photo_path") or ""
        if self.photo_path:
            self._set_photo_preview(self._resolve_photo_path(self.photo_path))
        else:
            if hasattr(self, "lbl_photo"):
                self.lbl_photo.setPixmap(QPixmap(":/resim/Photo.png"))
                self.lbl_photo.setAlignment(Qt.AlignmentFlag.AlignCenter)