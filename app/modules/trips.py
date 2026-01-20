import re
from datetime import datetime

from PyQt6 import uic
from PyQt6.QtCore import QDate, QTime, Qt

from PyQt6.QtGui import QColor, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHeaderView,
    QInputDialog,
    QMenu,
    QMessageBox,
    QTableWidgetItem,
    QWidget,
)

from app.core.db_manager import DatabaseManager
from config import get_ui_path
from app.utils.style_utils import clear_all_styles

class TripsGridApp(QWidget):
    def __init__(self, user_data=None, db_manager=None, parent=None):
        super().__init__(parent)
        uic.loadUi(get_ui_path("trips_grid_window.ui"), self)
        clear_all_styles(self)

        self.user_data = user_data or {}
        self.db = db_manager if db_manager else DatabaseManager()

        self._selected_contract_id = None
        self._selected_route_map = {}
        self._vehicle_map = {}
        self._driver_map = {}

        self._kalem_model = QStandardItemModel()
        if hasattr(self, "list_kalemler"):
            try:
                self.list_kalemler.setModel(self._kalem_model)
            except Exception:
                pass

        self._setup_tables()
        self._setup_connections()
        self._load_static_filters()
        self._load_customers()

    def _service_type_values(self, service_type: str):
        s = (service_type or "").strip().upper()
        if s in ("PERSONEL", "PERSONEL TAŞIMA"):
            return ["PERSONEL TAŞIMA", "PERSONEL"]
        if s in ("ÖĞRENCİ", "OGRENCI", "ÖĞRENCİ TAŞIMA", "OGRENCI TASIMA"):
            return ["ÖĞRENCİ TAŞIMA", "ÖĞRENCİ", "OGRENCI", "OGRENCI TASIMA"]
        return [service_type]

    def _load_vehicle_driver_maps(self):
        self._vehicle_map = {}
        self._driver_map = {}
        try:
            for vcode, plate in self.db.get_araclar_list(only_active=True) or []:
                self._vehicle_map[str(vcode)] = str(plate)
        except Exception:
            self._vehicle_map = {}
        try:
            for kod, ad in self.db.get_sofor_listesi() or []:
                self._driver_map[str(kod)] = str(ad)
        except Exception:
            self._driver_map = {}

    def _load_plan_map(self, contract_id: int, month: str, service_type: str):
        plan = {}
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT route_params_id, time_block, vehicle_id, driver_id, note
                FROM trip_plan
                WHERE contract_id = ? AND month = ? AND service_type = ?
                """,
                (int(contract_id), str(month), str(service_type)),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            rows = []
        for rid, tb, vid, did, note in rows:
            plan[(str(rid), str(tb or ""))] = {"vehicle_id": vid, "driver_id": did, "note": note}
        return plan

    def _parse_time(self, s: str):
        m = re.match(r"^(\d{1,2}):(\d{2})$", (s or "").strip())
        if not m:
            return None
        hh = int(m.group(1))
        mm = int(m.group(2))
        if hh < 0 or hh > 23 or mm < 0 or mm > 59:
            return None
        return hh, mm

    def _add_minutes(self, hh: int, mm: int, add_min: int) -> str:
        total = (hh * 60 + mm + int(add_min)) % (24 * 60)
        nh = total // 60
        nm = total % 60
        return f"{nh:02d}:{nm:02d}"

    def _apply_default_times_to_widgets(self):
        defaults = [
            ("time_g1", "08:00"),
            ("time_c1", "16:00"),
            ("time_g2", "08:15"),
            ("time_c2", "16:15"),
            ("time_g3", "00:00"),
            ("time_c3", "00:15"),
        ]
        for wname, tstr in defaults:
            w = getattr(self, wname, None)
            if w is None:
                continue
            try:
                if hasattr(w, "setTime"):
                    qt = QTime.fromString(tstr, "HH:mm")
                    if qt.isValid():
                        w.setTime(qt)
            except Exception:
                pass

    def _legacy_tb_to_times(self, tb: str):
        tbs = str(tb or "").strip().upper()
        m = re.match(r"^([GC])(\d)$", tbs)
        if not m:
            return None
        idx = int(m.group(2))
        gmap = {1: "08:00", 2: "08:15", 3: "00:00"}
        cmap = {1: "16:00", 2: "16:15", 3: "00:15"}
        if m.group(1) == "G":
            return gmap.get(idx, ""), ""
        return "", cmap.get(idx, "")

    def _delete_plan_for_context(self, contract_id: int, month: str, service_type: str):
        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM trip_plan
                WHERE contract_id = ? AND month = ? AND service_type = ?
                """,
                (int(contract_id), str(month), str(service_type)),
            )
            conn.commit()
        except Exception as e:
            try:
                if conn is not None:
                    conn.rollback()
            except Exception:
                pass
            QMessageBox.critical(self, "Hata", f"Silme hatası:\n{str(e)}")
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass

    # ------------------------- setup -------------------------
    def _setup_tables(self):
        if hasattr(self, "table_sefer"):
            self.table_sefer.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.table_sefer.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.table_sefer.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            self.table_sefer.setAlternatingRowColors(True)
            self.table_sefer.verticalHeader().setVisible(False)
            self.table_sefer.verticalHeader().setDefaultSectionSize(20)
            self.table_sefer.horizontalHeader().setHighlightSections(False)
            self.table_sefer.horizontalHeader().setStretchLastSection(False)
            
            headers = ["GÜZERGAH", "DURAKLAR", "GİRİŞ", "ÇIKIŞ", "ARAÇ PLAKA", "SÜRÜCÜ"]
            self.table_sefer.setColumnCount(len(headers))
            self.table_sefer.setHorizontalHeaderLabels(headers)

            h = self.table_sefer.horizontalHeader()
            h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            h.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

    def _setup_connections(self):
        if hasattr(self, "cmb_musteri"):
            self.cmb_musteri.currentIndexChanged.connect(self._on_customer_changed)
        if hasattr(self, "cmb_sozlesme"):
            self.cmb_sozlesme.currentIndexChanged.connect(self._on_contract_changed)
        if hasattr(self, "cmb_service_type"):
            self.cmb_service_type.currentIndexChanged.connect(self._reload_grid)

        if hasattr(self, "txt_kalem_sec"):
            try:
                self.txt_kalem_sec.textChanged.connect(self._apply_kalem_filter)
            except Exception:
                pass

        if hasattr(self, "list_kalemler") and self.list_kalemler.selectionModel() is not None:
            try:
                self.list_kalemler.selectionModel().selectionChanged.connect(self._on_kalem_selected)
            except Exception:
                pass

        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.clicked.connect(self._save_table_to_plan)
        if hasattr(self, "btn_satir_sil"):
            self.btn_satir_sil.clicked.connect(self._delete_selected_table_rows)
        if hasattr(self, "btn_delete_all"):
            self.btn_delete_all.clicked.connect(self._delete_all_table_rows)

    def _load_static_filters(self):
        if hasattr(self, "cmb_service_type"):
            self.cmb_service_type.blockSignals(True)
            self.cmb_service_type.clear()
            self.cmb_service_type.addItem("Seçiniz...", None)
            self.cmb_service_type.addItem("ÖĞRENCİ TAŞIMA", "ÖĞRENCİ TAŞIMA")
            self.cmb_service_type.addItem("PERSONEL TAŞIMA", "PERSONEL TAŞIMA")
            self.cmb_service_type.addItem("ARAÇ KİRALAMA", "ARAÇ KİRALAMA")
            self.cmb_service_type.addItem("DİĞER", "DİĞER")
            self.cmb_service_type.blockSignals(False)

    # ------------------------- data loading -------------------------
    def _ensure_route_params_table(self):
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

    def _load_customers(self):
        if not hasattr(self, "cmb_musteri"):
            return
        self.cmb_musteri.blockSignals(True)
        self.cmb_musteri.clear()
        self.cmb_musteri.addItem("Seçiniz...", None)
        rows = []
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
        self._selected_contract_id = None
        if hasattr(self, "cmb_sozlesme"):
            self.cmb_sozlesme.blockSignals(True)
            self.cmb_sozlesme.clear()
            self.cmb_sozlesme.addItem("Seçiniz...", None)
            cust_id = self.cmb_musteri.currentData() if hasattr(self, "cmb_musteri") else None
            if cust_id:
                try:
                    conn = self.db.connect()
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT id, contract_number, start_date, end_date
                        FROM contracts
                        WHERE customer_id = ? AND COALESCE(is_active,1)=1
                        ORDER BY start_date DESC
                        """,
                        (int(cust_id),),
                    )
                    rows = cursor.fetchall()
                    conn.close()
                except Exception:
                    rows = []
                for cid, cno, sdate, edate in rows:
                    label = f"{cno or ''} ({self._fmt_date_tr(sdate)} - {self._fmt_date_tr(edate)})"
                    self.cmb_sozlesme.addItem(label, cid)
            self.cmb_sozlesme.blockSignals(False)
        self._reload_grid()

    def _on_contract_changed(self):
        self._selected_contract_id = self.cmb_sozlesme.currentData() if hasattr(self, "cmb_sozlesme") else None
        self._reload_grid()

    def _fmt_date_tr(self, iso_date: str) -> str:
        s = (iso_date or "").strip()
        if not s:
            return ""
        d = QDate.fromString(s, "yyyy-MM-dd")
        if d.isValid():
            return d.toString("dd.MM.yyyy")
        return s

    def _month_key(self) -> str:
        d = QDate.currentDate()
        return d.toString("yyyy-MM")

    def _service_type(self):
        if not hasattr(self, "cmb_service_type"):
            return None
        return self.cmb_service_type.currentData()

    def _load_kalemler_from_contract(self, contract_id: int, service_type: str):
        """Yeni UI: list_kalemler içerisine route_params kayıtlarını yükler."""
        self._selected_route_map = {}
        self._kalem_model.clear()

        rows = []
        st_values = self._service_type_values(str(service_type))
        placeholders = ",".join(["?" for _ in st_values])
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            q = (
                "SELECT id, COALESCE(route_name,''), COALESCE(movement_type,''), stops, distance_km "
                "FROM route_params "
                f"WHERE contract_id = ? AND service_type IN ({placeholders}) AND COALESCE(route_name,'') <> '' "
                "ORDER BY id ASC"
            )
            cursor.execute(q, tuple([int(contract_id)] + [str(x) for x in st_values]))
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            rows = []

        for rid, rname, mtype, stops, km in rows:
            rid_s = str(rid)
            self._selected_route_map[rid_s] = {
                "route_name": (rname or ""),
                "movement_type": (mtype or ""),
                "stops": (stops or ""),
                "distance_km": km,
            }
            disp = f"{(rname or '').strip()} - {(mtype or '').strip()}" if (mtype or "").strip() else str(rname or "")
            it = QStandardItem(disp)
            it.setEditable(False)
            it.setData(rid_s, Qt.ItemDataRole.UserRole)
            self._kalem_model.appendRow(it)

        self._apply_kalem_filter()

    def _apply_kalem_filter(self):
        if not hasattr(self, "txt_kalem_sec"):
            return
        q = (self.txt_kalem_sec.text() or "").strip().lower()
        if not hasattr(self, "list_kalemler"):
            return

        # Not: QStandardItem.setEnabled(False) item'ı seçilemez yapar ve seçim "tutmuyor" gibi görünür.
        # Bu yüzden filtreleme için satır gizleme kullanıyoruz.
        for r in range(self._kalem_model.rowCount()):
            it = self._kalem_model.item(r)
            txt = (it.text() or "") if it is not None else ""
            hide = bool(q) and (q not in txt.lower())
            try:
                self.list_kalemler.setRowHidden(r, hide)
            except Exception:
                # Bazı widget tiplerinde setRowHidden olmayabilir; bu durumda filtre uygulamayalım.
                return

    def _selected_route_id(self):
        if not hasattr(self, "list_kalemler"):
            return None
        idxs = self.list_kalemler.selectedIndexes()
        if not idxs:
            return None
        it = self._kalem_model.itemFromIndex(idxs[0])
        if it is None:
            return None
        rid = it.data(Qt.ItemDataRole.UserRole)
        return (str(rid) if rid is not None else None)

    def _on_kalem_selected(self, *_args):
        if not self._selected_contract_id or not self._service_type():
            return
        route_id = self._selected_route_id()
        if not route_id:
            return

        rec = self._selected_route_map.get(str(route_id)) or {}
        route_name = str(rec.get("route_name") or "").strip()
        movement_type = str(rec.get("movement_type") or "").strip()
        stops_txt = str(rec.get("stops") or "")
        if not route_name:
            return

        # Not: list_kalemler seçimi korunur. Dialog kapanınca grid yenilenmez; sadece tabloya satır ekler/günceller.
        self._open_trips_dialog(route_id=str(route_id), route_name=route_name, movement_type=movement_type, stops_txt=stops_txt)

    def _open_trips_dialog(self, route_id: str, route_name: str, movement_type: str, stops_txt: str):
        dlg = QDialog(self)
        try:
            uic.loadUi(get_ui_path("trips_dialog.ui"), dlg)
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"trips_dialog.ui yüklenemedi:\n{str(e)}")
            return

        # Araç / sürücü listelerini doldur
        self._load_vehicle_driver_maps()
        cmb_arac = getattr(dlg, "cmb_arac_sec", None)
        cmb_sur = getattr(dlg, "cmb_surucu_sec", None)
        if cmb_arac is not None:
            cmb_arac.blockSignals(True)
            cmb_arac.clear()
            cmb_arac.addItem("Seçiniz...", None)
            for vcode, plate in self._vehicle_map.items():
                cmb_arac.addItem(plate, vcode)
            cmb_arac.blockSignals(False)
        if cmb_sur is not None:
            cmb_sur.blockSignals(True)
            cmb_sur.clear()
            cmb_sur.addItem("Seçiniz...", None)
            for did, name in self._driver_map.items():
                cmb_sur.addItem(name, did)
            cmb_sur.blockSignals(False)

        # Sefer tipleri (checkbox -> (giriş combo, çıkış combo))
        def _pair(chk: str, g: str, c: str):
            return (
                getattr(dlg, chk, None),
                getattr(dlg, g, None),
                getattr(dlg, c, None),
            )

        pairs = [
            _pair("chk_vardiya1", "cmb_vardiya1_g", "cmb_vardiya1_c"),
            _pair("chk_vardiya2", "cmb_vardiya2_g", "cmb_vardiya2_c"),
            _pair("chk_vardiya3", "cmb_vardiya3_g", "cmb_vardiya3_c"),
            _pair("chk_mesai1", "cmb_mesai1_g", "cmb_mesai1_c"),
            _pair("chk_mesai2", "cmb_mesai2_g", "cmb_mesai2_c"),
            _pair("chk_ek_sefer", "cmb_ek_sefer_g", "cmb_ek_sefer_c"),
        ]

        btn_kaydet = getattr(dlg, "btn_kaydet", None)
        if btn_kaydet is None:
            return

        def _add_or_update_row(time_in: str, time_out: str, vehicle_id, driver_id):
            if not hasattr(self, "table_sefer"):
                return
            table = self.table_sefer

            # Aynı route_id + time_in satırı varsa güncelle
            existing_row = None
            for r in range(table.rowCount()):
                it_meta = table.item(r, 1)
                if it_meta is None:
                    continue
                rid0 = it_meta.data(Qt.ItemDataRole.UserRole + 1)
                tb0 = it_meta.data(Qt.ItemDataRole.UserRole + 2)
                if str(rid0 or "") == str(route_id) and str(tb0 or "") == str(time_in):
                    existing_row = r
                    break

            rr = existing_row if existing_row is not None else table.rowCount()
            if existing_row is None:
                table.insertRow(rr)

            plate = self._vehicle_map.get(str(vehicle_id or ""), "")
            dname = self._driver_map.get(str(driver_id or ""), "")

            it_route = QTableWidgetItem(route_name)
            it_stops = QTableWidgetItem(str(stops_txt or ""))
            it_in = QTableWidgetItem(str(time_in or ""))
            it_out = QTableWidgetItem(str(time_out or ""))
            it_vehicle = QTableWidgetItem(str(plate or ""))
            it_driver = QTableWidgetItem(str(dname or ""))
            for it in (it_route, it_stops, it_in, it_out, it_vehicle, it_driver):
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)

            # meta: route_params_id / time_block / vehicle_id / driver_id / movement_type
            it_stops.setData(Qt.ItemDataRole.UserRole + 1, str(route_id))
            it_stops.setData(Qt.ItemDataRole.UserRole + 2, str(time_in))
            it_stops.setData(Qt.ItemDataRole.UserRole + 3, (None if vehicle_id in (None, "") else str(vehicle_id)))
            it_stops.setData(Qt.ItemDataRole.UserRole + 4, (None if driver_id in (None, "") else str(driver_id)))
            it_stops.setData(Qt.ItemDataRole.UserRole + 5, str(movement_type or ""))

            table.setItem(rr, 0, it_route)
            table.setItem(rr, 1, it_stops)
            table.setItem(rr, 2, it_in)
            table.setItem(rr, 3, it_out)
            table.setItem(rr, 4, it_vehicle)
            table.setItem(rr, 5, it_driver)

        def _on_save_clicked():
            vid = cmb_arac.currentData() if cmb_arac is not None else None
            did = cmb_sur.currentData() if cmb_sur is not None else None

            any_added = False
            for chk, cmb_g, cmb_c in pairs:
                if chk is None or not chk.isChecked():
                    continue
                if cmb_g is None or cmb_c is None:
                    continue
                tin = str(cmb_g.currentText() or "").strip()
                tout = str(cmb_c.currentText() or "").strip()
                if not tin:
                    continue
                _add_or_update_row(time_in=tin, time_out=tout, vehicle_id=vid, driver_id=did)
                any_added = True

            if not any_added:
                QMessageBox.information(dlg, "Bilgi", "Kaydedilecek sefer tipi seçiniz.")
                return
            dlg.accept()

        try:
            btn_kaydet.clicked.connect(_on_save_clicked)
        except Exception:
            pass

        dlg.exec()

    def _delete_selected_table_rows(self):
        if not hasattr(self, "table_sefer"):
            return
        rows = sorted({it.row() for it in self.table_sefer.selectedItems()}, reverse=True)
        if not rows:
            return
        for r in rows:
            self.table_sefer.removeRow(r)

    def _delete_all_table_rows(self):
        if not hasattr(self, "table_sefer"):
            return

        msg = QMessageBox.question(
            self,
            "Onay",
            "Tüm sefer satırları silinsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if msg != QMessageBox.StandardButton.Yes:
            return
        self.table_sefer.setRowCount(0)

        if self._selected_contract_id and self._service_type():
            self._delete_plan_for_context(
                contract_id=int(self._selected_contract_id),
                month=self._month_key(),
                service_type=str(self._service_type()),
            )

        self._reload_grid()

    def _save_table_to_plan(self):
        if not self._selected_contract_id or not self._service_type():
            QMessageBox.warning(self, "Uyarı", "Önce müşteri / sözleşme / tip seçiniz.")
            return
        if not hasattr(self, "table_sefer") or self.table_sefer.rowCount() == 0:
            QMessageBox.information(self, "Bilgi", "Kaydedilecek satır yok.")
            return

        contract_id = int(self._selected_contract_id)
        service_type = str(self._service_type())
        month = self._month_key()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()

            # Full sync: önce ilgili dönemin planını temizle, sonra tablodakileri yaz.
            cursor.execute(
                """
                DELETE FROM trip_plan
                WHERE contract_id = ? AND month = ? AND service_type = ?
                """,
                (contract_id, month, service_type),
            )

            for r in range(self.table_sefer.rowCount()):
                it_tb = self.table_sefer.item(r, 1)
                if it_tb is None:
                    continue

                rid = it_tb.data(Qt.ItemDataRole.UserRole + 1)
                tb = it_tb.data(Qt.ItemDataRole.UserRole + 2)
                vid = it_tb.data(Qt.ItemDataRole.UserRole + 3)
                did = it_tb.data(Qt.ItemDataRole.UserRole + 4)

                if not rid:
                    continue

                # time_block alanını saat formatında normalize et.
                tb_s = str(tb or "").strip()
                legacy = self._legacy_tb_to_times(tb_s)
                if legacy is not None:
                    tin, tout = legacy
                    tb_s = tin or tout
                if not tb_s:
                    continue

                cursor.execute(
                    """
                    INSERT INTO trip_plan (
                        contract_id, route_params_id, month, service_type, time_block,
                        vehicle_id, driver_id, note, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(contract_id, route_params_id, month, service_type, time_block)
                    DO UPDATE SET vehicle_id=excluded.vehicle_id, driver_id=excluded.driver_id, updated_at=excluded.updated_at
                    """,
                    (
                        contract_id,
                        int(rid),
                        month,
                        service_type,
                        str(tb_s),
                        (None if vid in (None, "") else str(vid)),
                        (None if did in (None, "") else str(did)),
                        None,
                        now,
                        now,
                    ),
                )
            conn.commit()
            QMessageBox.information(self, "Başarılı", "Sefer planı kaydedildi.")
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

        self._reload_grid()

    def _reload_grid(self):
        if not hasattr(self, "table_sefer"):
            return

        self._load_vehicle_driver_maps()

        contract_id = self._selected_contract_id
        service_type = self._service_type()
        month = self._month_key()

        self.table_sefer.setRowCount(0)
        self._selected_route_map = {}
        self._kalem_model.clear()

        if not contract_id or not service_type:
            return

        self._apply_default_times_to_widgets()

        # Kalem listesi
        self._load_kalemler_from_contract(int(contract_id), str(service_type))

        plan_map = self._load_plan_map(int(contract_id), month, str(service_type))
        if not plan_map:
            return

        def _tb_sort_key(tb_val: str):
            parsed = self._parse_time(str(tb_val or "").strip())
            if parsed is not None:
                hh, mm = parsed
                return hh * 60 + mm
            return 9999

        for (rid, tb), prec in sorted(plan_map.items(), key=lambda x: (int(x[0][0]), _tb_sort_key(x[0][1]))):
            rrec = self._selected_route_map.get(str(rid)) or {}
            route_name = str(rrec.get("route_name") or "")
            movement_type = str(rrec.get("movement_type") or "")
            stops_txt = str(rrec.get("stops") or "")
            vid = prec.get("vehicle_id")
            did = prec.get("driver_id")

            tin = str(tb or "")
            tout = ""
            legacy = self._legacy_tb_to_times(tin)
            if legacy is not None:
                tin, tout = legacy
            else:
                parsed = self._parse_time(tin)
                if parsed is not None:
                    hh, mm = parsed
                    tout = self._add_minutes(hh, mm, 15)

            plate = self._vehicle_map.get(str(vid or ""), "")
            dname = self._driver_map.get(str(did or ""), "")

            rr = self.table_sefer.rowCount()
            self.table_sefer.insertRow(rr)

            it_route = QTableWidgetItem(route_name)
            it_stops = QTableWidgetItem(stops_txt)
            it_in = QTableWidgetItem(tin)
            it_out = QTableWidgetItem(tout)
            it_v = QTableWidgetItem(plate)
            it_d = QTableWidgetItem(dname)
            for it in (it_route, it_stops, it_in, it_out, it_v, it_d):
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)

            it_stops.setData(Qt.ItemDataRole.UserRole + 1, str(rid))
            it_stops.setData(Qt.ItemDataRole.UserRole + 2, str(tb or ""))
            it_stops.setData(Qt.ItemDataRole.UserRole + 3, (None if vid is None else str(vid)))
            it_stops.setData(Qt.ItemDataRole.UserRole + 4, (None if did is None else str(did)))
            it_stops.setData(Qt.ItemDataRole.UserRole + 5, str(movement_type or ""))

            self.table_sefer.setItem(rr, 0, it_route)
            self.table_sefer.setItem(rr, 1, it_stops)
            self.table_sefer.setItem(rr, 2, it_in)
            self.table_sefer.setItem(rr, 3, it_out)
            self.table_sefer.setItem(rr, 4, it_v)
            self.table_sefer.setItem(rr, 5, it_d)
            it_route.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)