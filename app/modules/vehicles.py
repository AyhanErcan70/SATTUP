import sys
import os
# --- PATH AYARLARI (Modül Bulunamadı Hatası İçin) ---
# Şu anki dosyanın bulunduğu klasörü al
current_dir = os.path.dirname(os.path.abspath(__file__))

# Bir üst klasöre (Proje Kök Dizini: C:\ELBEK) çık
root_dir = os.path.dirname(current_dir)

# Eğer proje kök dizini sistem yollarında yoksa, en başa ekle
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
import shutil
import json
from PyQt6.QtWidgets import (QMainWindow, QMessageBox, QFileDialog, QListWidgetItem, QWidget, QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt6.QtCore import QDate, Qt, QRegularExpression
from PyQt6.QtGui import QPixmap, QRegularExpressionValidator
from PyQt6 import uic

from app.core.db_manager import DatabaseManager
from config import get_ui_path
from app.utils.style_utils import clear_all_styles

# UI Dosyası Yolu
UI_PATH = "ui_files/arac.ui" if os.path.exists("ui_files/arac.ui") else "arac.ui"

class AracApp(QMainWindow):
    def __init__(self, dbManager=None, main_app_instance=None): # BU SATIR KRİTİK
        super().__init__()
        self.db = dbManager if dbManager else DatabaseManager()
        self.main_app = main_app_instance
        # 1. Arayüzü Yükle
        try:
            uic.loadUi(UI_PATH, self)
        except FileNotFoundError:
            uic.loadUi(os.path.join(os.path.dirname(__file__), "..", "ui", "arac.ui"), self)

        clear_all_styles(self)

        self.secili_resim_yolu = "" # Geçici resim yolu hafızası

        # --- JSON YÜKLEME ---
        self.marka_model_data = {}
        json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aracMarkaModel.json")
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                self.marka_model_data = json.load(f)
        except Exception as e:
            print(f"JSON Yükleme Hatası: {e}")
            # Hata olursa boş dictionary ile devam et, program çökmesin
            self.marka_model_data = {}

        # 2. ComboBox'ları Doldur (Sabit Veriler)
        self.init_combos()
        
        # 3. Listeyi Doldur
        self.load_arac_listesi()
        
        # 4. Sinyalleri Bağla
        self.setup_connections()

        self.txt_arac_kodu.setReadOnly(True) # Kullanıcı elle değiştiremesin
        self.formu_temizle()
        # self.yeni_kod_uret() # Açılışta kodu getir
        self.tarih_kisitlamalarini_baslat()

    def init_combos(self):
        
                
        # Tarihleri bugüne ayarla
        bugun = QDate.currentDate()
        tarih_alanlari = [
            self.date_muayene, self.date_sigorta, self.date_ruhsat, 
            self.date_kasko, self.date_koltuk, self.date_guzergah
        ]
        for tarih in tarih_alanlari:
            tarih.setDate(bugun)
            tarih.setDisplayFormat("dd.MM.yyyy") # <--- KRİTİK AYAR BURASI
            tarih.setCalendarPopup(True) # Takvim açılır olsun
        self.hizmet_turu_degisti()


    def setup_connections(self):
        self.btn_kaydet.clicked.connect(self.kaydet)
        self.btn_yeni.clicked.connect(self.formu_temizle)
        self.btn_sil.clicked.connect(self.sil)
        self.btn_resim.clicked.connect(self.resim_sec)
        
       # --- ZİNCİRLEME BAĞLANTILAR ---
        # 1. Hizmet değişince -> Kategori ve Markalar dolsun
        self.cmb_hizmet_turu.currentTextChanged.connect(self.hizmet_turu_degisti)
        
        # 2. Marka değişince -> Modeller dolsun
        self.cmb_marka.currentTextChanged.connect(self.marka_degisti)
        # Ana Menüye Dönüş
        # if self.main_app:
        #     self.btn_anamenu.clicked.connect(self.main_app.ana_menuye_don)
        
        # Listeden seçim
        self.list_araclar.itemClicked.connect(self.arac_secildi)
        
        # Arama
        self.txt_arac_ara.textChanged.connect(self.arama_yap)

    def yeni_kod_uret(self):
        """Veritabanından sıradaki kodu çeker ve kutuya yazar"""
        yeni_kod = self.db.get_next_arac_kodu()
        self.txt_arac_kodu.setText(yeni_kod)

    def load_arac_listesi(self):
        self.list_araclar.clear()
        araclar = self.db.get_araclar_list() # [(kod, plaka), ...] döner
        for kod, plaka in araclar:
            item = QListWidgetItem(f"{plaka} - {kod}")
            item.setData(Qt.ItemDataRole.UserRole, kod) # Kodu arka planda sakla
            self.list_araclar.addItem(item)

    def arama_yap(self):
        aranan = self.txt_arac_ara.text().lower()
        for i in range(self.list_araclar.count()):
            item = self.list_araclar.item(i)
            item.setHidden(aranan not in item.text().lower())

    def resim_sec(self):
        dosya_yolu, _ = QFileDialog.getOpenFileName(
            self, "Araç Resmi Seç", "", "Resim Dosyaları (*.png *.jpg *.jpeg)"
        )
        if dosya_yolu:
            self.secili_resim_yolu = dosya_yolu
            pixmap = QPixmap(dosya_yolu)
            self.lbl_resim.setPixmap(pixmap.scaled(self.lbl_resim.size(), Qt.AspectRatioMode.KeepAspectRatio))

    def hizmet_turu_degisti(self):
        """Hizmet Türü değişince hem Kategoriyi hem de Markaları yeniler."""
        secilen_hizmet = self.cmb_hizmet_turu.currentText().upper() # BÜYÜK HARF GÜVENCESİ
        
        # 1. KATEGORİ AYARLARI
        self.cmb_kategori.clear()
        if secilen_hizmet == "SERVİS ARACI":
            self.cmb_kategori.addItems(["Seçiniz...", "OTOBÜS", "MİNİBÜS"])
        elif secilen_hizmet == "HİZMET ARACI":
            self.cmb_kategori.addItems(["Seçiniz...", "OTOMOBİL", "KAMYONET", "PICK-UP"])
        else:
            self.cmb_kategori.addItem("Seçiniz...")

        # 2. MARKA AYARLARI (JSON'dan Çekme)
        self.cmb_marka.clear()
        self.cmb_marka.addItem("Seçiniz...")
        
        if secilen_hizmet in self.marka_model_data:
            # JSON'daki markaları alfabetik sırayla ekle
            markalar = sorted(self.marka_model_data[secilen_hizmet].keys())
            self.cmb_marka.addItems(markalar)
            
        # Marka değişince Modeli sıfırlaması için tetikle
        self.marka_degisti()

    def marka_degisti(self):
        """Marka değişince Modelleri yeniler."""
        secilen_hizmet = self.cmb_hizmet_turu.currentText().upper()
        secilen_marka = self.cmb_marka.currentText() # Zaten JSON'dan geldiği için büyüktür
        
        self.cmb_modeli.clear()
        self.cmb_modeli.addItem("Seçiniz...")
        
        # Zincirleme Kontrol: Hizmet Türü var mı? -> O Hizmetin içinde o Marka var mı?
        if (secilen_hizmet in self.marka_model_data and 
            secilen_marka in self.marka_model_data[secilen_hizmet]):
            
            modeller = self.marka_model_data[secilen_hizmet][secilen_marka]
            self.cmb_modeli.addItems(modeller)

    def kaydet(self):
        if not self.txt_plaka.text() or not self.txt_arac_kodu.text():
            QMessageBox.warning(self, "Hata", "Plaka ve Araç Kodu zorunludur!")
            return

        # Verileri Topla
        data = {
            "arac_kodu": self.txt_arac_kodu.text(),
            "plaka": self.txt_plaka.text(),
            "arac_turu": self.cmb_arac_turu.currentText(),
            "hizmet_turu": self.cmb_hizmet_turu.currentText(),
            "kategori": self.cmb_kategori.currentText(),
            "marka": self.cmb_marka.currentText(),
            "model": self.cmb_modeli.currentText(),
            "yil": self.txt_yil.text(),
            "kapasite": self.txt_kapasite.text(),
            "muayene_tarihi": self.date_muayene.date().toString("yyyy-MM-dd"),
            "sigorta_tarihi": self.date_sigorta.date().toString("yyyy-MM-dd"),
            "ruhsat_tarihi": self.date_ruhsat.date().toString("yyyy-MM-dd"),
            "kasko_tarihi": self.date_kasko.date().toString("yyyy-MM-dd"),
            "koltuk_tarihi": self.date_koltuk.date().toString("yyyy-MM-dd"),
            "guzergah_tarihi": self.date_guzergah.date().toString("yyyy-MM-dd"),
            "resim_yolu": self.secili_resim_yolu
        }

        # Güncelleme mi Yeni Kayıt mı Kontrolü
        # Basit mantık: Bu kodda bir araç var mı?
        mevcut = self.db.get_arac_by_code(data["arac_kodu"])
        
        if mevcut:
            # Güncelleme
            if self.db.update_arac(data):
                QMessageBox.information(self, "Başarılı", "Araç bilgileri güncellendi.")
            else:
                
                QMessageBox.critical(self, "Hata", "Güncelleme başarısız.")
        else:
            # Yeni Kayıt
            if self.db.add_arac(data):
                QMessageBox.information(self, "Başarılı", "Yeni araç eklendi.")
            else:
                QMessageBox.critical(self, "Hata", "Kayıt başarısız (Araç Kodu çakışıyor olabilir).")
        self.formu_temizle()
        self.load_arac_listesi()
        # Formu temizlemiyoruz ki kullanıcı kaydettiğini görsün, "Yeni" butonu var zaten.

    def tarih_kisitlamalarini_baslat(self):
        """Tarih alanlarına gelecek tarih girilmesini engeller."""
        
        # Hangi tarih kutusu, hangi etikete ait? (Uyarı mesajı için)
        self.tarih_alanlari_map = {
            self.date_muayene: "Muayene Tarihi",
            self.date_sigorta: "Trafik Sigorta Tarihi",
            self.date_ruhsat: "Ruhsat Tarihi",
            self.date_kasko: "Kasko Tarihi",
            self.date_koltuk: "Koltuk Sigorta Tarihi",
            self.date_guzergah: "Güzergah İzin Tarihi"
        }

        # Hepsine sinyal bağla: Tarih değişince kontrol et
        for date_widget in self.tarih_alanlari_map.keys():
            # CalendarPopup (Takvim) kapandığında veya tarih değiştiğinde tetikle
            date_widget.dateChanged.connect(lambda val, w=date_widget: self.tarih_kontrol(w))

    def tarih_kontrol(self, widget):
        """Seçilen tarih bugünden büyükse uyarır ve bugüne çeker."""
        secilen_tarih = widget.date()
        bugun = QDate.currentDate()
        
        if secilen_tarih > bugun:
            alan_adi = self.tarih_alanlari_map.get(widget, "Tarih Alanı")
            
            QMessageBox.warning(self, "Tarih Hatası", 
                                f"{alan_adi} için GELECEK bir tarih giremezsiniz!\n"
                                "Lütfen işlemin YAPILDIĞI son tarihi giriniz.\n"
                                "Sistem geçerlilik süresini kendisi hesaplayacaktır.")
            
            # Tarihi bugüne geri al (Hata yapmasını engelle)
            widget.blockSignals(True) # Sonsuz döngüye girmesin diye sinyali durdur
            widget.setDate(bugun)
            widget.blockSignals(False)

    def hesapla_gecerlilik_tarihi(self, islem_tarihi_str, belge_turu):
        """
        İleride 'Sabitler' modülünden gelecek verilerle hesaplama yapacak fonksiyon.
        Şimdilik burada manuel tanımlıyoruz.
        """
        # --- GEÇİCİ SABİTLER (Gün cinsinden) ---
        # İleride: sure = self.db.get_sabit_deger(belge_turu)
        sabit_sureler = {
            "muayene": 365,      # 1 Yıl
            "sigorta": 365,      # 1 Yıl
            "kasko": 365,        # 1 Yıl
            "koltuk": 365,       # 1 Yıl
            "guzergah": 180,     # 6 Ay (Örnek)
            "ruhsat": 3650       # 10 Yıl (Örnek)
        }
        
        sure = sabit_sureler.get(belge_turu, 365) # Bulamazsa varsayılan 1 yıl
        
        # String tarihi (yyyy-MM-dd) QDate'e çevir, süreyi ekle
        tarih = QDate.fromString(islem_tarihi_str, "dd-MM-yyyy")
        bitis_tarihi = tarih.addDays(sure)
        
        return bitis_tarihi.toString("d-MM-yyyy")  

    def arac_secildi(self, item):
        arac_kodu = item.data(Qt.ItemDataRole.UserRole)
        data = self.db.get_arac_by_code(arac_kodu)
        
        if not data:
            return

        # Alanları Doldur
        self.txt_arac_kodu.setText(data['arac_kodu'])
        self.txt_plaka.setText(data['plaka'])
        self.cmb_arac_turu.setCurrentText(data['arac_turu'])
        self.cmb_hizmet_turu.setCurrentText(data['hizmet_turu'])
        self.cmb_kategori.setCurrentText(data['kategori'])
        self.cmb_marka.setCurrentText(data['marka'])
        self.cmb_modeli.setCurrentText(data['model'])
        self.txt_yil.setText(data['yil'])
        self.txt_kapasite.setText(data['kapasite'])
        
        # Tarihleri Yükle (yyyy-MM-dd formatından QDate'e)
        def set_date(date_widget, date_str):
            if date_str:
                # Veritabanı formatı (yyyy-MM-dd) ile okuyoruz
                tarih_verisi = QDate.fromString(date_str, "yyyy-MM-dd")
                
                # Eğer veritabanında format farklıysa (dd.MM.yyyy gibiyse) onu da dene
                if not tarih_verisi.isValid():
                     tarih_verisi = QDate.fromString(date_str, "dd.MM.yyyy")
                     
                date_widget.setDate(tarih_verisi)

        set_date(self.date_muayene, data['muayene_tarihi'])
        set_date(self.date_sigorta, data['sigorta_tarihi'])
        set_date(self.date_ruhsat, data['ruhsat_tarihi'])
        set_date(self.date_kasko, data['kasko_tarihi'])
        set_date(self.date_koltuk, data['koltuk_tarihi'])
        set_date(self.date_guzergah, data['guzergah_tarihi'])

        # Resmi Yükle
        self.secili_resim_yolu = data['resim_yolu']
        if self.secili_resim_yolu and os.path.exists(self.secili_resim_yolu):
            pixmap = QPixmap(self.secili_resim_yolu)
            self.lbl_resim.setPixmap(pixmap.scaled(self.lbl_resim.size(), Qt.AspectRatioMode.KeepAspectRatio))
        else:
            self.lbl_resim.setText("RESİM YOK")

    def sil(self):
        arac_kodu = self.txt_arac_kodu.text()
        if not arac_kodu:
            return
            
        soru = QMessageBox.question(self, "Sil", f"{arac_kodu} kodlu aracı silmek istediğinize emin misiniz?", 
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if soru == QMessageBox.StandardButton.Yes:
            if self.db.delete_arac(arac_kodu):
                self.load_arac_listesi()
                self.formu_temizle()
                QMessageBox.information(self, "Bilgi", "Araç silindi.")

    def formu_temizle(self):
        # Mevcut temizleme kodların...
        self.txt_plaka.clear()
        self.txt_yil.clear()
        self.txt_kapasite.clear()
        self.cmb_arac_turu.setCurrentIndex(0)
        self.cmb_hizmet_turu.setCurrentIndex(0)
        self.cmb_kategori.setCurrentIndex(0)
        self.cmb_marka.setCurrentIndex(0)
        self.cmb_modeli.setCurrentIndex(0)
        self.secili_resim_yolu = ""
        self.lbl_resim.setText("RESİM ALANI")
        
        # --- EKLEMEN GEREKEN SATIR BURADA ---
        self.yeni_kod_uret() # Temizlendikten sonra yeni kodu ver
        # ------------------------------------
        
        self.txt_plaka.setFocus() # Odağı plakaya ver (Kod otomatik dolduğu için)


def _normalize_plate(text: str) -> str:
    import re
    t = (text or "").strip().upper()
    t = re.sub(r"\s+", " ", t)
    return t


class VehiclesApp(QWidget):
    def __init__(self, user_data=None, parent=None):
        super().__init__(parent)
        uic.loadUi(get_ui_path("vehicles_window.ui"), self)

        self.db = DatabaseManager()
        self.user_data = user_data
        self.current_code = None

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

        self._init_combos()
        self._init_dates()
        self.load_data()
        self._setup_filters()
        self._assign_next_code()

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
            "PLAKA",
            "ARAÇ TÜRÜ",
            "HİZMET TÜRÜ",
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
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        query = """
            SELECT vehicle_code, plate_number, arac_turu, hizmet_turu, kategori, brand, model, yil, capacity, is_active
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
                    if c == 9:
                        display = "AKTİF" if int(value or 0) == 1 else "PASİF"
                    else:
                        display = str(value) if value is not None else ""
                    item = QTableWidgetItem(display)
                    if c in [0, 2, 3, 7, 8, 9]:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if c == 9 and int(value or 0) == 0:
                        item.setForeground(Qt.GlobalColor.red)
                    self.tableView.setItem(r, c, item)
        except Exception as e:
            print(f"Araç yükleme hatası: {e}")

        if hasattr(self, "apply_filters"):
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
            row_arac_turu = (self.tableView.item(row, 2).text() if self.tableView.item(row, 2) else "").strip()
            row_hizmet = (self.tableView.item(row, 3).text() if self.tableView.item(row, 3) else "").strip()
            row_marka = (self.tableView.item(row, 5).text() if self.tableView.item(row, 5) else "").strip()
            row_plaka = (self.tableView.item(row, 1).text() if self.tableView.item(row, 1) else "").strip().upper()

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

        def to_int(val):
            try:
                return int(val)
            except Exception:
                return None

        return {
            "vehicle_code": (self.txt_arac_kodu.text() or "").strip() if hasattr(self, "txt_arac_kodu") else "",
            "plate_number": plate,
            "arac_turu": (self.cmb_arac_turu.currentText() or "").strip() if hasattr(self, "cmb_arac_turu") else "",
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
        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.setText("Kaydet")
        if hasattr(self, "txt_arac_plaka"):
            self.txt_arac_plaka.clear()
        if hasattr(self, "txt_yil"):
            self.txt_yil.clear()
        if hasattr(self, "txt_kapasite"):
            self.txt_kapasite.clear()
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

    def toggle_active_selected(self):
        code = self._get_selected_vehicle_code()
        if not code:
            QMessageBox.warning(self, "Uyarı", "Lütfen tablodan bir araç seçin.")
            return
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