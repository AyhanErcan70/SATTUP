import sys
import os
from PyQt6.QtWidgets import (QMainWindow, QMessageBox, QTableWidgetItem, QHeaderView, 
                             QAbstractItemView, QDialog, QVBoxLayout, QTableWidget, 
                             QLabel, QPushButton)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor
from PyQt6 import uic
from app.dbManager import DatabaseManager
from app.excelUtils import create_excel

UI_PATH = "ui_files/puantaj.ui" if os.path.exists("ui_files/puantaj.ui") else "puantaj.ui"

class PuantajApp(QMainWindow):
    def __init__(self, dbManager=None, main_app_instance=None): # BU SATIR KRİTİK
        super().__init__()
        self.db = dbManager if dbManager else DatabaseManager()
        self.main_app = main_app_instance
        try:
            uic.loadUi(UI_PATH, self)
        except FileNotFoundError:
            uic.loadUi(os.path.join(os.path.dirname(__file__), "..", "ui", "puantaj.ui"), self)

        self.main_app = main_app_instance
        self.db = DatabaseManager()
        self.aylik_veriler = []
        
        self.init_ui()
        self.setup_connections()

    def init_ui(self):
        self.setWindowTitle("Puantaj ve Hakediş Hesaplama")
        
        # --- MÜŞTERİ TABLOSU AYARLARI ---
        m_headers = ["Müşteri Adı", "Toplam Sefer", "Toplam KM", "Tahmini Tutar"]
        self.tbl_musteri_hakedis.setColumnCount(len(m_headers))
        self.tbl_musteri_hakedis.setHorizontalHeaderLabels(m_headers)
        self.tbl_musteri_hakedis.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_musteri_hakedis.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_musteri_hakedis.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        # --- SÜRÜCÜ TABLOSU AYARLARI ---
        s_headers = ["Plaka", "Sürücü", "Toplam Sefer", "Toplam KM"]
        self.tbl_surucu_hakedis.setColumnCount(len(s_headers))
        self.tbl_surucu_hakedis.setHorizontalHeaderLabels(s_headers)
        self.tbl_surucu_hakedis.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_surucu_hakedis.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_surucu_hakedis.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

    def setup_connections(self):
        if hasattr(self, 'btn_hesapla'): self.btn_hesapla.clicked.connect(self.hesapla)
        if hasattr(self, 'btn_geri_don'): self.btn_geri_don.clicked.connect(self.kapat)
        if hasattr(self, 'btn_excele_aktar'): self.btn_excele_aktar.clicked.connect(self.export_excel)
        
        # Çift Tıklama ile Detay Açma
        self.tbl_musteri_hakedis.itemDoubleClicked.connect(self.musteri_detay_ac)
        self.tbl_surucu_hakedis.itemDoubleClicked.connect(self.surucu_detay_ac)

        # TOPLU ÇETELE BUTONU (Kodla ekliyoruz, tasarımda yoksa)
        if hasattr(self, 'frame') and not hasattr(self, 'btn_toplu_cetele'):
            # Butonun ekleneceği layout'u bulmaya çalışalım (genelde footer'dadır)
            # Eğer footer_frame yoksa frame (sol menü) altına ekleyelim
            target_layout = None
            if hasattr(self, 'footer_frame'):
                target_layout = self.footer_frame.layout()
            elif hasattr(self, 'frame'):
                target_layout = self.frame.layout()

            if target_layout:
                self.btn_toplu_cetele = QPushButton("TOPLU ÇETELE GİRİŞİ")
                self.btn_toplu_cetele.setMinimumHeight(40)
                self.btn_toplu_cetele.setStyleSheet("background-color: #2c3e50; color: white; font-weight: bold;")
                self.btn_toplu_cetele.clicked.connect(self.toplu_cetele_ac)
                target_layout.addWidget(self.btn_toplu_cetele)

    def hesapla(self):
        """Seçilen ayın verilerini çeker, gruplar ve PARASINI hesaplar."""
        yil = self.cmb_yil.currentText()
        ay_isim = self.cmb_ay.currentText()
        
        aylar = {"OCAK": "01", "ŞUBAT": "02", "MART": "03", "NİSAN": "04", "MAYIS": "05", "HAZİRAN": "06",
                 "TEMMUZ": "07", "AĞUSTOS": "08", "EYLÜL": "09", "EKİM": "10", "KASIM": "11", "ARALIK": "12"}
        ay_no = aylar.get(ay_isim, "01")

        # Veritabanından Çek
        self.aylik_veriler = self.db.get_aylik_seferler(ay_no, yil)
        
        if not self.aylik_veriler:
            QMessageBox.information(self, "Bilgi", "Seçilen ayda kayıtlı sefer bulunamadı.")
            self.tbl_musteri_hakedis.setRowCount(0)
            self.tbl_surucu_hakedis.setRowCount(0)
            self.lbl_ozet.setText("Kayıt Bulunamadı")
            return

        # --- 1. MÜŞTERİ HAKEDİŞLERİNİ HESAPLA ---
        musteri_ozet = {} 
        genel_toplam_tutar = 0.0
        
        for row in self.aylik_veriler:
            # Sadece 'Tamamlandı' olanları topla
            durum = row[12] if len(row) > 12 else "Tamamlandı"
            if durum != "Tamamlandı": continue

            musteri = row[1]
            km = row[8] if row[8] else 0
            
            fiyat_str = str(row[10]).replace(".", "").replace(",", ".") if row[10] else "0"
            try:
                fiyat = float(fiyat_str)
            except:
                fiyat = 0.0

            if musteri not in musteri_ozet:
                musteri_ozet[musteri] = {"sefer": 0, "km": 0, "tutar": 0.0}
            
            musteri_ozet[musteri]["sefer"] += 1
            musteri_ozet[musteri]["km"] += int(km)
            musteri_ozet[musteri]["tutar"] += fiyat
            genel_toplam_tutar += fiyat

        # Tabloyu Doldur
        self.tbl_musteri_hakedis.setRowCount(0)
        for m_adi, veri in musteri_ozet.items():
            r = self.tbl_musteri_hakedis.rowCount()
            self.tbl_musteri_hakedis.insertRow(r)
            self.tbl_musteri_hakedis.setItem(r, 0, QTableWidgetItem(m_adi))
            self.tbl_musteri_hakedis.setItem(r, 1, QTableWidgetItem(str(veri["sefer"])))
            self.tbl_musteri_hakedis.setItem(r, 2, QTableWidgetItem(str(veri["km"])))
            para_format = f"{veri['tutar']:,.2f} TL".replace(",", "X").replace(".", ",").replace("X", ".")
            self.tbl_musteri_hakedis.setItem(r, 3, QTableWidgetItem(para_format))

        # --- 2. SÜRÜCÜ HAKEDİŞLERİNİ HESAPLA ---
        surucu_ozet = {}
        for row in self.aylik_veriler:
            durum = row[12] if len(row) > 12 else "Tamamlandı"
            if durum != "Tamamlandı": continue

            key = f"{row[2]} - {row[3]}"
            km = row[8] if row[8] else 0
            
            if key not in surucu_ozet:
                surucu_ozet[key] = {"sefer": 0, "km": 0}
            
            surucu_ozet[key]["sefer"] += 1
            surucu_ozet[key]["km"] += int(km)

        self.tbl_surucu_hakedis.setRowCount(0)
        for s_adi, veri in surucu_ozet.items():
            r = self.tbl_surucu_hakedis.rowCount()
            self.tbl_surucu_hakedis.insertRow(r)
            parts = s_adi.split(" - ")
            self.tbl_surucu_hakedis.setItem(r, 0, QTableWidgetItem(parts[0]))
            self.tbl_surucu_hakedis.setItem(r, 1, QTableWidgetItem(parts[1] if len(parts)>1 else ""))
            self.tbl_surucu_hakedis.setItem(r, 2, QTableWidgetItem(str(veri["sefer"])))
            self.tbl_surucu_hakedis.setItem(r, 3, QTableWidgetItem(str(veri["km"])))

        # Özet Bilgi
        toplam_sefer = len([x for x in self.aylik_veriler if len(x)>12 and x[12]=="Tamamlandı"])
        ciro_format = f"{genel_toplam_tutar:,.2f} TL".replace(",", "X").replace(".", ",").replace("X", ".")
        self.lbl_ozet.setText(f"Tamamlanan Sefer: {toplam_sefer} | Ciro: {ciro_format}")

    def toplu_cetele_ac(self):
        if not self.aylik_veriler:
            QMessageBox.warning(self, "Uyarı", "Lütfen önce 'HESAPLA' butonuna basınız.")
            return
        self.detay_penceresi_goster("TOPLU PUANTAJ GİRİŞİ", self.aylik_veriler, toplu_mod=True)

    def musteri_detay_ac(self, item):
        row = item.row()
        musteri_adi = self.tbl_musteri_hakedis.item(row, 0).text()
        detaylar = [x for x in self.aylik_veriler if x[1] == musteri_adi]
        self.detay_penceresi_goster(f"{musteri_adi} Detayı", detaylar)

    def surucu_detay_ac(self, item):
        row = item.row()
        plaka = self.tbl_surucu_hakedis.item(row, 0).text()
        detaylar = [x for x in self.aylik_veriler if x[2] == plaka]
        self.detay_penceresi_goster(f"{plaka} Detayı", detaylar)

    def detay_penceresi_goster(self, baslik, veriler, toplu_mod=False):
        """EXCEL GÖRÜNÜMLÜ PUANTAJ - TAM FONKSİYONEL"""
        self.temp_dialog = QDialog(self)
        self.temp_dialog.setWindowTitle(baslik)
        self.temp_dialog.setWindowState(Qt.WindowState.WindowMaximized)
        
        layout = QVBoxLayout()
        
        # Tarih Hesabı
        yil = int(self.cmb_yil.currentText())
        ay_isim = self.cmb_ay.currentText()
        aylar = {"OCAK": 1, "ŞUBAT": 2, "MART": 3, "NİSAN": 4, "MAYIS": 5, "HAZİRAN": 6,
                 "TEMMUZ": 7, "AĞUSTOS": 8, "EYLÜL": 9, "EKİM": 10, "KASIM": 11, "ARALIK": 12}
        ay = aylar.get(ay_isim, 1)
        self.days_in_month = QDate(yil, ay, 1).daysInMonth()

        # Bilgi
        lbl = QLabel("TURBO GİRİŞ: Rakam (1,2..) yazıp ilerleyin. Silmek için Delete tuşuna basın.")
        lbl.setStyleSheet("font-weight: bold; color: #2c3e50; font-size: 14px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)

        self.temp_table = QTableWidget()
        self.temp_table.setStyleSheet("""
            QTableWidget { gridline-color: #bdc3c7; selection-background-color: #3498db; }
            QTableWidget::item:selected { background-color: #b8e994; color: black; font-weight: bold; border: 2px solid green; }
        """)

        # Başlıklar
        headers = ["GÜZERGAH", "PLAKA / SÜRÜCÜ", "SAAT / YÖN"]
        self.haftasonu_sutunlari = []
        
        for i in range(1, self.days_in_month + 1):
            d = QDate(yil, ay, i)
            gun_adi = ["Pzt","Sal","Çar","Per","Cum","Cmt","Paz"][d.dayOfWeek()-1]
            headers.append(f"{i}\n{gun_adi}")
            if d.dayOfWeek() in [6, 7]: self.haftasonu_sutunlari.append(i + 2)
            
        headers.extend(["TOPLAM\nSEFER", "BİRİM\nFİYAT", "GENEL\nTUTAR"])
        
        self.temp_table.setColumnCount(len(headers))
        self.temp_table.setHorizontalHeaderLabels(headers)

        # Sütun Genişlikleri
        h_header = self.temp_table.horizontalHeader()
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        for i in range(3, 3 + self.days_in_month): h_header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        h_header.setSectionResizeMode(3 + self.days_in_month, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(3 + self.days_in_month + 1, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(3 + self.days_in_month + 2, QHeaderView.ResizeMode.Fixed)
        self.temp_table.setColumnWidth(3 + self.days_in_month + 2, 120)

        # Veri Hazırlama
        satir_data = {} 
        satir_meta = {} 

        for row in veriler:
            try:
                # row yapısı: 0:tarih ... 10:fiyat, 11:id, 12:durum, 13:saat
                gun = int(row[0].split(".")[0])
                sefer_id = row[11]
                durum = row[12] if len(row) > 12 else "Planlandı"
                fiyat = row[10] if row[10] else "0"
                saat = row[13] if len(row) > 13 else ""
                
                # GİRİŞ/ÇIKIŞ metni
                saat_metni = f"{saat} {row[4]}" if saat else row[4]
                plaka_metni = f"{row[2]}\n{row[3]}"
                
                anahtar = (row[5], plaka_metni, saat_metni)
                
                if anahtar not in satir_data: 
                    satir_data[anahtar] = {}
                    satir_meta[anahtar] = fiyat 
                
                if gun not in satir_data[anahtar]: satir_data[anahtar][gun] = []
                satir_data[anahtar][gun].append((sefer_id, durum))
            except: continue

        self.temp_table.setRowCount(len(satir_data))

        # Tabloyu Doldur
        for r_idx, (anahtar, gunler) in enumerate(satir_data.items()):
            self.temp_table.setItem(r_idx, 0, QTableWidgetItem(anahtar[0]))
            self.temp_table.setItem(r_idx, 1, QTableWidgetItem(anahtar[1]))
            self.temp_table.setItem(r_idx, 2, QTableWidgetItem(anahtar[2]))
            
            start_col = 3
            end_col = 3 + self.days_in_month
            toplam_sefer = 0
            
            for day in range(1, self.days_in_month + 1):
                col_idx = start_col + (day - 1)
                bg_color = QColor("#ecf0f1") if col_idx in self.haftasonu_sutunlari else QColor("#ffffff")
                item = QTableWidgetItem("")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setBackground(bg_color)
                
                if day in gunler:
                    sefer_listesi = gunler[day]
                    sefer_id = sefer_listesi[0][0]
                    durum = sefer_listesi[0][1]
                    item.setData(Qt.ItemDataRole.UserRole, sefer_id)
                    
                    if durum == "Tamamlandı":
                        item.setText("1")
                        item.setFont(self.get_bold_font())
                        toplam_sefer += 1
                else:
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                
                self.temp_table.setItem(r_idx, col_idx, item)
            
            # Sağ Taraf
            item_toplam = QTableWidgetItem(str(toplam_sefer))
            item_toplam.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_toplam.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item_toplam.setBackground(QColor("#dfe6e9"))
            self.temp_table.setItem(r_idx, end_col, item_toplam)
            
            fiyat_str = satir_meta.get(anahtar, "0")
            item_fiyat = QTableWidgetItem(fiyat_str)
            item_fiyat.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.temp_table.setItem(r_idx, end_col + 1, item_fiyat)
            
            self.satir_tutarini_hesapla(r_idx)

        self.temp_table.keyPressEvent = self.tablo_tus_olayi
        layout.addWidget(self.temp_table)
        
        btn_onayla = QPushButton("DEĞİŞİKLİKLERİ ONAYLA VE KAYDET")
        btn_onayla.setMinimumHeight(45)
        btn_onayla.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
        btn_onayla.clicked.connect(self.kaydet_ve_cikis)
        layout.addWidget(btn_onayla)

        self.temp_dialog.setLayout(layout)
        self.temp_dialog.exec()
        self.hesapla()

    def get_bold_font(self):
        f = self.temp_table.font()
        f.setBold(True)
        return f

    def tablo_tus_olayi(self, event):
        row = self.temp_table.currentRow()
        col = self.temp_table.currentColumn()
        item = self.temp_table.currentItem()
        start_col = 3
        end_col = 3 + self.days_in_month
        
        if not item or col < start_col or col >= end_col:
            QTableWidget.keyPressEvent(self.temp_table, event)
            return
        if not item.data(Qt.ItemDataRole.UserRole):
            QTableWidget.keyPressEvent(self.temp_table, event)
            return

        if event.text().isdigit() and int(event.text()) > 0:
            item.setText(event.text())
            item.setFont(self.get_bold_font())
            item.setBackground(QColor(Qt.GlobalColor.green))
            self.satir_tutarini_hesapla(row)
            self.temp_table.setCurrentCell(row, col + 1)
        elif event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            item.setText("")
            bg = QColor("#ecf0f1") if col in self.haftasonu_sutunlari else QColor("#ffffff")
            item.setBackground(bg)
            self.satir_tutarini_hesapla(row)
        else:
            QTableWidget.keyPressEvent(self.temp_table, event)

    def satir_tutarini_hesapla(self, row):
        toplam_sefer = 0
        start_col = 3
        end_col = 3 + self.days_in_month
        for c in range(start_col, end_col):
            item = self.temp_table.item(row, c)
            if item and item.text().isdigit():
                toplam_sefer += int(item.text())
        
        col_toplam = end_col
        self.temp_table.item(row, col_toplam).setText(str(toplam_sefer))
        
        col_fiyat = end_col + 1
        col_tutar = end_col + 2
        try:
            fiyat_str = self.temp_table.item(row, col_fiyat).text()
            fiyat = float(fiyat_str.replace(".", "").replace(",", "."))
            tutar = toplam_sefer * fiyat
            tutar_fmt = f"{tutar:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            if not self.temp_table.item(row, col_tutar):
                self.temp_table.setItem(row, col_tutar, QTableWidgetItem(""))
            self.temp_table.item(row, col_tutar).setText(tutar_fmt + " TL")
            self.temp_table.item(row, col_tutar).setBackground(QColor("#dff9fb"))
        except: pass

    def kaydet_ve_cikis(self):
        soru = QMessageBox.question(self.temp_dialog, "Onay", "Puantaj kaydedilsin mi?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if soru == QMessageBox.StandardButton.No: return
        conn = self.db.connect()
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN TRANSACTION")
            rows = self.temp_table.rowCount()
            start_col = 3
            end_col = 3 + self.days_in_month
            for r in range(rows):
                for c in range(start_col, end_col):
                    item = self.temp_table.item(r, c)
                    if not item: continue
                    sefer_id = item.data(Qt.ItemDataRole.UserRole)
                    if not sefer_id: continue
                    text = item.text()
                    yeni_durum = "Tamamlandı" if (text.isdigit() and int(text) > 0) else "Planlandı"
                    cursor.execute("UPDATE seferler SET durum=? WHERE id=?", (yeni_durum, sefer_id))
            cursor.execute("COMMIT")
            self.temp_dialog.accept()
        except Exception as e:
            cursor.execute("ROLLBACK")
            QMessageBox.critical(self.temp_dialog, "Hata", str(e))
        finally:
            conn.close()

    def export_excel(self):
        user = getattr(self.main_app, 'current_user', 'Admin')
        aktif_index = self.sekmeli_form.currentIndex()
        if aktif_index == 0:
            create_excel(self.tbl_musteri_hakedis, "Müşteri Hakediş Raporu", user, self)
        else:
            create_excel(self.tbl_surucu_hakedis, "Sürücü Hakediş Raporu", user, self)

    def kapat(self):
        if self.main_app: self.main_app.ana_menuye_don()