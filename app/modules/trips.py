import re
from datetime import datetime

from PyQt6 import uic
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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

        self._ensure_route_params_table()
        self._setup_tables()
        self._setup_connections()
        self._load_static_filters()
        self._load_customers()

    # ------------------------- setup -------------------------
    def _setup_tables(self):
        if hasattr(self, "tbl_grid"):
            self.tbl_grid.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.tbl_grid.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
            self.tbl_grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            self.tbl_grid.setAlternatingRowColors(True)
            self.tbl_grid.verticalHeader().setVisible(False)
            self.tbl_grid.horizontalHeader().setHighlightSections(False)
            self.tbl_grid.horizontalHeader().setStretchLastSection(False)

        if hasattr(self, "tbl_alloc"):
            self.tbl_alloc.setAlternatingRowColors(True)
            self.tbl_alloc.verticalHeader().setVisible(False)
            self.tbl_alloc.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.tbl_alloc.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            self.tbl_alloc.setColumnCount(4)
            self.tbl_alloc.setHorizontalHeaderLabels(["Güzergah", "Saat", "Araç", "Şoför"])
            h = self.tbl_alloc.horizontalHeader()
            h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

    def _setup_connections(self):
        if hasattr(self, "cmb_musteri"):
            self.cmb_musteri.currentIndexChanged.connect(self._on_customer_changed)
        if hasattr(self, "cmb_sozlesme"):
            self.cmb_sozlesme.currentIndexChanged.connect(self._on_contract_changed)
        if hasattr(self, "cmb_service_type"):
            self.cmb_service_type.currentIndexChanged.connect(self._reload_grid)
        if hasattr(self, "date_month"):
            self.date_month.dateChanged.connect(self._reload_grid)

        if hasattr(self, "btn_reload"):
            self.btn_reload.clicked.connect(self._reload_grid)
        if hasattr(self, "btn_save"):
            self.btn_save.clicked.connect(self._save_from_alloc_table)
        if hasattr(self, "btn_close"):
            self.btn_close.clicked.connect(self.close)
        if hasattr(self, "btn_lock_period"):
            self.btn_lock_period.clicked.connect(self._toggle_lock)

        if hasattr(self, "btn_alloc_add"):
            self.btn_alloc_add.clicked.connect(lambda: self._alloc_from_selection(append=True))
        if hasattr(self, "btn_alloc_del"):
            self.btn_alloc_del.clicked.connect(self._alloc_clear_selected_rows)
        if hasattr(self, "btn_alloc_save"):
            self.btn_alloc_save.clicked.connect(self._save_from_alloc_table)

        if hasattr(self, "btn_apply_default_to_selection"):
            self.btn_apply_default_to_selection.clicked.connect(self._apply_defaults_to_selection)

        if hasattr(self, "btn_note_save"):
            self.btn_note_save.clicked.connect(self._save_note)
        if hasattr(self, "btn_note_clear"):
            self.btn_note_clear.clicked.connect(self._clear_note)

        if hasattr(self, "tbl_grid"):
            self.tbl_grid.itemSelectionChanged.connect(self._on_grid_selection_changed)
            self.tbl_grid.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.tbl_grid.horizontalHeader().customContextMenuRequested.connect(self._open_grid_header_menu)

    def _load_static_filters(self):
        if hasattr(self, "cmb_period"):
            self.cmb_period.blockSignals(True)
            self.cmb_period.clear()
            self.cmb_period.addItem("Seçiniz...", None)
            self.cmb_period.addItem("Aylık", "monthly")
            self.cmb_period.setCurrentIndex(1)
            self.cmb_period.setEnabled(False)
            self.cmb_period.blockSignals(False)

        if hasattr(self, "date_month"):
            self.date_month.setCalendarPopup(True)
            self.date_month.setDate(QDate.currentDate())

        if hasattr(self, "cmb_service_type"):
            self.cmb_service_type.blockSignals(True)
            self.cmb_service_type.clear()
            self.cmb_service_type.addItem("Seçiniz...", None)
            self.cmb_service_type.addItem("ÖĞRENCİ", "ÖĞRENCİ")
            self.cmb_service_type.addItem("PERSONEL", "PERSONEL")
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
                    start_point TEXT,
                    stops TEXT,
                    distance_km REAL,
                    created_at TEXT,
                    FOREIGN KEY (contract_id) REFERENCES contracts (id)
                )
                """
            )
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
        if hasattr(self, "date_month"):
            d = self.date_month.date()
        else:
            d = QDate.currentDate()
        return d.toString("yyyy-MM")

    def _service_type(self):
        if not hasattr(self, "cmb_service_type"):
            return None
        return self.cmb_service_type.currentData()

    def _load_vehicle_driver_maps(self):
        self._vehicle_map = {}
        self._driver_map = {}

        prev_default_vehicle = None
        prev_default_driver = None
        if hasattr(self, "cmb_default_vehicle"):
            prev_default_vehicle = self.cmb_default_vehicle.currentData()
        if hasattr(self, "cmb_default_driver"):
            prev_default_driver = self.cmb_default_driver.currentData()

        try:
            for vcode, plate in self.db.get_araclar_list(only_active=True):
                self._vehicle_map[str(vcode)] = str(plate)
        except Exception:
            self._vehicle_map = {}

        try:
            for kod, ad in self.db.get_sofor_listesi():
                self._driver_map[str(kod)] = str(ad)
        except Exception:
            self._driver_map = {}

        if hasattr(self, "cmb_default_vehicle"):
            self.cmb_default_vehicle.blockSignals(True)
            self.cmb_default_vehicle.clear()
            self.cmb_default_vehicle.addItem("Seçiniz...", None)
            for vcode, plate in self._vehicle_map.items():
                self.cmb_default_vehicle.addItem(plate, vcode)
            if prev_default_vehicle:
                idx = self.cmb_default_vehicle.findData(str(prev_default_vehicle))
                if idx >= 0:
                    self.cmb_default_vehicle.setCurrentIndex(idx)
            self.cmb_default_vehicle.blockSignals(False)

        if hasattr(self, "cmb_default_driver"):
            self.cmb_default_driver.blockSignals(True)
            self.cmb_default_driver.clear()
            self.cmb_default_driver.addItem("Seçiniz...", None)
            for did, name in self._driver_map.items():
                self.cmb_default_driver.addItem(name, did)
            if prev_default_driver:
                idx = self.cmb_default_driver.findData(str(prev_default_driver))
                if idx >= 0:
                    self.cmb_default_driver.setCurrentIndex(idx)
            self.cmb_default_driver.blockSignals(False)

    def _fixed_time_blocks(self):
        return ["08:00", "08:15", "16:00", "16:15", "00:00", "00:15"]

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
        total = (hh * 60 + mm + add_min) % (24 * 60)
        nh = total // 60
        nm = total % 60
        return f"{nh:02d}:{nm:02d}"

    def _get_custom_times(self, contract_id: int, month: str, service_type: str):
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT custom1, custom2
                FROM trip_time_blocks
                WHERE contract_id = ? AND month = ? AND service_type = ?
                LIMIT 1
                """,
                (int(contract_id), month, service_type),
            )
            row = cursor.fetchone()
            conn.close()
        except Exception:
            row = None
        if not row:
            return None, None
        return (row[0] or "").strip(), (row[1] or "").strip()

    def _set_custom_times(self, contract_id: int, month: str, service_type: str, custom1: str, custom2: str):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trip_time_blocks (contract_id, month, service_type, custom1, custom2, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(contract_id, month, service_type)
                DO UPDATE SET custom1=excluded.custom1, custom2=excluded.custom2, updated_at=excluded.updated_at
                """,
                (int(contract_id), month, service_type, custom1, custom2, now, now),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Özel saatler kaydedilemedi:\n{str(e)}")

    def _time_blocks_for_context(self, contract_id: int, month: str, service_type: str):
        blocks = list(self._fixed_time_blocks())
        c1, c2 = self._get_custom_times(contract_id, month, service_type)
        for ct in [c1, c2]:
            parsed = self._parse_time(ct)
            if parsed is None:
                blocks.extend(["", ""])
            else:
                hh, mm = parsed
                blocks.append(f"{hh:02d}:{mm:02d}")
                blocks.append(self._add_minutes(hh, mm, 15))
        return blocks

    def _header_labels_for_time_blocks(self, time_blocks):
        labels = []
        special_index = 0
        for tb in time_blocks:
            if tb:
                labels.append(tb)
                continue
            special_index += 1
            if special_index == 1:
                labels.append("ÖZEL 1")
            elif special_index == 2:
                labels.append("ÖZEL 1+15")
            elif special_index == 3:
                labels.append("ÖZEL 2")
            elif special_index == 4:
                labels.append("ÖZEL 2+15")
            else:
                labels.append("ÖZEL")
        return labels

    def _load_routes_for_contract(self, contract_id: int, service_type: str):
        self._selected_route_map = {}
        rows = []
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, route_name, distance_km
                FROM route_params
                WHERE contract_id = ? AND COALESCE(route_name,'') <> '' AND service_type = ?
                ORDER BY id ASC
                """,
                (int(contract_id), service_type),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            rows = []
        for rid, rname, km in rows:
            self._selected_route_map[str(rid)] = {"route_name": rname or "", "distance_km": km}
        return list(self._selected_route_map.items())

    def _is_locked(self, contract_id: int, month: str, service_type: str) -> bool:
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT locked
                FROM trip_period_lock
                WHERE contract_id = ? AND month = ? AND service_type = ?
                LIMIT 1
                """,
                (int(contract_id), month, service_type),
            )
            row = cursor.fetchone()
            conn.close()
        except Exception:
            row = None
        if not row:
            return False
        try:
            return int(row[0] or 0) == 1
        except Exception:
            return False

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
                (int(contract_id), month, service_type),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            rows = []
        for rid, tb, vid, did, note in rows:
            plan[(str(rid), str(tb or ""))] = {"vehicle_id": vid, "driver_id": did, "note": note}
        return plan

    def _reload_grid(self):
        if not hasattr(self, "tbl_grid"):
            return
        self._load_vehicle_driver_maps()

        contract_id = self._selected_contract_id
        service_type = self._service_type()
        month = self._month_key()

        self.tbl_grid.clear()
        self.tbl_grid.setRowCount(0)
        self.tbl_grid.setColumnCount(0)
        if hasattr(self, "tbl_alloc"):
            self.tbl_alloc.setRowCount(0)
        if hasattr(self, "txt_note"):
            self.txt_note.setPlainText("")

        if not contract_id or not service_type:
            self._apply_lock_ui(False)
            return

        routes = self._load_routes_for_contract(int(contract_id), str(service_type))
        if not routes:
            self._apply_lock_ui(False)
            return

        time_blocks = self._time_blocks_for_context(int(contract_id), month, str(service_type))
        headers = ["NO", "GÜZERGAH", "KM"] + self._header_labels_for_time_blocks(time_blocks)
        self.tbl_grid.setColumnCount(len(headers))
        self.tbl_grid.setHorizontalHeaderLabels(headers)
        self.tbl_grid.setRowCount(len(routes))

        h = self.tbl_grid.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        for c in range(3, len(headers)):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

        plan_map = self._load_plan_map(int(contract_id), month, str(service_type))
        for r, (route_id, meta) in enumerate(routes):
            route_name = meta.get("route_name") or ""
            km = meta.get("distance_km")

            it_no = QTableWidgetItem(str(r + 1))
            it_no.setFlags(it_no.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_grid.setItem(r, 0, it_no)

            it_route = QTableWidgetItem(route_name)
            it_route.setFlags(it_route.flags() & ~Qt.ItemFlag.ItemIsEditable)
            it_route.setData(Qt.ItemDataRole.UserRole + 1, str(route_id))
            self.tbl_grid.setItem(r, 1, it_route)

            it_km = QTableWidgetItem("" if km is None else str(km))
            it_km.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            it_km.setFlags(it_km.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_grid.setItem(r, 2, it_km)

            for ci, tb in enumerate(time_blocks):
                c = 3 + ci
                display = ""
                rec = plan_map.get((str(route_id), tb))
                if rec is not None:
                    plate = self._vehicle_map.get(str(rec.get("vehicle_id") or ""), "")
                    dname = self._driver_map.get(str(rec.get("driver_id") or ""), "")
                    if plate or dname:
                        display = f"{plate}\n{dname}".strip()

                cell = QTableWidgetItem(display)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                cell.setData(Qt.ItemDataRole.UserRole + 1, str(route_id))
                cell.setData(Qt.ItemDataRole.UserRole + 2, tb)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if not tb:
                    cell.setBackground(QColor(245, 245, 245))
                self.tbl_grid.setItem(r, c, cell)

        locked = self._is_locked(int(contract_id), month, str(service_type))
        self._apply_lock_ui(locked)

    # ------------------------- header menu (custom times) -------------------------
    def _open_grid_header_menu(self, pos):
        if not self._selected_contract_id:
            return
        service_type = self._service_type()
        if not service_type:
            return
        menu = QMenu(self)
        act = menu.addAction("Özel Saatleri Ayarla")
        chosen = menu.exec(self.tbl_grid.horizontalHeader().mapToGlobal(pos))
        if chosen != act:
            return

        month = self._month_key()
        c1, c2 = self._get_custom_times(int(self._selected_contract_id), month, str(service_type))
        v1, ok1 = QInputDialog.getText(self, "Özel Saat 1", "HH:MM", text=(c1 or ""))
        if not ok1:
            return
        v2, ok2 = QInputDialog.getText(self, "Özel Saat 2", "HH:MM", text=(c2 or ""))
        if not ok2:
            return
        v1 = (v1 or "").strip()
        v2 = (v2 or "").strip()
        if v1 and self._parse_time(v1) is None:
            QMessageBox.warning(self, "Uyarı", "Özel Saat 1 formatı geçersiz (HH:MM).")
            return
        if v2 and self._parse_time(v2) is None:
            QMessageBox.warning(self, "Uyarı", "Özel Saat 2 formatı geçersiz (HH:MM).")
            return
        self._set_custom_times(int(self._selected_contract_id), month, str(service_type), v1, v2)
        self._reload_grid()

    # ------------------------- selection -> alloc -------------------------
    def _selected_grid_cells(self):
        if not hasattr(self, "tbl_grid"):
            return []
        cells = []
        for it in self.tbl_grid.selectedItems():
            r, c = it.row(), it.column()
            if c < 3:
                continue
            route_id = it.data(Qt.ItemDataRole.UserRole + 1)
            time_block = it.data(Qt.ItemDataRole.UserRole + 2)
            if route_id is None:
                continue
            tb = str(time_block or "")
            if not tb:
                continue
            cells.append((r, c, str(route_id), tb))

        uniq = []
        seen = set()
        for x in cells:
            key = (x[2], x[3])
            if key in seen:
                continue
            seen.add(key)
            uniq.append(x)
        return uniq

    def _alloc_from_selection(self, append: bool = False):
        if self._is_current_locked():
            QMessageBox.information(self, "Bilgi", "Bu dönem kilitli. Değişiklik yapılamaz.")
            return
        if not hasattr(self, "tbl_alloc"):
            return

        cells = self._selected_grid_cells()
        if not cells:
            QMessageBox.information(self, "Bilgi", "EKLE için grid'den en az 1 hücre seçiniz.")
            self._refresh_note_from_selection()
            return

        if not append:
            self.tbl_alloc.setRowCount(0)
        else:
            existing = set()
            for r in range(self.tbl_alloc.rowCount()):
                it = self.tbl_alloc.item(r, 0)
                rid = it.data(Qt.ItemDataRole.UserRole + 1) if it else None
                tb = it.data(Qt.ItemDataRole.UserRole + 2) if it else None
                if rid and tb:
                    existing.add((str(rid), str(tb)))
            cells = [c for c in cells if (c[2], c[3]) not in existing]
            if not cells:
                QMessageBox.information(self, "Bilgi", "Seçili hücreler zaten atama tablosunda.")
                self._refresh_note_from_selection()
                return

        plan_map = None
        if self._selected_contract_id and self._service_type():
            plan_map = self._load_plan_map(
                int(self._selected_contract_id), self._month_key(), str(self._service_type())
            )

        for _r, _c, route_id, tb in cells:
            row = self.tbl_alloc.rowCount()
            self.tbl_alloc.insertRow(row)

            route_name = self._selected_route_map.get(str(route_id), {}).get("route_name", "")
            it_route = QTableWidgetItem(route_name)
            it_route.setFlags(it_route.flags() & ~Qt.ItemFlag.ItemIsEditable)
            it_route.setData(Qt.ItemDataRole.UserRole + 1, str(route_id))
            it_route.setData(Qt.ItemDataRole.UserRole + 2, tb)
            self.tbl_alloc.setItem(row, 0, it_route)

            it_tb = QTableWidgetItem(tb)
            it_tb.setFlags(it_tb.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl_alloc.setItem(row, 1, it_tb)

            cmb_v = QComboBox()
            cmb_v.addItem("Seçiniz...", None)
            for vcode, plate in self._vehicle_map.items():
                cmb_v.addItem(plate, vcode)
            self.tbl_alloc.setCellWidget(row, 2, cmb_v)

            cmb_d = QComboBox()
            cmb_d.addItem("Seçiniz...", None)
            for did, name in self._driver_map.items():
                cmb_d.addItem(name, did)
            self.tbl_alloc.setCellWidget(row, 3, cmb_d)

            if plan_map is not None:
                rec = plan_map.get((str(route_id), tb))
                if rec is not None:
                    vid = str(rec.get("vehicle_id") or "")
                    did = str(rec.get("driver_id") or "")
                    if vid:
                        idx = cmb_v.findData(vid)
                        if idx >= 0:
                            cmb_v.setCurrentIndex(idx)
                    if did:
                        idx = cmb_d.findData(did)
                        if idx >= 0:
                            cmb_d.setCurrentIndex(idx)

        self._refresh_note_from_selection()

    def _on_grid_selection_changed(self):
        self._alloc_from_selection(append=False)

    # ------------------------- save / clear allocation -------------------------
    def _is_current_locked(self) -> bool:
        if not self._selected_contract_id or not self._service_type():
            return False
        return self._is_locked(int(self._selected_contract_id), self._month_key(), str(self._service_type()))

    def _apply_defaults_to_selection(self):
        if self._is_current_locked():
            QMessageBox.information(self, "Bilgi", "Bu dönem kilitli. Değişiklik yapılamaz.")
            return
        if not hasattr(self, "cmb_default_vehicle") or not hasattr(self, "cmb_default_driver"):
            return
        vid = self.cmb_default_vehicle.currentData()
        did = self.cmb_default_driver.currentData()
        if not vid and not did:
            QMessageBox.information(self, "Bilgi", "Varsayılan araç veya sürücü seçiniz.")
            return
        if not hasattr(self, "tbl_alloc"):
            return
        if self.tbl_alloc.rowCount() == 0:
            QMessageBox.information(self, "Bilgi", "Önce grid'den hücre seçip EKLE'ye basınız.")
            return
        for r in range(self.tbl_alloc.rowCount()):
            if vid:
                cmb_v = self.tbl_alloc.cellWidget(r, 2)
                if cmb_v is not None:
                    idx = cmb_v.findData(str(vid))
                    if idx >= 0:
                        cmb_v.setCurrentIndex(idx)
            if did:
                cmb_d = self.tbl_alloc.cellWidget(r, 3)
                if cmb_d is not None:
                    idx = cmb_d.findData(str(did))
                    if idx >= 0:
                        cmb_d.setCurrentIndex(idx)

    def _alloc_clear_selected_rows(self):
        if self._is_current_locked():
            QMessageBox.information(self, "Bilgi", "Bu dönem kilitli. Değişiklik yapılamaz.")
            return
        if not hasattr(self, "tbl_alloc"):
            return
        selected_rows = sorted({i.row() for i in self.tbl_alloc.selectedItems()}, reverse=True)
        if not selected_rows:
            QMessageBox.information(self, "Bilgi", "Silmek için atama tablosundan satır seçiniz.")
            return
        for r in selected_rows:
            route_item = self.tbl_alloc.item(r, 0)
            route_id = route_item.data(Qt.ItemDataRole.UserRole + 1) if route_item else None
            tb = route_item.data(Qt.ItemDataRole.UserRole + 2) if route_item else None
            if route_id and tb:
                self._upsert_plan(str(route_id), str(tb), None, None, note=None)
        self._reload_grid()

    def _save_from_alloc_table(self):
        if self._is_current_locked():
            QMessageBox.information(self, "Bilgi", "Bu dönem kilitli. Değişiklik yapılamaz.")
            return
        if not hasattr(self, "tbl_alloc") or self.tbl_alloc.rowCount() == 0:
            QMessageBox.information(self, "Bilgi", "Kaydedilecek satır yok. Grid'den hücre seçip EKLE'ye basınız.")
            return

        single_route_id = None
        single_vid = None
        single_did = None
        for r in range(self.tbl_alloc.rowCount()):
            route_item = self.tbl_alloc.item(r, 0)
            route_id = route_item.data(Qt.ItemDataRole.UserRole + 1) if route_item else None
            tb = route_item.data(Qt.ItemDataRole.UserRole + 2) if route_item else None
            if not route_id or not tb:
                continue
            cmb_v = self.tbl_alloc.cellWidget(r, 2)
            cmb_d = self.tbl_alloc.cellWidget(r, 3)
            vid = cmb_v.currentData() if cmb_v is not None else None
            did = cmb_d.currentData() if cmb_d is not None else None
            self._upsert_plan(str(route_id), str(tb), vid, did, note=None)

            if self.tbl_alloc.rowCount() == 1:
                single_route_id = str(route_id)
                single_vid = vid
                single_did = did

        if self.tbl_alloc.rowCount() == 1 and single_route_id and (single_vid or single_did):
            reply = QMessageBox.question(
                self,
                "Onay",
                "Bu güzergahın tüm saat dilimlerini aynı araç ve sürücü ile doldurmak ister misiniz?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                if self._selected_contract_id and self._service_type():
                    month = self._month_key()
                    tbs = self._time_blocks_for_context(int(self._selected_contract_id), month, str(self._service_type()))
                    for tb in tbs:
                        if not tb:
                            continue
                        self._upsert_plan(single_route_id, str(tb), single_vid, single_did, note=None)
        self._reload_grid()

    def _apply_lock_ui(self, locked: bool):
        for name in [
            "btn_alloc_add",
            "btn_alloc_del",
            "btn_alloc_save",
            "btn_apply_default_to_selection",
            "btn_note_save",
            "btn_note_clear",
            "btn_save",
        ]:
            if hasattr(self, name):
                getattr(self, name).setEnabled(not locked)
        if hasattr(self, "btn_lock_period"):
            self.btn_lock_period.setText("KİLİDİ AÇ" if locked else "KİLİTLE")

    def _toggle_lock(self):
        if not self._selected_contract_id or not self._service_type():
            return
        contract_id = int(self._selected_contract_id)
        month = self._month_key()
        service_type = str(self._service_type())
        current = self._is_locked(contract_id, month, service_type)
        new_val = 0 if current else 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trip_period_lock (contract_id, month, service_type, locked, locked_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(contract_id, month, service_type)
                DO UPDATE SET locked=excluded.locked, locked_at=excluded.locked_at
                """,
                (contract_id, month, service_type, int(new_val), now if new_val else None),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Kilit işlemi başarısız:\n{str(e)}")
            return
        self._reload_grid()

    def _upsert_plan(self, route_id: str, time_block: str, vehicle_id, driver_id, note):
        if not self._selected_contract_id or not self._service_type():
            return
        if not time_block:
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        month = self._month_key()
        service_type = str(self._service_type())
        contract_id = int(self._selected_contract_id)
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note
                FROM trip_plan
                WHERE contract_id=? AND route_params_id=? AND month=? AND service_type=? AND time_block=?
                LIMIT 1
                """,
                (contract_id, int(route_id), month, service_type, time_block),
            )
            existing_note_row = cursor.fetchone()
            final_note = note
            if note is None and existing_note_row is not None:
                final_note = existing_note_row[0]
            cursor.execute(
                """
                INSERT INTO trip_plan (
                    contract_id, route_params_id, month, service_type, time_block,
                    vehicle_id, driver_id, note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(contract_id, route_params_id, month, service_type, time_block)
                DO UPDATE SET vehicle_id=excluded.vehicle_id, driver_id=excluded.driver_id, note=excluded.note, updated_at=excluded.updated_at
                """,
                (
                    contract_id,
                    int(route_id),
                    month,
                    service_type,
                    time_block,
                    vehicle_id,
                    driver_id,
                    final_note,
                    now,
                    now,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Kayıt hatası:\n{str(e)}")

    # ------------------------- note handling -------------------------
    def _selection_note_key(self):
        cells = self._selected_grid_cells()
        if not cells:
            return None
        _r, _c, route_id, tb = cells[0]
        return route_id, tb

    def _refresh_note_from_selection(self):
        if not hasattr(self, "txt_note"):
            return
        key = self._selection_note_key()
        if key is None:
            self.txt_note.setPlainText("")
            return
        rec = self._get_plan_record(key[0], key[1])
        self.txt_note.setPlainText((rec or {}).get("note") or "")

    def _get_plan_record(self, route_id: str, time_block: str):
        if not self._selected_contract_id or not self._service_type():
            return None
        plan_map = self._load_plan_map(int(self._selected_contract_id), self._month_key(), str(self._service_type()))
        return plan_map.get((str(route_id), str(time_block)))

    def _save_note(self):
        if self._is_current_locked():
            QMessageBox.information(self, "Bilgi", "Bu dönem kilitli. Değişiklik yapılamaz.")
            return
        if not hasattr(self, "txt_note"):
            return
        key = self._selection_note_key()
        if key is None:
            QMessageBox.information(self, "Bilgi", "Not kaydetmek için grid'den bir hücre seçiniz.")
            return
        note = self.txt_note.toPlainText()
        self._upsert_plan(key[0], key[1], vehicle_id=None, driver_id=None, note=note)
        self._reload_grid()

    def _clear_note(self):
        if self._is_current_locked():
            QMessageBox.information(self, "Bilgi", "Bu dönem kilitli. Değişiklik yapılamaz.")
            return
        if not hasattr(self, "txt_note"):
            return
        key = self._selection_note_key()
        if key is None:
            QMessageBox.information(self, "Bilgi", "Not temizlemek için grid'den bir hücre seçiniz.")
            return
        self.txt_note.setPlainText("")
        self._upsert_plan(key[0], key[1], vehicle_id=None, driver_id=None, note="")
        self._reload_grid()