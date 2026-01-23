
import json
import re

from PyQt6 import uic
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QDialog, QHeaderView, QMessageBox, QTableWidgetItem, QWidget

from app.core.db_manager import DatabaseManager
from config import get_ui_path
from app.utils.style_utils import clear_all_styles


class RoutesApp(QWidget):
    def __init__(self, user_data=None, parent=None):
        super().__init__(parent)
        uic.loadUi(get_ui_path("routes_window.ui"), self)
        clear_all_styles(self)

        # Yeni UI'da tablo ismi table_rotalar. Eski kod table_rota bekliyor olabilir.
        if hasattr(self, "table_rotalar") and not hasattr(self, "table_rota"):
            try:
                self.table_rota = getattr(self, "table_rotalar")
            except Exception:
                pass

        self.db = DatabaseManager()
        self.user_data = user_data or {}

        self._selected_contract_id = None
        self._selected_contract_number = ""
        self._selected_contract_start = ""
        self._selected_contract_end = ""
        self._selected_contract_type = ""

        self._contract_route_km_map = {}

        self._opening_indibindi_dialog = False

        self._contract_model = QStandardItemModel(self)
        if hasattr(self, "list_sozlesme"):
            self.list_sozlesme.setModel(self._contract_model)

        self._kalem_model = QStandardItemModel(self)
        if hasattr(self, "list_kalemler"):
            self.list_kalemler.setModel(self._kalem_model)

        self._ensure_routes_table()
        self._init_tables()
        self._init_buttons()
        self._setup_connections()
        self._load_customers()

    def _ensure_routes_table(self):
        conn = None
        try:
            conn = self.db.connect()
            if conn is None:
                return
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS route_params (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contract_id INTEGER NOT NULL,
                    contract_number TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    service_type TEXT,
                    route_name TEXT,
                    movement_type TEXT,
                    start_point TEXT,
                    stops TEXT,
                    distance_km REAL,
                    created_at TEXT,
                    FOREIGN KEY (contract_id) REFERENCES contracts (id)
                )
                """
            )

            # migration: movement_type kolonu yoksa ekle
            try:
                cursor.execute("PRAGMA table_info(route_params)")
                cols = {row[1] for row in cursor.fetchall()}
                if "movement_type" not in cols:
                    cursor.execute("ALTER TABLE route_params ADD COLUMN movement_type TEXT")
            except Exception:
                pass
            conn.commit()
        except Exception:
            try:
                if conn is not None:
                    conn.rollback()
            except Exception:
                pass
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass

    def _init_tables(self):
        # Yeni UI tek tablo: table_rotalar (veya table_rota alias)
        if hasattr(self, "table_rotalar") or hasattr(self, "table_rota"):
            tbl = getattr(self, "table_rotalar", None) or getattr(self, "table_rota", None)
            if tbl is not None:
                if tbl.columnCount() != 4:
                    tbl.setColumnCount(4)
                tbl.setHorizontalHeaderLabels(
                    ["HİZMET TİPİ", "İŞ KALEMİ (HAT)", "DURAK NOKTALARI", "MESAFE (KM)"]
                )
                tbl.verticalHeader().setVisible(False)
                tbl.setAlternatingRowColors(True)
                tbl.setSelectionBehavior(tbl.SelectionBehavior.SelectRows)
                tbl.setSelectionMode(tbl.SelectionMode.ExtendedSelection)
                h = tbl.horizontalHeader()
                h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
                h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
                h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
                h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
                h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        if hasattr(self, "table_son"):
            if self.table_son.columnCount() != 7:
                self.table_son.setColumnCount(7)
            self.table_son.setHorizontalHeaderLabels(
                [
                    "Sözleşme",
                    "Başlangıç",
                    "Bitiş",
                    "Hizmet Türü",
                    "Güzergah",
                    "Noktalar",
                    "KM",
                ]
            )
            self.table_son.verticalHeader().setVisible(False)
            self.table_son.setAlternatingRowColors(True)
            self.table_son.setSelectionBehavior(self.table_son.SelectionBehavior.SelectRows)
            self.table_son.setSelectionMode(self.table_son.SelectionMode.ExtendedSelection)
            h2 = self.table_son.horizontalHeader()
            h2.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            h2.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            h2.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            h2.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            h2.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            h2.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            h2.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
            if self.table_son.columnCount() > 6:
                h2.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
            

    def _init_buttons(self):
        # Yeni UI: kullanıcı akışı EKLE/ÇIKAR ile tabloyu doldurur, KAYDET ile DB'ye yazar.
        # Butonları seçimlere göre dinamik kapatmak yerine handler içinde doğrulayacağız.
        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.setEnabled(True)
        if hasattr(self, "btn_sil"):
            self.btn_sil.setEnabled(True)

    def _setup_connections(self):
        if hasattr(self, "cmb_musteri"):
            self.cmb_musteri.currentIndexChanged.connect(self._on_customer_changed)
        if hasattr(self, "list_sozlesme") and self.list_sozlesme.selectionModel() is not None:
            self.list_sozlesme.selectionModel().selectionChanged.connect(self._on_contract_selected)
            # Bazı durumlarda selectionChanged tetiklenmeyebiliyor (ör. aynı item tekrar tıklama)
            # Bu yüzden clicked/activated ile de aynı handler'a düşüyoruz.
            try:
                self.list_sozlesme.clicked.connect(self._on_contract_clicked)
            except Exception:
                pass
            try:
                self.list_sozlesme.activated.connect(self._on_contract_clicked)
            except Exception:
                pass
        if hasattr(self, "btn_ekle"):
            self.btn_ekle.clicked.connect(self._add_selected_kalem_to_table)
        if hasattr(self, "btn_cikar"):
            self.btn_cikar.clicked.connect(self._remove_selected_rows_from_table)
        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.clicked.connect(self._save_table_rows)
        if hasattr(self, "btn_sil"):
            self.btn_sil.clicked.connect(self._delete_selected_rows_from_db)

        if hasattr(self, "list_kalemler") and self.list_kalemler.selectionModel() is not None:
            try:
                self.list_kalemler.selectionModel().selectionChanged.connect(self._on_kalem_selected)
            except Exception:
                pass

    def _on_contract_clicked(self, index):
        # clicked/activated sinyali ile geldiğinde, selection model bazen gecikmeli güncelleniyor.
        # Index üzerinden item'ı direkt alıp aynı akışı çalıştırıyoruz.
        try:
            item = self._contract_model.itemFromIndex(index)
        except Exception:
            item = None
        if item is None:
            return

        self._selected_contract_id = item.data(Qt.ItemDataRole.UserRole)
        self._selected_contract_number = item.data(Qt.ItemDataRole.UserRole + 1) or ""
        self._selected_contract_start = item.data(Qt.ItemDataRole.UserRole + 2) or ""
        self._selected_contract_end = item.data(Qt.ItemDataRole.UserRole + 3) or ""

        self._load_contract_details_and_fill_rota()
        self._load_saved_routes_into_table()
        self._load_kalemler_from_contract()
        # Yeni UI'da butonlar statik açık; tabloları/resetleri yaptık.

    def _load_customers(self):
        if not hasattr(self, "cmb_musteri"):
            return
        self.cmb_musteri.blockSignals(True)
        self.cmb_musteri.clear()
        self.cmb_musteri.addItem("Seçiniz...", None)
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, COALESCE(title,'') FROM customers WHERE is_active = 1 ORDER BY title COLLATE NOCASE"
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            rows = []
        for cid, title in rows:
            self.cmb_musteri.addItem(title or "", cid)
        self.cmb_musteri.blockSignals(False)

    def _on_customer_changed(self):
        cust_id = self.cmb_musteri.currentData() if hasattr(self, "cmb_musteri") else None
        self._selected_contract_id = None
        self._selected_contract_number = ""
        self._selected_contract_start = ""
        self._selected_contract_end = ""
        self._selected_contract_type = ""

        self._contract_model.clear()
        if hasattr(self, "table_rotalar"):
            self.table_rotalar.setRowCount(0)
        if hasattr(self, "table_rota"):
            self.table_rota.setRowCount(0)

        self._kalem_model.clear()

        if not cust_id:
            self._update_action_buttons()
            return

        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, contract_number, start_date, end_date
                FROM contracts
                WHERE customer_id = ?
                ORDER BY start_date DESC
                """,
                (int(cust_id),),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            rows = []

        for cid, number, start_date, end_date in rows:
            label = self._fmt_contract_label(number, start_date, end_date)
            item = QStandardItem(label)
            item.setEditable(False)
            item.setData(cid, Qt.ItemDataRole.UserRole)
            item.setData(number or "", Qt.ItemDataRole.UserRole + 1)
            item.setData(start_date or "", Qt.ItemDataRole.UserRole + 2)
            item.setData(end_date or "", Qt.ItemDataRole.UserRole + 3)
            self._contract_model.appendRow(item)

        self._update_action_buttons()

    def _fmt_date_tr(self, iso_date: str) -> str:
        s = (iso_date or "").strip()
        if not s:
            return ""
        d = QDate.fromString(s, "yyyy-MM-dd")
        if d.isValid():
            return d.toString("dd.MM.yyyy")
        return s

    def _fmt_contract_label(self, number: str, start_date: str, end_date: str) -> str:
        n = (number or "").strip()
        s = self._fmt_date_tr(start_date)
        e = self._fmt_date_tr(end_date)
        if s and e:
            return f"{n} ({s} - {e})"
        return n

    def _on_contract_selected(self, *_args):
        if not hasattr(self, "list_sozlesme"):
            return
        indexes = self.list_sozlesme.selectedIndexes()
        if not indexes:
            return
        idx = indexes[0]
        item = self._contract_model.itemFromIndex(idx)
        if item is None:
            return

        self._selected_contract_id = item.data(Qt.ItemDataRole.UserRole)
        self._selected_contract_number = item.data(Qt.ItemDataRole.UserRole + 1) or ""
        self._selected_contract_start = item.data(Qt.ItemDataRole.UserRole + 2) or ""
        self._selected_contract_end = item.data(Qt.ItemDataRole.UserRole + 3) or ""

        self._load_contract_details_and_fill_rota()
        self._load_saved_routes_into_table()
        self._load_kalemler_from_contract()

    def _table_rotalar_widget(self):
        return getattr(self, "table_rotalar", None) or getattr(self, "table_rota", None)

    def _load_kalemler_from_contract(self):
        """Seçili sözleşmedeki aday güzergahları list_kalemler'e yükler."""
        self._kalem_model.clear()
        if not self._selected_contract_id:
            return

        contract_id = int(self._selected_contract_id)
        contract_type = (self._selected_contract_type or "").strip()

        def _extract_movement_type(rec: dict) -> str:
            if not isinstance(rec, dict):
                return ""
            raw = (
                rec.get("gidis_gelis")
                or rec.get("movement_type")
                or rec.get("hareket_turu")
                or rec.get("hareket")
                or rec.get("hareketTuru")
                or rec.get("hareket_tipi")
                or rec.get("tip")
                or ""
            )
            return str(raw or "").strip()

        kalem_list = []
        inferred_mt_by_route = {}
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute("SELECT price_matrix_json FROM contracts WHERE id = ?", (contract_id,))
            row = cursor.fetchone()
            conn.close()
            price_json = row[0] if row else ""
            parsed = json.loads(price_json) if price_json else []
            if isinstance(parsed, list):
                for e in parsed:
                    guz = str((e or {}).get("guzergah") or "").strip()
                    hareket = _extract_movement_type(e or {})
                    km = (e or {}).get("km")
                    if guz:
                        kalem_list.append({"route_name": guz, "movement_type": hareket, "km": km})
                        if hareket:
                            k = guz.strip().lower()
                            inferred_mt_by_route.setdefault(k, set()).add(hareket.strip())
        except Exception:
            kalem_list = []

        if not kalem_list:
            try:
                conn = self.db.connect()
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT COALESCE(route_name,''), COALESCE(movement_type,'')
                    FROM route_params
                    WHERE contract_id = ?
                    ORDER BY id ASC
                    """,
                    (contract_id,),
                )
                rows = cursor.fetchall()
                conn.close()
                for rname, mtype in rows:
                    rn = str(rname or "").strip()
                    if rn:
                        kalem_list.append({"route_name": rn, "movement_type": str(mtype or "").strip(), "km": None})
            except Exception:
                kalem_list = []

        # Legacy düzeltme: route_params.movement_type boş ise ve sözleşme fiyat matrisinde
        # bu hat için tek bir hareket türü net şekilde varsa otomatik doldur.
        if inferred_mt_by_route:
            try:
                conn = self.db.connect()
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, COALESCE(route_name,''), COALESCE(movement_type,'')
                    FROM route_params
                    WHERE contract_id = ?
                    ORDER BY id ASC
                    """,
                    (contract_id,),
                )
                rp_rows = cursor.fetchall() or []
                updated = False
                for rid, rname, mtype in rp_rows:
                    rn = str(rname or "").strip()
                    mt = str(mtype or "").strip()
                    if not rn or mt:
                        continue
                    key = rn.lower()
                    mts = inferred_mt_by_route.get(key) or set()
                    if len(mts) == 1:
                        inferred = list(mts)[0]
                        cursor.execute(
                            "UPDATE route_params SET movement_type = ? WHERE id = ?",
                            (str(inferred), int(rid)),
                        )
                        updated = True
                if updated:
                    conn.commit()
                conn.close()

                # listeyi güncel DB verisiyle normalize etmek için mtype boş satırları tekrar oku
                if updated and not kalem_list:
                    pass
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass

        # (hat + hareket_türü) bazlı tekilleştirme (sıralama korunur)
        uniq = []
        seen = set()
        for k in kalem_list:
            rn = str((k or {}).get("route_name") or "").strip()
            mt = str((k or {}).get("movement_type") or "").strip()
            key = (rn.lower(), mt.lower())
            if not rn or key in seen:
                continue
            seen.add(key)
            uniq.append({"route_name": rn, "movement_type": mt, "km": (k or {}).get("km")})
        kalem_list = uniq

        def _norm_name(s: str) -> str:
            s2 = str(s or "").strip().casefold()
            s2 = re.sub(r"\s+", " ", s2)
            s2 = re.sub(r"[^0-9a-zA-ZğüşöçıİĞÜŞÖÇ]", "", s2)
            return s2

        existing_names = set()
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COALESCE(route_name,'')
                FROM route_params
                WHERE contract_id = ?
                """,
                (contract_id,),
            )
            for (rname,) in cursor.fetchall() or []:
                rn = _norm_name(str(rname or ""))
                if rn:
                    existing_names.add(rn)
            conn.close()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            existing_names = set()
        for k in kalem_list:
            rn = str((k or {}).get("route_name") or "").strip()
            mt = str((k or {}).get("movement_type") or "").strip()
            disp = f"{rn} - {mt}" if mt else rn
            it = QStandardItem(disp)
            it.setEditable(False)

            try:
                if _norm_name(rn) in existing_names:
                    it.setForeground(QColor(0, 128, 0))
                else:
                    it.setForeground(QColor(200, 0, 0))
            except Exception:
                pass
            it.setData(json.dumps({"route_name": rn, "movement_type": mt}, ensure_ascii=False), Qt.ItemDataRole.UserRole)
            it.setData(contract_type, Qt.ItemDataRole.UserRole + 1)  # hizmet tipi 1-A
            self._kalem_model.appendRow(it)

    def _on_kalem_selected(self, *_args):
        if self._opening_indibindi_dialog:
            return
        if not self._selected_contract_id:
            return
        if not hasattr(self, "list_kalemler"):
            return
        idxs = self.list_kalemler.selectedIndexes()
        if not idxs:
            return

        it = self._kalem_model.itemFromIndex(idxs[0])
        if it is None:
            return

        raw = (it.data(Qt.ItemDataRole.UserRole) or "")
        try:
            obj = json.loads(raw) if raw else {}
        except Exception:
            obj = {}
        kalem = str((obj or {}).get("route_name") or "").strip()
        movement_type = str((obj or {}).get("movement_type") or "").strip()
        if not kalem:
            return

        # Hizmet tipi: sözleşme tipinden (1-A akışı)
        stype = (self._selected_contract_type or "").strip()
        self._open_indibindi_dialog(route_name=kalem, movement_type=movement_type, service_type=stype)

    def _open_indibindi_dialog(self, route_name: str, movement_type: str, service_type: str):
        dlg = QDialog(self)
        try:
            uic.loadUi(get_ui_path("indibindi_dialog.ui"), dlg)
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"indibindi_dialog.ui yüklenemedi:\n{str(e)}")
            return

        # UI bindings
        lbl = getattr(dlg, "lbl_kalem_adi", None)
        txt = getattr(dlg, "txt_indi_bindi", None)
        btn_save = getattr(dlg, "btn_kaydet", None)
        btn_del = getattr(dlg, "btn_sil", None)

        if lbl is not None:
            try:
                disp = f"{route_name} - {movement_type}" if (movement_type or "").strip() else route_name
                lbl.setText(disp)
            except Exception:
                pass

        tbl = self._table_rotalar_widget()
        if tbl is None:
            return

        # Eğer tabloda satır varsa mevcut durakları dialoga bas
        existing_row = None
        existing_stops = ""
        for r in range(tbl.rowCount()):
            it1 = tbl.item(r, 1)
            rn = ""
            mv = ""
            if it1 is not None:
                rn = (it1.data(Qt.ItemDataRole.UserRole + 201) or "").strip() or (it1.text().strip())
                mv = (it1.data(Qt.ItemDataRole.UserRole + 202) or "").strip()
            it0 = tbl.item(r, 0)
            raw_st = ""
            if it0 is not None:
                raw_st = (it0.data(Qt.ItemDataRole.UserRole + 102) or "").strip()
            if not raw_st:
                raw_st = (it0.text().strip() if it0 is not None else "")

            # Aynı isimli iş kalemleri olabildiği için ilk eşleşmede durmayıp
            # en son (en güncel) eşleşen satırı seçiyoruz.
            if rn == route_name and mv == (movement_type or "").strip() and (not service_type or raw_st == (service_type or "").strip()):
                existing_row = r
                existing_stops = (tbl.item(r, 2).text() if tbl.item(r, 2) else "")

        if txt is not None:
            try:
                txt.setText(existing_stops or "")
                txt.setFocus()
            except Exception:
                pass

        def ensure_row():
            nonlocal existing_row
            if existing_row is not None:
                return existing_row
            r = tbl.rowCount()
            tbl.insertRow(r)
            raw_service_type = (service_type or "").strip()
            it0 = QTableWidgetItem(self._display_service_type(raw_service_type) or "")
            it0.setFlags(it0.flags() & ~Qt.ItemFlag.ItemIsEditable)
            disp = f"{route_name} - {movement_type}" if (movement_type or "").strip() else (route_name or "")
            it1 = QTableWidgetItem(disp)
            it1.setFlags(it1.flags() & ~Qt.ItemFlag.ItemIsEditable)
            it1.setData(Qt.ItemDataRole.UserRole + 201, (route_name or "").strip())
            it1.setData(Qt.ItemDataRole.UserRole + 202, (movement_type or "").strip())
            it2 = QTableWidgetItem("")
            it3 = QTableWidgetItem("")
            it3.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tbl.setItem(r, 0, it0)
            tbl.setItem(r, 1, it1)
            tbl.setItem(r, 2, it2)
            tbl.setItem(r, 3, it3)
            existing_row = r
            return r

        def do_save():
            stops = ""
            if txt is not None:
                try:
                    stops = (txt.text() or "").strip()
                except Exception:
                    stops = ""
            r = ensure_row()
            cell = tbl.item(r, 2)
            if cell is None:
                cell = QTableWidgetItem("")
                tbl.setItem(r, 2, cell)
            cell.setText(stops)
            dlg.accept()

        def do_delete():
            nonlocal existing_row
            if existing_row is not None:
                tbl.removeRow(existing_row)
                existing_row = None
            dlg.accept()

        if btn_save is not None:
            try:
                btn_save.clicked.connect(do_save)
            except Exception:
                pass
        if btn_del is not None:
            try:
                btn_del.clicked.connect(do_delete)
            except Exception:
                pass

        self._opening_indibindi_dialog = True
        try:
            dlg.exec()
        finally:
            self._opening_indibindi_dialog = False

    def _load_saved_routes_into_table(self):
        """Seçili sözleşme için route_params kayıtlarını table_rotalar'a yükler."""
        tbl = self._table_rotalar_widget()
        if tbl is None:
            return

        tbl.blockSignals(True)
        tbl.setRowCount(0)
        tbl.blockSignals(False)

        if not self._selected_contract_id:
            return

        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, COALESCE(service_type,''), COALESCE(route_name,''), COALESCE(movement_type,''), COALESCE(stops,''), distance_km
                FROM route_params
                WHERE contract_id = ?
                ORDER BY id ASC
                """,
                (int(self._selected_contract_id),),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            rows = []

        tbl.blockSignals(True)
        for rid, stype, rname, mtype, stops, km in rows:
            r = tbl.rowCount()
            tbl.insertRow(r)
            values = [stype or "", rname or "", stops or "", "" if km is None else str(km)]
            for c, v in enumerate(values):
                it = QTableWidgetItem(str(v))
                if c in (0, 1):
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 3:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if c == 0:
                    it.setData(Qt.ItemDataRole.UserRole + 101, int(rid))
                tbl.setItem(r, c, it)
        tbl.blockSignals(False)

    def _selected_kalem_texts(self):
        if not hasattr(self, "list_kalemler"):
            return []
        idxs = self.list_kalemler.selectedIndexes()
        out = []
        for idx in idxs:
            it = self._kalem_model.itemFromIndex(idx)
            if it is None:
                continue
            raw = it.data(Qt.ItemDataRole.UserRole)
            if raw:
                out.append(raw)
        return list(dict.fromkeys(out))

    def _add_selected_kalem_to_table(self):
        if not self._selected_contract_id:
            QMessageBox.warning(self, "Uyarı", "Önce müşteri ve sözleşme seçiniz.")
            return
        tbl = self._table_rotalar_widget()
        if tbl is None:
            return

        raw_stype = (self._selected_contract_type or "").strip()
        disp_stype = self._display_service_type(raw_stype)
        kalemler = self._selected_kalem_texts()
        if not kalemler:
            QMessageBox.information(self, "Bilgi", "EKLE için soldan en az 1 iş kalemi seçiniz.")
            return

        existing = set()
        for r in range(tbl.rowCount()):
            it1 = tbl.item(r, 1)
            rn = (it1.data(Qt.ItemDataRole.UserRole + 201) or "").strip() if it1 is not None else ""
            mv = (it1.data(Qt.ItemDataRole.UserRole + 202) or "").strip() if it1 is not None else ""
            if rn:
                existing.add((rn.lower(), mv.lower()))

        for raw in kalemler:
            try:
                obj = json.loads(raw) if raw else {}
            except Exception:
                obj = {}
            rn = str((obj or {}).get("route_name") or "").strip()
            mv = str((obj or {}).get("movement_type") or "").strip()
            if not rn:
                continue
            if (rn.lower(), mv.lower()) in existing:
                continue
            r = tbl.rowCount()
            tbl.insertRow(r)
            it0 = QTableWidgetItem(disp_stype)
            it0.setFlags(it0.flags() & ~Qt.ItemFlag.ItemIsEditable)
            disp = f"{rn} - {mv}" if (mv or "").strip() else rn
            it1 = QTableWidgetItem(disp)
            it1.setFlags(it1.flags() & ~Qt.ItemFlag.ItemIsEditable)
            it1.setData(Qt.ItemDataRole.UserRole + 201, rn)
            it1.setData(Qt.ItemDataRole.UserRole + 202, mv)
            it2 = QTableWidgetItem("")
            it3 = QTableWidgetItem("")
            it3.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tbl.setItem(r, 0, it0)
            tbl.setItem(r, 1, it1)
            tbl.setItem(r, 2, it2)
            tbl.setItem(r, 3, it3)

    def _remove_selected_rows_from_table(self):
        tbl = self._table_rotalar_widget()
        if tbl is None:
            return
        rows = sorted({it.row() for it in tbl.selectedItems()}, reverse=True)
        if not rows:
            return
        for r in rows:
            tbl.removeRow(r)

    def _save_table_rows(self):
        if not self._selected_contract_id:
            QMessageBox.warning(self, "Uyarı", "Önce müşteri ve sözleşme seçiniz.")
            return
        tbl = self._table_rotalar_widget()
        if tbl is None or tbl.rowCount() == 0:
            QMessageBox.information(self, "Bilgi", "Kaydedilecek satır yok.")
            return

        contract_id = int(self._selected_contract_id)
        now = QDate.currentDate().toString("yyyy-MM-dd")

        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            for r in range(tbl.rowCount()):
                rid = None
                it0 = tbl.item(r, 0)
                if it0 is not None:
                    rid = it0.data(Qt.ItemDataRole.UserRole + 101)

                it1 = tbl.item(r, 1)
                mtype = ""
                if it1 is not None:
                    try:
                        mtype = str(it1.data(Qt.ItemDataRole.UserRole + 202) or "").strip()
                    except Exception:
                        mtype = ""

                stype = (tbl.item(r, 0).text().strip() if tbl.item(r, 0) else "")
                rname = (tbl.item(r, 1).text().strip() if tbl.item(r, 1) else "")
                stops = (tbl.item(r, 2).text().strip() if tbl.item(r, 2) else "")
                km_txt = (tbl.item(r, 3).text().strip() if tbl.item(r, 3) else "")
                if not rname:
                    continue

                km_val = None
                try:
                    km_val = float(km_txt.replace(",", ".")) if km_txt else None
                except Exception:
                    km_val = None

                if rid:
                    cursor.execute(
                        """
                        UPDATE route_params
                        SET service_type = ?, route_name = ?, movement_type = ?, stops = ?, distance_km = ?
                        WHERE id = ?
                        """,
                        (stype, rname, (mtype or "").strip(), stops, km_val, int(rid)),
                    )
                else:
                    cursor.execute(
                        "SELECT contract_number, start_date, end_date FROM contracts WHERE id = ? LIMIT 1",
                        (contract_id,),
                    )
                    crow = cursor.fetchone() or ("", "", "")
                    cno, sdate, edate = crow[0] or "", crow[1] or "", crow[2] or ""
                    cursor.execute(
                        """
                        INSERT INTO route_params (
                            contract_id, contract_number, start_date, end_date,
                            service_type, route_name, movement_type, start_point, stops, distance_km,
                            created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (contract_id, cno, sdate, edate, stype, rname, (mtype or "").strip(), "", stops, km_val, now),
                    )
                    new_id = cursor.lastrowid
                    if it0 is not None and new_id:
                        it0.setData(Qt.ItemDataRole.UserRole + 101, int(new_id))

            conn.commit()
            QMessageBox.information(self, "Başarılı", "Kayıt tamamlandı.")
        except Exception as e:
            try:
                if conn is not None:
                    conn.rollback()
            except Exception:
                pass
            QMessageBox.critical(self, "Hata", f"Kayıt hatası:\n{str(e)}")
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass

        self._load_saved_routes_into_table()

    def _delete_selected_rows_from_db(self):
        tbl = self._table_rotalar_widget()
        if tbl is None:
            return

        selected_rows = sorted({it.row() for it in tbl.selectedItems()})
        if not selected_rows:
            return

        ids = []
        for r in selected_rows:
            it0 = tbl.item(r, 0)
            rid = it0.data(Qt.ItemDataRole.UserRole + 101) if it0 is not None else None
            if rid:
                ids.append(int(rid))

        if not ids:
            for r in sorted(selected_rows, reverse=True):
                tbl.removeRow(r)
            return

        msg = QMessageBox.question(
            self,
            "Onay",
            "Seçili kayıtlar DB'den silinsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if msg != QMessageBox.StandardButton.Yes:
            return

        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            for rid in ids:
                cursor.execute("DELETE FROM route_params WHERE id = ?", (rid,))
            conn.commit()
        except Exception as e:
            try:
                if conn is not None:
                    conn.rollback()
            except Exception:
                pass
            QMessageBox.critical(self, "Hata", f"Silme hatası:\n{str(e)}")
            return
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass

        self._load_saved_routes_into_table()

    def _load_contract_details_and_fill_rota(self):
        # Yeni UI (routes_window.ui) tek tablo: table_rotalar (4 kolon).
        # Eski akışta bu fonksiyon 5 kolonlu (başlangıç + durak + km) tabloyu dolduruyordu.
        # Yeni ekranda tablo formatı farklı olduğu için burada sadece sözleşme tipini yükleyip çıkıyoruz.
        if hasattr(self, "table_rotalar") and not hasattr(self, "table_son"):
            if not self._selected_contract_id:
                return
            try:
                conn = self.db.connect()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT contract_type FROM contracts WHERE id = ? LIMIT 1",
                    (int(self._selected_contract_id),),
                )
                row = cursor.fetchone()
                conn.close()
                self._selected_contract_type = ((row[0] or "").strip() if row else "")
            except Exception:
                self._selected_contract_type = ""
            self._contract_route_km_map = self._get_contract_route_km_map(int(self._selected_contract_id))
            return

        if not self._selected_contract_id or not hasattr(self, "table_rota"):
            return
        if self.table_rota.columnCount() < 5:
            self.table_rota.setColumnCount(5)
        self.table_rota.blockSignals(True)
        self.table_rota.setRowCount(0)
        self.table_rota.blockSignals(False)

        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT contract_type, price_matrix_json FROM contracts WHERE id = ?",
                (int(self._selected_contract_id),),
            )
            row = cursor.fetchone()
            conn.close()
        except Exception:
            row = None

        contract_type = ""
        price_json = ""
        if row:
            contract_type = (row[0] or "").strip()
            price_json = row[1] or ""
        self._selected_contract_type = contract_type

        guzergah_list = []
        try:
            parsed = json.loads(price_json) if price_json else []
            if isinstance(parsed, list):
                guzergah_list = parsed
        except Exception:
            guzergah_list = []

        if not guzergah_list:
            guzergah_list = self._fallback_rota_from_saved_routes(int(self._selected_contract_id), contract_type)

        saved_map = self._get_saved_route_details_map(int(self._selected_contract_id), contract_type)

        self.table_rota.blockSignals(True)
        for entry in guzergah_list:
            guz = str((entry or {}).get("guzergah") or "").strip()
            km = (entry or {}).get("km")
            sp = (entry or {}).get("_start_point") or ""
            stops = (entry or {}).get("_stops") or ""
            stype = (entry or {}).get("_service_type") or (entry or {}).get("service_type") or contract_type

            key = ((stype or contract_type or "").strip().lower(), (guz or "").strip().lower())
            saved = saved_map.get(key)
            if saved is not None:
                saved_sp, saved_stops, saved_km = saved
                if not sp:
                    sp = saved_sp or ""
                if not stops:
                    stops = saved_stops or ""
                if km is None and saved_km is not None:
                    km = saved_km
            r = self.table_rota.rowCount()
            self.table_rota.insertRow(r)
            values = [
                str(stype or ""),
                guz,
                str(sp or ""),
                str(stops or ""),
                ("" if km is None else str(km)),
            ]
            for c, v in enumerate(values):
                it = QTableWidgetItem(v)
                if c in (0, 1):
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 4:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table_rota.setItem(r, c, it)

        if self.table_rota.rowCount() == 0:
            self.table_rota.setRowCount(1)
            for c in range(self.table_rota.columnCount()):
                self.table_rota.setItem(0, c, QTableWidgetItem(""))
        self.table_rota.blockSignals(False)

    def _display_service_type(self, raw: str) -> str:
        s = (raw or "").strip()
        up = s.upper()
        if up in ("PERSONEL", "PERSONEL TAŞIMA", "PERSONEL TASIMA"):
            return "PERSONEL TAŞIMA"
        if up in ("ÖĞRENCİ", "OGRENCI", "ÖĞRENCİ TAŞIMA", "OGRENCI TASIMA"):
            return "ÖĞRENCİ TAŞIMA"
        if up in ("ARAÇ KİRALAMA", "ARAC KIRALAMA"):
            return "ARAÇ KİRALAMA"
        if up in ("DİĞER", "DIGER"):
            return "DİĞER"
        return s

    def _get_contract_route_km_map(self, contract_id: int) -> dict:
        """contracts.price_matrix_json içinden güzergah -> km map'i."""
        out = {}
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute("SELECT price_matrix_json FROM contracts WHERE id = ?", (int(contract_id),))
            row = cursor.fetchone()
            conn.close()
            price_json = row[0] if row else ""
            parsed = json.loads(price_json) if price_json else []
        except Exception:
            parsed = []

        if isinstance(parsed, list):
            for e in parsed:
                guz = str((e or {}).get("guzergah") or "").strip()
                km = (e or {}).get("km")
                if not guz:
                    continue
                if km is None or km == "":
                    continue
                out[guz.lower()] = km
        return out

    def _get_saved_route_details_map(self, contract_id: int, contract_type: str):
        details = {}
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT service_type, route_name, start_point, stops, distance_km
                FROM route_params
                WHERE contract_id = ?
                """,
                (int(contract_id),),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            rows = []

        for stype, rname, sp, st, km in rows:
            st_key = (stype or contract_type or "").strip().lower()
            rn_key = (rname or "").strip().lower()
            if not rn_key:
                continue
            details[(st_key, rn_key)] = ((sp or "").strip(), (st or "").strip(), km)

        return details

    def _fallback_rota_from_saved_routes(self, contract_id: int, contract_type: str):
        rows = []
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT route_name, start_point, stops, distance_km, service_type
                FROM route_params
                WHERE contract_id = ?
                ORDER BY id ASC
                """,
                (int(contract_id),),
            )
            db_rows = cursor.fetchall()
            conn.close()
        except Exception:
            db_rows = []

        for rname, sp, stops, km, stype in db_rows:
            rows.append(
                {
                    "guzergah": rname or "",
                    "km": km,
                    "_start_point": sp or "",
                    "_stops": stops or "",
                    "_service_type": (stype or contract_type or "").strip(),
                }
            )

        seen = set()
        unique = []
        for d in rows:
            key = (d.get("_service_type") or "", d.get("guzergah") or "")
            if key in seen:
                continue
            seen.add(key)
            unique.append(d)
        return unique

    def _load_saved_routes_for_contract(self):
        if not self._selected_contract_id or not hasattr(self, "table_son"):
            return

        if self.table_son.columnCount() < 7:
            self.table_son.setColumnCount(7)

        self.table_son.blockSignals(True)
        self.table_son.setRowCount(0)
        self.table_son.blockSignals(False)

        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, contract_number, start_date, end_date, service_type, route_name, start_point, stops, distance_km
                FROM route_params
                WHERE contract_id = ?
                ORDER BY id ASC
                """,
                (int(self._selected_contract_id),),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            rows = []

        for rid, cno, sdate, edate, stype, rname, sp, stops, km in rows:
            self._append_son_row(
                route_id=rid,
                contract_number=cno or self._selected_contract_number,
                start_date=sdate or self._selected_contract_start,
                end_date=edate or self._selected_contract_end,
                service_type=stype or "",
                route_name=rname or "",
                points=self._build_points(sp, stops),
                distance_km=km,
                pending=False,
            )

    def _build_points(self, start_point: str, stops: str) -> str:
        sp = (start_point or "").strip()
        st = (stops or "").strip()
        if sp and st:
            return f"{sp} | {st}"
        return sp or st

    def _son_key(self, contract_id, service_type, route_name):
        return (
            int(contract_id or 0),
            (service_type or "").strip().lower(),
            (route_name or "").strip().lower(),
        )

    def _existing_saved_keys(self):
        keys = set()
        if not self._selected_contract_id:
            return keys
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT service_type, route_name FROM route_params WHERE contract_id = ?",
                (int(self._selected_contract_id),),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            rows = []
        for st, rn in rows:
            keys.add(self._son_key(self._selected_contract_id, st, rn))
        return keys

    def _son_has_key(self, key_tuple) -> bool:
        if not hasattr(self, "table_son"):
            return False
        for r in range(self.table_son.rowCount()):
            stype = (self.table_son.item(r, 3).text().strip() if self.table_son.item(r, 3) else "")
            rname = (self.table_son.item(r, 4).text().strip() if self.table_son.item(r, 4) else "")
            if self._son_key(self._selected_contract_id, stype, rname) == key_tuple:
                return True
        return False

    def _pending_exists(self) -> bool:
        if not hasattr(self, "table_son"):
            return False
        for r in range(self.table_son.rowCount()):
            item0 = self.table_son.item(r, 0)
            if item0 is not None and bool(item0.data(Qt.ItemDataRole.UserRole + 100)):
                return True
        return False

    def _append_son_row(
        self,
        route_id,
        contract_number: str,
        start_date: str,
        end_date: str,
        service_type: str,
        route_name: str,
        points: str,
        distance_km,
        pending: bool,
    ):
        if not hasattr(self, "table_son"):
            return
        r = self.table_son.rowCount()
        self.table_son.insertRow(r)
        values = [
            contract_number,
            self._fmt_date_tr(start_date),
            self._fmt_date_tr(end_date),
            service_type,
            route_name,
            points,
            "" if distance_km is None else str(distance_km),
        ]
        for c, v in enumerate(values):
            it = QTableWidgetItem(v)
            if c in (0, 1, 2, 3, 4):
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if c == 5 and not pending:
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if c == 6:
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if not pending:
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            it.setForeground(QColor("red" if pending else "black"))
            if c == 0:
                it.setData(Qt.ItemDataRole.UserRole + 100, bool(pending))
                it.setData(Qt.ItemDataRole.UserRole + 101, route_id)
            self.table_son.setItem(r, c, it)

    def _add_to_son(self):
        if not self._selected_contract_id:
            QMessageBox.warning(self, "Uyarı", "Önce müşteri ve sözleşme seçiniz.")
            return
        if not hasattr(self, "table_rota") or not hasattr(self, "table_son"):
            return
        saved_keys = self._existing_saved_keys()
        selected_rows = sorted({it.row() for it in self.table_rota.selectedItems()})
        if not selected_rows:
            selected_rows = [self.table_rota.currentRow()] if self.table_rota.currentRow() >= 0 else []
        if not selected_rows:
            return
        for r in selected_rows:
            stype = (self.table_rota.item(r, 0).text().strip() if self.table_rota.item(r, 0) else "")
            rname = (self.table_rota.item(r, 1).text().strip() if self.table_rota.item(r, 1) else "")
            sp = (self.table_rota.item(r, 2).text().strip() if self.table_rota.item(r, 2) else "")
            stops = (self.table_rota.item(r, 3).text().strip() if self.table_rota.item(r, 3) else "")
            km_txt = (self.table_rota.item(r, 4).text().strip() if self.table_rota.item(r, 4) else "")
            if not rname:
                continue

            km_val = None
            try:
                km_val = float(km_txt.replace(",", ".")) if km_txt else None
            except Exception:
                km_val = None
            key = self._son_key(self._selected_contract_id, stype, rname)
            if key in saved_keys:
                continue
            if self._son_has_key(key):
                continue
            self._append_son_row(
                route_id=None,
                contract_number=self._selected_contract_number,
                start_date=self._selected_contract_start,
                end_date=self._selected_contract_end,
                service_type=stype,
                route_name=rname,
                points=self._build_points(sp, stops),
                distance_km=km_val,
                pending=True,
            )
        self._update_action_buttons()

    def _on_son_double_clicked(self, model_index):
        if not hasattr(self, "table_son"):
            return
        try:
            row = model_index.row()
        except Exception:
            row = -1
        if row < 0:
            return

        # Çift tık: satırı güncelleme moduna al (kırmızı/pending)
        item0 = self.table_son.item(row, 0)
        if item0 is None:
            return

        # Sadece mevcut kayıtlar için (siyah) edit moduna geçişte pending'e çekiyoruz.
        item0.setData(Qt.ItemDataRole.UserRole + 100, True)
        for c in range(self.table_son.columnCount()):
            it = self.table_son.item(row, c)
            if it is None:
                continue
            it.setForeground(QColor("red"))

        # NOKTALAR (col 5) editable olsun
        points_item = self.table_son.item(row, 5)
        if points_item is not None:
            points_item.setFlags(points_item.flags() | Qt.ItemFlag.ItemIsEditable)

        # KM (col 6) editable olsun (varsa)
        if self.table_son.columnCount() > 6:
            km_item = self.table_son.item(row, 6)
            if km_item is not None:
                km_item.setFlags(km_item.flags() | Qt.ItemFlag.ItemIsEditable)

        self._update_action_buttons()

    def _remove_from_son(self):
        if not hasattr(self, "table_son"):
            return
        selected = sorted({it.row() for it in self.table_son.selectedItems()}, reverse=True)
        if not selected:
            return
        for r in selected:
            item0 = self.table_son.item(r, 0)
            is_pending = bool(item0.data(Qt.ItemDataRole.UserRole + 100)) if item0 else False
            if is_pending:
                self.table_son.removeRow(r)
        self._update_action_buttons()

    def _update_action_buttons(self):
        # Yeni UI (routes_window.ui): pending tablosu (table_son) yok.
        # Bu ekranda KAYDET/SİL butonlarını pasife çekmeyelim; handler içinde doğrulama var.
        if hasattr(self, "table_rotalar") and not hasattr(self, "table_son"):
            if hasattr(self, "btn_kaydet"):
                self.btn_kaydet.setEnabled(True)
            if hasattr(self, "btn_sil"):
                self.btn_sil.setEnabled(True)
            return

        pending = self._pending_exists()
        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.setEnabled(pending)
        if hasattr(self, "btn_sil"):
            self.btn_sil.setEnabled(pending)

    def _save_pending(self):
        if not self._selected_contract_id or not hasattr(self, "table_son"):
            return
        pending_rows = []
        for r in range(self.table_son.rowCount()):
            item0 = self.table_son.item(r, 0)
            if item0 is not None and bool(item0.data(Qt.ItemDataRole.UserRole + 100)):
                pending_rows.append(r)
        if not pending_rows:
            self._update_action_buttons()
            return
        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            for r in pending_rows:
                id_item = self.table_son.item(r, 0)
                route_id = id_item.data(Qt.ItemDataRole.UserRole + 101) if id_item is not None else None
                service_type = self.table_son.item(r, 3).text().strip() if self.table_son.item(r, 3) else ""
                route_name = self.table_son.item(r, 4).text().strip() if self.table_son.item(r, 4) else ""
                points = self.table_son.item(r, 5).text().strip() if self.table_son.item(r, 5) else ""
                km_txt = (
                    self.table_son.item(r, 6).text().strip()
                    if self.table_son.columnCount() > 6 and self.table_son.item(r, 6)
                    else ""
                )
                km_val = None
                try:
                    km_val = float(km_txt.replace(",", ".")) if km_txt else None
                except Exception:
                    km_val = None
                start_point = points
                stops = ""
                if "|" in points:
                    parts = [p.strip() for p in points.split("|", 1)]
                    start_point = parts[0] if parts else ""
                    stops = parts[1] if len(parts) > 1 else ""
                if route_id:
                    cursor.execute(
                        """
                        UPDATE route_params
                        SET service_type = ?, route_name = ?, start_point = ?, stops = ?, distance_km = ?
                        WHERE id = ?
                        """,
                        (
                            service_type,
                            route_name,
                            start_point,
                            stops,
                            km_val,
                            int(route_id),
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO route_params (
                            contract_id, contract_number, start_date, end_date,
                            service_type, route_name, start_point, stops, distance_km,
                            created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            int(self._selected_contract_id),
                            self._selected_contract_number,
                            self._selected_contract_start,
                            self._selected_contract_end,
                            service_type,
                            route_name,
                            start_point,
                            stops,
                            km_val,
                            QDate.currentDate().toString("yyyy-MM-dd"),
                        ),
                    )
                    new_id = cursor.lastrowid
                    if id_item is not None:
                        id_item.setData(Qt.ItemDataRole.UserRole + 101, new_id)
            conn.commit()
            for r in pending_rows:
                item0 = self.table_son.item(r, 0)
                if item0 is not None:
                    item0.setData(Qt.ItemDataRole.UserRole + 100, False)
                for c in range(self.table_son.columnCount()):
                    it = self.table_son.item(r, c)
                    if it is not None:
                        it.setForeground(QColor("black"))
            QMessageBox.information(self, "Başarılı", "Rota satırları kaydedildi.")
        except Exception as e:
            try:
                if conn is not None:
                    conn.rollback()
            except Exception:
                pass
            QMessageBox.critical(self, "Hata", f"Kayıt hatası:\n{str(e)}")
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass

        self._update_action_buttons()

    def _delete_pending(self):
        if not hasattr(self, "table_son"):
            return

        selected_rows = sorted({it.row() for it in self.table_son.selectedItems()})
        if not selected_rows:
            self._update_action_buttons()
            return

        msg = QMessageBox.question(
            self,
            "Onay",
            "Seçili satırlar silinsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if msg != QMessageBox.StandardButton.Yes:
            return

        ids_to_delete = []
        for r in selected_rows:
            item0 = self.table_son.item(r, 0)
            if item0 is None:
                continue
            rid = item0.data(Qt.ItemDataRole.UserRole + 101)
            if rid:
                ids_to_delete.append(int(rid))

        if ids_to_delete:
            conn = None
            try:
                conn = self.db.connect()
                cursor = conn.cursor()
                for rid in ids_to_delete:
                    cursor.execute("DELETE FROM route_params WHERE id = ?", (rid,))
                conn.commit()
            except Exception as e:
                try:
                    if conn is not None:
                        conn.rollback()
                except Exception:
                    pass
                QMessageBox.critical(self, "Hata", f"Silme hatası:\n{str(e)}")
                return
            finally:
                try:
                    if conn is not None:
                        conn.close()
                except Exception:
                    pass

        for r in sorted(selected_rows, reverse=True):
            self.table_son.removeRow(r)

        self._update_action_buttons()

    def closeEvent(self, event):
        if self._pending_exists():
            msg = QMessageBox.question(
                self,
                "Uyarı",
                "Kaydedilmemiş (kırmızı) rota satırları var. Çıkmak istiyor musunuz?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if msg != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()
