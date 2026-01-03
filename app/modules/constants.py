from PyQt6.QtWidgets import QWidget, QListWidgetItem, QMessageBox
from PyQt6.QtCore import Qt
from PyQt6 import uic, QtCore
import ui.icons.resource_rc 
from config import get_ui_path

class ConstantsApp(QWidget):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        uic.loadUi(get_ui_path("constants_window.ui"), self)
        self.db = db_manager
        
        self.groups = {
            "turler": "personel_turu",
            "gorev": "gorev",
            "banka": "banka",
            "kan": "kan_grubu",
            "iller": "il",
            "ilceler": "ilce"
        }
        
        self.setup_connections()
        self.load_all_data()

    def setup_connections(self):
        # --- EKLEME BUTONLARI ---
        self.btn_ekle_turler.clicked.connect(lambda: self.add_new_item("turler"))
        self.btn_ekle_gorev.clicked.connect(lambda: self.add_new_item("gorev"))
        self.btn_ekle_banka.clicked.connect(lambda: self.add_new_item("banka"))
        self.btn_ekle_kan.clicked.connect(lambda: self.add_new_item("kan"))
        self.btn_ekle_iller.clicked.connect(lambda: self.add_new_item("iller"))
        self.btn_ekle_ilceler.clicked.connect(self.add_new_district)

        # --- SİLME BUTONLARI ---
        self.btn_sil_turler.clicked.connect(lambda: self.remove_item("turler"))
        self.btn_sil_gorev.clicked.connect(lambda: self.remove_item("gorev"))
        self.btn_sil_banka.clicked.connect(lambda: self.remove_item("banka"))
        self.btn_sil_kan.clicked.connect(lambda: self.remove_item("kan"))
        self.btn_sil_iller.clicked.connect(lambda: self.remove_item("iller"))
        self.btn_sil_ilceler.clicked.connect(lambda: self.remove_item("ilceler"))

        # --- ANINDA KAYIT SİNYALLERİ ---
        self.list_turler.itemChanged.connect(lambda item: self.save_item(item, "turler"))
        self.list_gorev.itemChanged.connect(lambda item: self.save_item(item, "gorev"))
        self.list_banka.itemChanged.connect(lambda item: self.save_item(item, "banka"))
        self.list_kan.itemChanged.connect(lambda item: self.save_item(item, "kan"))
        self.list_iller.itemChanged.connect(lambda item: self.save_item(item, "iller"))
        self.list_ilceler.itemChanged.connect(lambda item: self.save_item(item, "ilceler"))

        # İl seçilince ilçeleri filtrele
        self.list_iller.itemSelectionChanged.connect(self.load_districts)
        self.all_lists = [
            self.list_turler, self.list_gorev, self.list_banka, 
            self.list_kan, self.list_iller, self.list_ilceler
        ]

        # Her liste için "tıklandığında diğerlerini temizle" kuralını bağla
        for lst in self.all_lists:
            lst.itemPressed.connect(lambda item, current_list=lst: self.clear_other_selections(current_list))

    def clear_other_selections(self, active_list):
        """Aktif liste dışındaki tüm listelerin seçimlerini temizler."""
        for lst in self.all_lists:
            if lst is not active_list:
                lst.clearSelection()

    def add_new_item(self, key):
        list_widget = getattr(self, f"list_{key}")
        item = QListWidgetItem("Yeni Kayıt...")
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        list_widget.addItem(item)
        list_widget.editItem(item)

    def add_new_district(self):
        selected_il = self.list_iller.currentItem()
        if not selected_il or selected_il.data(Qt.ItemDataRole.UserRole) is None:
            QMessageBox.warning(self, "Uyarı", "Lütfen önce kayıtlı bir İl seçiniz!")
            return
        self.add_new_item("ilceler")

    def save_item(self, item, key):
        text = item.text().strip()
        if not text or text == "Yeni Kayıt...": return

        constant_id = item.data(Qt.ItemDataRole.UserRole)
        group_db_name = self.groups[key]
        
        parent_id = None
        if key == "ilceler":
            selected_il = self.list_iller.currentItem()
            if selected_il:
                # HATA BURADAYDI: .setData değil .data kullanıyoruz
                parent_id = selected_il.data(Qt.ItemDataRole.UserRole)

        # DB'ye kaydet/güncelle
        new_id = self.db.update_or_insert_constant(group_db_name, text, constant_id, parent_id)
        
        # Sinyali geçici blokla (Sonsuz döngüyü engellemek için önemli)
        list_widget = getattr(self, f"list_{key}")
        list_widget.blockSignals(True)
        item.setData(Qt.ItemDataRole.UserRole, new_id)
        list_widget.blockSignals(False)

    def remove_item(self, key):
        list_widget = getattr(self, f"list_{key}")
        item = list_widget.currentItem()
        if not item: return
        
        constant_id = item.data(Qt.ItemDataRole.UserRole)
        if constant_id:
            msg = QMessageBox.question(self, "Onay", "Bu kaydı silmek istediğinize emin misiniz?",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if msg == QMessageBox.StandardButton.Yes:
                self.db.delete_constant(constant_id)
                list_widget.takeItem(list_widget.row(item))
        else:
            # Henüz DB'ye kaydedilmemişse doğrudan listeden sil
            list_widget.takeItem(list_widget.row(item))

    def load_districts(self):
        selected_il = self.list_iller.currentItem()
        if not selected_il: return
        
        il_id = selected_il.data(Qt.ItemDataRole.UserRole)
        self.list_ilceler.clear()
        self.list_ilceler.blockSignals(True)
        if il_id:
            districts = self.db.get_constants("ilce", parent_id=il_id)
            for d_id, d_val in districts:
                item = QListWidgetItem(d_val)
                item.setData(Qt.ItemDataRole.UserRole, d_id)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                self.list_ilceler.addItem(item)
        self.list_ilceler.blockSignals(False)

    def load_all_data(self):
        for key in ["turler", "gorev", "banka", "kan", "iller"]:
            self.refresh_list(key)

    def refresh_list(self, key):
        list_widget = getattr(self, f"list_{key}")
        list_widget.blockSignals(True)
        list_widget.clear()
        data = self.db.get_constants(self.groups[key])
        for id_val, value in data:
            item = QListWidgetItem(value)
            item.setData(Qt.ItemDataRole.UserRole, id_val)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            item.setSizeHint(QtCore.QSize(0, 22))
            list_widget.addItem(item)
        list_widget.blockSignals(False)
        """Veritabanından güncel verileri listeye çeker"""
        list_widget = getattr(self, f"list_{key}")
        list_widget.clear()
        data = self.db.get_constants(self.groups[key])
        for id_val, value in data:
            item = QListWidgetItem(value)
            item.setData(Qt.ItemDataRole.UserRole, id_val) # ID bilgisini saklıyoruz
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsEnabled)
            item.setSizeHint(QtCore.QSize(0, 22))
            list_widget.addItem(item)