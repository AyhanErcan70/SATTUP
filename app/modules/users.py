import os
from PyQt6.QtWidgets import QWidget, QMessageBox, QTableWidgetItem, QHeaderView, QAbstractItemView,QSizePolicy
from PyQt6.QtCore import Qt 

from PyQt6 import uic
from app.core.db_manager import DatabaseManager
from config import get_ui_path
from app.utils.style_utils import clear_all_styles

class UsersApp(QWidget):
    def __init__(self, dbManager=None, main_app_instance=None):
        super().__init__()
        # 1. Arayüzü Yükle
        uic.loadUi(get_ui_path("users_window.ui"), self)
        clear_all_styles(self)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.db = dbManager if dbManager else DatabaseManager()
        self.main_app = main_app_instance
        self.selected_user_id = None # Güncelleme için seçili ID

        # 2. Hazırlıkları Yap
        self.init_ui()
        self.setup_connections()
        self.load_data()

    def init_ui(self):
        # Combo içeriği
        self.cmb_role.clear()
        self.cmb_role.addItems(["personel", "admin"])
        
        # Tablo ayarları
        self.table_users.setColumnCount(4)
        self.table_users.setHorizontalHeaderLabels(["ID", "Kullanıcı Adı", "Rol", "Durum"])
        self.table_users.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_users.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def setup_connections(self):
        self.btn_save.clicked.connect(self.save_user)
        self.btn_del.clicked.connect(self.delete_user)
        self.btn_new.clicked.connect(self.clear_form)
        self.table_users.itemDoubleClicked.connect(self.on_row_selected)

    def load_data(self):
        """db_manager üzerinden kullanıcıları çeker ve tabloya doldur."""
        self.table_users.setRowCount(0)
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, role, is_active FROM users")
            users = cursor.fetchall()
            conn.close()

            for row_idx, row_data in enumerate(users):
                self.table_users.insertRow(row_idx)
                for col_idx, value in enumerate(row_data):
                    display_value = "Aktif" if col_idx == 3 and value == 1 else ("Pasif" if col_idx == 3 else str(value))
                    self.table_users.setItem(row_idx, col_idx, QTableWidgetItem(display_value))
        except Exception as e:
            print(f"Kullanıcı yükleme hatası: {e}")

    def save_user(self):
        username = self.txt_username.text().strip()
        password = self.txt_pass.text().strip()
        password_confirm = self.txt_pass_again.text().strip() # Yeni nesne
        role = self.cmb_role.currentText()

        # Eksik veri kontrolü
        if not username or not password:
            QMessageBox.warning(self, "Eksik Veri", "Kullanıcı adı ve şifre boş bırakılamaz!")
            return

        # Şifre teyit kontrolü
        if password != password_confirm:
            QMessageBox.warning(self, "Şifre Hatası", "Girdiğiniz şifreler birbiriyle eşleşmiyor!")
            return

        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            
            if self.selected_user_id: # GÜNCELLEME
                cursor.execute("UPDATE users SET username=?, password=?, role=? WHERE id=?", 
                               (username, password, role, self.selected_user_id))
            else: # YENİ KAYIT
                cursor.execute("INSERT INTO users (username, password, role, is_active) VALUES (?, ?, ?, 1)", 
                               (username, password, role))
            
            conn.commit()
            conn.close()
            QMessageBox.information(self, "Başarılı", "Kullanıcı bilgileri kaydedildi.")
            self.load_data()
            self.clear_form()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"İşlem başarısız: {str(e)}")

    def delete_user(self):
        if not self.selected_user_id:
            QMessageBox.warning(self, "Seçim Yok", "Lütfen silmek istediğiniz kullanıcıyı tablodan çift tıklayarak seçin.")
            return

        if self.txt_username.text() == "admin":
            QMessageBox.warning(self, "Kısıtlama", "Ana yönetici (admin) hesabı silinemez!")
            return

        soru = QMessageBox.question(self, "Onay", "Kullanıcıyı silmek istediğinize emin misiniz?", 
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if soru == QMessageBox.StandardButton.Yes:
            try:
                conn = self.db.connect()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE id=?", (self.selected_user_id,))
                conn.commit()
                conn.close()
                self.load_data()
                self.clear_form()
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Silme hatası: {e}")

    def on_row_selected(self, item):
        row = item.row()
        self.selected_user_id = self.table_users.item(row, 0).text()
        self.txt_username.setText(self.table_users.item(row, 1).text())
        self.cmb_role.setCurrentText(self.table_users.item(row, 2).text())
        # Şifre alanlarını güncelleme modunda boş bırakıyoruz (güvenlik için)
        self.txt_pass.clear()
        self.txt_pass_again.clear()
        self.btn_save.setText("GÜNCELLE")

    def clear_form(self):
        self.selected_user_id = None
        self.txt_username.clear()
        self.txt_pass.clear()
        self.txt_pass_again.clear() # Temizleme eklendi
        self.cmb_role.setCurrentIndex(0)
        self.btn_save.setText("KAYDET")
        self.txt_username.setFocus()