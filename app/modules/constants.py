from PyQt6.QtWidgets import QWidget, QListWidgetItem, QMessageBox, QTableWidgetItem
from PyQt6.QtCore import Qt
from PyQt6 import uic, QtCore
import ui.icons.context_rc 
from config import get_ui_path
from app.utils.style_utils import clear_all_styles

class ConstantsApp(QWidget):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        uic.loadUi(get_ui_path("constants_window.ui"), self)
        clear_all_styles(self)
        self.db = db_manager

        self._selected_belge_id = None
        
        self.groups = {
            "turler": "personel_turu",
            "gorev": "gorev",
            "banka": "banka",
            "kan": "kan_grubu",
            "iller": "il",
            "ilceler": "ilce",
            "marka": "arac_marka",
            "model": "arac_model",
            "bakim_firma": "bakim_firma",
            "bakim_islemleri": "bakim_islemleri",
            "bakim_turu": "bakim_turu",
            "belge_tanimlari": "belge_tanimlari",
        }
        
        self.ui_lists = {
            "turler": "list_turler",
            "gorev": "list_gorev",
            "banka": "list_banka",
            "kan": "list_kan",
            "iller": "list_iller",
            "ilceler": "list_ilceler",
            "marka": "list_marka",
            "model": "list_model",
            "bakim_firma": "list_firma",
            "bakim_islemleri": "list_bakim_islem",
            "bakim_turu": "list_bakim_turu",
        }
        
        self.setup_connections()
        self.load_all_data()
        self._load_vize_surucu_values()
        self._setup_belge_tanimlari_ui()
        self._load_belge_tanimlari_table()

    def setup_connections(self):
        # --- EKLEME BUTONLARI ---
        self.btn_ekle_turler.clicked.connect(lambda: self.add_new_item("turler"))
        self.btn_ekle_gorev.clicked.connect(lambda: self.add_new_item("gorev"))
        self.btn_ekle_banka.clicked.connect(lambda: self.add_new_item("banka"))
        self.btn_ekle_kan.clicked.connect(lambda: self.add_new_item("kan"))
        self.btn_ekle_iller.clicked.connect(lambda: self.add_new_item("iller"))
        self.btn_ekle_ilceler.clicked.connect(self.add_new_district)

        if hasattr(self, "btn_ekle_marka"):
            self.btn_ekle_marka.clicked.connect(lambda: self.add_new_item("marka"))
        if hasattr(self, "btn_ekle_model"):
            self.btn_ekle_model.clicked.connect(lambda: self.add_new_item("model"))
        if hasattr(self, "btn_ekle_firma"):
            self.btn_ekle_firma.clicked.connect(lambda: self.add_new_item("bakim_firma"))
        if hasattr(self, "btn_ekle_bakim_islem"):
            self.btn_ekle_bakim_islem.clicked.connect(lambda: self.add_new_item("bakim_islemleri"))
        if hasattr(self, "btn_ekle_bakim_turu"):
            self.btn_ekle_bakim_turu.clicked.connect(lambda: self.add_new_item("bakim_turu"))

        # --- SİLME BUTONLARI ---
        self.btn_sil_turler.clicked.connect(lambda: self.remove_item("turler"))
        self.btn_sil_gorev.clicked.connect(lambda: self.remove_item("gorev"))
        self.btn_sil_banka.clicked.connect(lambda: self.remove_item("banka"))
        self.btn_sil_kan.clicked.connect(lambda: self.remove_item("kan"))
        self.btn_sil_iller.clicked.connect(lambda: self.remove_item("iller"))
        self.btn_sil_ilceler.clicked.connect(lambda: self.remove_item("ilceler"))

        if hasattr(self, "btn_sil_marka"):
            self.btn_sil_marka.clicked.connect(lambda: self.remove_item("marka"))
        if hasattr(self, "btn_sil_model"):
            self.btn_sil_model.clicked.connect(lambda: self.remove_item("model"))
        if hasattr(self, "btn_sil_firma"):
            self.btn_sil_firma.clicked.connect(lambda: self.remove_item("bakim_firma"))
        if hasattr(self, "btn_sil_bakim_islem"):
            self.btn_sil_bakim_islem.clicked.connect(lambda: self.remove_item("bakim_islemleri"))
        if hasattr(self, "btn_sil_bakim_turu"):
            self.btn_sil_bakim_turu.clicked.connect(lambda: self.remove_item("bakim_turu"))

        # --- ANINDA KAYIT SİNYALLERİ ---
        self.list_turler.itemChanged.connect(lambda item: self.save_item(item, "turler"))
        self.list_gorev.itemChanged.connect(lambda item: self.save_item(item, "gorev"))
        self.list_banka.itemChanged.connect(lambda item: self.save_item(item, "banka"))
        self.list_kan.itemChanged.connect(lambda item: self.save_item(item, "kan"))
        self.list_iller.itemChanged.connect(lambda item: self.save_item(item, "iller"))
        self.list_ilceler.itemChanged.connect(lambda item: self.save_item(item, "ilceler"))

        if hasattr(self, "list_marka"):
            self.list_marka.itemChanged.connect(lambda item: self.save_item(item, "marka"))
        if hasattr(self, "list_model"):
            self.list_model.itemChanged.connect(lambda item: self.save_item(item, "model"))
        if hasattr(self, "list_firma"):
            self.list_firma.itemChanged.connect(lambda item: self.save_item(item, "bakim_firma"))
        if hasattr(self, "list_bakim_islem"):
            self.list_bakim_islem.itemChanged.connect(lambda item: self.save_item(item, "bakim_islemleri"))
        if hasattr(self, "list_bakim_turu"):
            self.list_bakim_turu.itemChanged.connect(lambda item: self.save_item(item, "bakim_turu"))

        if hasattr(self, "btn_kaydet_2"):
            self.btn_kaydet_2.clicked.connect(self._save_vizeler)
        if hasattr(self, "btn_sil_2"):
            self.btn_sil_2.clicked.connect(self._delete_vizeler)
        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.clicked.connect(self._save_surucu)
        if hasattr(self, "btn_sil"):
            self.btn_sil.clicked.connect(self._delete_surucu)

        if hasattr(self, "btn_belge_ekle"):
            self.btn_belge_ekle.clicked.connect(self._belge_ekle_or_guncelle)
        if hasattr(self, "btn_belge_sil"):
            self.btn_belge_sil.clicked.connect(self._belge_sil)
        if hasattr(self, "btn_belge_yeni"):
            self.btn_belge_yeni.clicked.connect(self._belge_form_temizle)
        if hasattr(self, "table_belge_tanimlari"):
            self.table_belge_tanimlari.itemSelectionChanged.connect(self._belge_on_select)

        # İl seçilince ilçeleri filtrele
        self.list_iller.itemSelectionChanged.connect(self.load_districts)
        self.all_lists = [
            self.list_turler, self.list_gorev, self.list_banka, 
            self.list_kan, self.list_iller, self.list_ilceler
        ]

        if hasattr(self, "list_marka"):
            self.all_lists.append(self.list_marka)
        if hasattr(self, "list_model"):
            self.all_lists.append(self.list_model)
        if hasattr(self, "list_firma"):
            self.all_lists.append(self.list_firma)
        if hasattr(self, "list_bakim_turu"):
            self.all_lists.append(self.list_bakim_turu)
        if hasattr(self, "list_bakim_islem"):
            self.all_lists.append(self.list_bakim_islem)

        # Her liste için "tıklandığında diğerlerini temizle" kuralını bağla
        for lst in self.all_lists:
            lst.itemPressed.connect(lambda item, current_list=lst: self.clear_other_selections(current_list))

    def clear_other_selections(self, active_list):
        """Aktif liste dışındaki tüm listelerin seçimlerini temizler."""
        for lst in self.all_lists:
            if lst is not active_list:
                lst.clearSelection()

    def add_new_item(self, key):
        list_widget_name = self.ui_lists.get(key)
        if not list_widget_name or not hasattr(self, list_widget_name):
            return
        list_widget = getattr(self, list_widget_name)
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
        list_widget_name = self.ui_lists.get(key)
        if not list_widget_name or not hasattr(self, list_widget_name):
            return
        list_widget = getattr(self, list_widget_name)
        list_widget.blockSignals(True)
        item.setData(Qt.ItemDataRole.UserRole, new_id)
        list_widget.blockSignals(False)

    def remove_item(self, key):
        list_widget_name = self.ui_lists.get(key)
        if not list_widget_name or not hasattr(self, list_widget_name):
            return
        list_widget = getattr(self, list_widget_name)
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
        for key in [
            "turler",
            "gorev",
            "banka",
            "kan",
            "iller",
            "marka",
            "model",
            "bakim_firma",
            "bakim_islemleri",
            "bakim_turu",
        ]:
            self.refresh_list(key)

    def _upsert_single_constant(self, group_name, value):
        rows = self.db.get_constants(group_name)
        constant_id = rows[0][0] if rows else None
        return self.db.update_or_insert_constant(group_name, value, constant_id=constant_id)

    def _delete_group_constants(self, group_name):
        rows = self.db.get_constants(group_name)
        for cid, _val in rows:
            self.db.delete_constant(cid)

    def _get_combo_value(self, combo_name, text_name):
        if not hasattr(self, combo_name) or not hasattr(self, text_name):
            return ""
        combo = getattr(self, combo_name)
        txt = getattr(self, text_name)
        unit = (combo.currentText() or "").strip()
        val = (txt.text() or "").strip()
        if not val:
            return ""
        if unit:
            return f"{val} {unit}"
        return val

    def _set_combo_value(self, combo_name, text_name, stored):
        if not hasattr(self, combo_name) or not hasattr(self, text_name):
            return
        combo = getattr(self, combo_name)
        txt = getattr(self, text_name)
        stored = (stored or "").strip()
        if not stored:
            txt.setText("")
            return
        parts = stored.split(" ")
        if len(parts) >= 2:
            val = " ".join(parts[:-1]).strip()
            unit = parts[-1].strip()
        else:
            val = stored
            unit = ""
        txt.setText(val)
        if unit:
            idx = combo.findText(unit)
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def _load_vize_surucu_values(self):
        mapping = {
            "vize_muayene": ("cmb_muayene", "txt_muayene"),
            "vize_sigorta": ("cmb_sigorta", "txt_sigorta"),
            "vize_koltuk": ("cmb_koltuk", "txt_koltuk"),
            "vize_kasko": ("cmb_kasko", "txt_kasko"),
            "surucu_src": ("cmb_src", "txt_src"),
            "surucu_psikoteknik": ("cmb_psikoteknik", "txt_psikoteknik"),
            "surucu_ehliyet": ("cmb_ehliyet", "txt_ehliyet"),
        }
        for group_name, (cmb, txt) in mapping.items():
            rows = self.db.get_constants(group_name)
            value = rows[0][1] if rows else ""
            self._set_combo_value(cmb, txt, value)

    def _save_vizeler(self):
        mapping = {
            "vize_muayene": ("cmb_muayene", "txt_muayene"),
            "vize_sigorta": ("cmb_sigorta", "txt_sigorta"),
            "vize_koltuk": ("cmb_koltuk", "txt_koltuk"),
            "vize_kasko": ("cmb_kasko", "txt_kasko"),
        }
        for group_name, (cmb, txt) in mapping.items():
            value = self._get_combo_value(cmb, txt)
            if value:
                self._upsert_single_constant(group_name, value)
            else:
                self._delete_group_constants(group_name)
        QMessageBox.information(self, "Bilgi", "Vize süreleri kaydedildi.")

    def _delete_vizeler(self):
        for group_name in ["vize_muayene", "vize_sigorta", "vize_koltuk", "vize_kasko"]:
            self._delete_group_constants(group_name)
        self._load_vize_surucu_values()
        QMessageBox.information(self, "Bilgi", "Vize süreleri silindi.")

    def _save_surucu(self):
        mapping = {
            "surucu_src": ("cmb_src", "txt_src"),
            "surucu_psikoteknik": ("cmb_psikoteknik", "txt_psikoteknik"),
            "surucu_ehliyet": ("cmb_ehliyet", "txt_ehliyet"),
        }
        for group_name, (cmb, txt) in mapping.items():
            value = self._get_combo_value(cmb, txt)
            if value:
                self._upsert_single_constant(group_name, value)
            else:
                self._delete_group_constants(group_name)
        QMessageBox.information(self, "Bilgi", "Sürücü belge süreleri kaydedildi.")

    def _delete_surucu(self):
        for group_name in ["surucu_src", "surucu_psikoteknik", "surucu_ehliyet"]:
            self._delete_group_constants(group_name)
        self._load_vize_surucu_values()
        QMessageBox.information(self, "Bilgi", "Sürücü belge süreleri silindi.")

    def _setup_belge_tanimlari_ui(self):
        if not hasattr(self, "table_belge_tanimlari"):
            return
        self.table_belge_tanimlari.setColumnCount(5)
        self.table_belge_tanimlari.setHorizontalHeaderLabels(["ID", "Kategori", "Belge Adı", "Süre", "Birim"])
        self.table_belge_tanimlari.hideColumn(0)
        if hasattr(self.table_belge_tanimlari, "horizontalHeader"):
            try:
                self.table_belge_tanimlari.horizontalHeader().setStretchLastSection(True)
            except Exception:
                pass

    def _belge_form_temizle(self):
        self._selected_belge_id = None
        if hasattr(self, "txt_belge_adi"):
            self.txt_belge_adi.setText("")
        if hasattr(self, "txt_belge_sure"):
            self.txt_belge_sure.setText("")
        if hasattr(self, "cmb_belge_birim"):
            self.cmb_belge_birim.setCurrentIndex(0)
        if hasattr(self, "cmb_belge_kategori"):
            self.cmb_belge_kategori.setCurrentIndex(0)

    def _belge_parse_value(self, value):
        value = (value or "").strip()
        parts = value.split("|")
        if len(parts) >= 4:
            kategori, ad, sure, birim = parts[0], parts[1], parts[2], parts[3]
            return kategori.strip(), ad.strip(), sure.strip(), birim.strip()
        return "", "", "", ""

    def _belge_build_value(self, kategori, ad, sure, birim):
        kategori = (kategori or "").strip()
        ad = (ad or "").strip()
        sure = (sure or "").strip()
        birim = (birim or "").strip()
        return f"{kategori}|{ad}|{sure}|{birim}"

    def _load_belge_tanimlari_table(self):
        if not hasattr(self, "table_belge_tanimlari"):
            return
        self.table_belge_tanimlari.setRowCount(0)
        rows = self.db.get_constants("belge_tanimlari")
        for r, (cid, value) in enumerate(rows):
            kategori, ad, sure, birim = self._belge_parse_value(value)
            self.table_belge_tanimlari.insertRow(r)
            self.table_belge_tanimlari.setItem(r, 0, QTableWidgetItem(str(cid)))
            self.table_belge_tanimlari.setItem(r, 1, QTableWidgetItem(kategori))
            self.table_belge_tanimlari.setItem(r, 2, QTableWidgetItem(ad))
            self.table_belge_tanimlari.setItem(r, 3, QTableWidgetItem(sure))
            self.table_belge_tanimlari.setItem(r, 4, QTableWidgetItem(birim))

    def _belge_on_select(self):
        if not hasattr(self, "table_belge_tanimlari"):
            return
        items = self.table_belge_tanimlari.selectedItems()
        if not items:
            return
        row = items[0].row()
        id_item = self.table_belge_tanimlari.item(row, 0)
        kat_item = self.table_belge_tanimlari.item(row, 1)
        ad_item = self.table_belge_tanimlari.item(row, 2)
        sure_item = self.table_belge_tanimlari.item(row, 3)
        birim_item = self.table_belge_tanimlari.item(row, 4)

        try:
            self._selected_belge_id = int(id_item.text()) if id_item else None
        except Exception:
            self._selected_belge_id = None

        if hasattr(self, "txt_belge_adi") and ad_item:
            self.txt_belge_adi.setText(ad_item.text())
        if hasattr(self, "txt_belge_sure") and sure_item:
            self.txt_belge_sure.setText(sure_item.text())
        if hasattr(self, "cmb_belge_kategori") and kat_item:
            idx = self.cmb_belge_kategori.findText(kat_item.text())
            if idx >= 0:
                self.cmb_belge_kategori.setCurrentIndex(idx)
        if hasattr(self, "cmb_belge_birim") and birim_item:
            idx = self.cmb_belge_birim.findText(birim_item.text())
            if idx >= 0:
                self.cmb_belge_birim.setCurrentIndex(idx)

    def _belge_ekle_or_guncelle(self):
        if not hasattr(self, "txt_belge_adi") or not hasattr(self, "txt_belge_sure"):
            return
        kategori = self.cmb_belge_kategori.currentText() if hasattr(self, "cmb_belge_kategori") else ""
        ad = (self.txt_belge_adi.text() or "").strip()
        sure = (self.txt_belge_sure.text() or "").strip()
        birim = self.cmb_belge_birim.currentText() if hasattr(self, "cmb_belge_birim") else ""

        if not ad:
            QMessageBox.warning(self, "Uyarı", "Belge adı boş olamaz.")
            return
        if not sure.isdigit():
            QMessageBox.warning(self, "Uyarı", "Süre sadece sayı olmalıdır.")
            return

        value = self._belge_build_value(kategori, ad, sure, birim)
        self.db.update_or_insert_constant("belge_tanimlari", value, constant_id=self._selected_belge_id)
        self._load_belge_tanimlari_table()
        self._belge_form_temizle()

    def _belge_sil(self):
        if not self._selected_belge_id:
            return
        msg = QMessageBox.question(
            self,
            "Onay",
            "Seçili belge tanımını silmek istediğinize emin misiniz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if msg == QMessageBox.StandardButton.Yes:
            self.db.delete_constant(self._selected_belge_id)
            self._load_belge_tanimlari_table()
            self._belge_form_temizle()

    def refresh_list(self, key):
        list_widget_name = self.ui_lists.get(key)
        if not list_widget_name or not hasattr(self, list_widget_name):
            return
        list_widget = getattr(self, list_widget_name)

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