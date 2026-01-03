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
from PyQt6.QtWidgets import (QMainWindow, QMessageBox, QFileDialog, QListWidgetItem)
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QPixmap
from PyQt6 import uic
from app.dbManager import DatabaseManager

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