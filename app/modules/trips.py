import re
from datetime import datetime

from PyQt6 import uic
from PyQt6.QtCore import QDate, QTime, Qt, QTimer

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

class TripsGridApp(QWidget):
    def __init__(self, user_data=None, db_manager=None, parent=None):
        super().__init__(parent)
        uic.loadUi(get_ui_path("trips_grid_window.ui"), self)
        self.setObjectName("main_form")

        if hasattr(self, "table_sefer") and not hasattr(self, "tbl_grid"):
            self.tbl_grid = self.table_sefer
        if hasattr(self, "tbl_grid") and not hasattr(self, "table_sefer"):
            self.table_sefer = self.tbl_grid

        self.user_data = user_data or {}
        self.db = db_manager if db_manager else DatabaseManager()

        self._selected_contract_id = None
        self._selected_route_map = {}
        self._vehicle_map = {}
        self._driver_map = {}

        self._assignment_ready = False
        self._last_kalem_warn_key = None
        self._reload_debug_printed = False
        self._opening_trips_dialog = False

        self._kalem_model = QStandardItemModel()
        if hasattr(self, "list_kalemler"):
            try:
                self.list_kalemler.setModel(self._kalem_model)
            except Exception:
                pass

        self._tbl_grid_cols = {}

        self._setup_tables()
        self._setup_connections()
        self._load_static_filters()
        self._load_customers()

        try:
            QTimer.singleShot(0, self._reload_grid)
        except Exception:
            pass

    def _service_type_values(self, service_type: str):
        raw = (service_type or "").strip()
        s = raw.upper().replace("_", " ")
        s2 = s.replace("TAŞIMA", "TASIMA")

        if s in ("PERSONEL", "PERSONEL TAŞIMA", "PERSONEL TASIMA") or s2 in (
            "PERSONEL",
            "PERSONEL TASIMA",
        ):
            return [
                "PERSONEL TAŞIMA",
                "PERSONEL TASIMA",
                "PERSONEL_TAŞIMA",
                "PERSONEL_TASIMA",
                "PERSONEL",
            ]

        if s in ("ÖĞRENCİ", "OGRENCI", "ÖĞRENCİ TAŞIMA", "ÖĞRENCİ TASIMA", "OGRENCI TASIMA") or s2 in (
            "OGRENCI",
            "OGRENCI TASIMA",
        ):
            return [
                "ÖĞRENCİ TAŞIMA",
                "ÖĞRENCİ TASIMA",
                "OGRENCI TASIMA",
                "ÖĞRENCİ_TAŞIMA",
                "ÖĞRENCİ_TASIMA",
                "OGRENCI_TASIMA",
                "ÖĞRENCİ",
                "OGRENCI",
            ]

        vals = []
        for v in (raw, s, s2):
            vv = (v or "").strip()
            if vv and vv not in vals:
                vals.append(vv)
        return vals

    def _load_vehicle_driver_maps(self):
        self._vehicle_map = {}
        self._vehicle_capacity_map = {}
        self._driver_map = {}
        try:
            for vcode, plate, cap in self.db.get_araclar_list_with_capacity(only_active=True) or []:
                self._vehicle_map[str(vcode)] = str(plate)
                try:
                    self._vehicle_capacity_map[str(vcode)] = int(cap or 0)
                except Exception:
                    self._vehicle_capacity_map[str(vcode)] = 0
        except Exception:
            self._vehicle_map = {}
            self._vehicle_capacity_map = {}
        try:
            for kod, ad in self.db.get_sofor_listesi() or []:
                self._driver_map[str(kod)] = str(ad)
        except Exception:
            self._driver_map = {}

    def _resolve_contract_id(self):
        if self._selected_contract_id not in (None, ""):
            return self._selected_contract_id

        if not hasattr(self, "cmb_sozlesme"):
            return None

        try:
            v = self.cmb_sozlesme.currentData()
        except Exception:
            v = None
        if v not in (None, ""):
            return v

        try:
            txt = (self.cmb_sozlesme.currentText() or "").strip()
        except Exception:
            txt = ""
        if not txt:
            return None

        contract_no = txt.split("(")[0].strip().split()[0].strip()
        if not contract_no:
            return None

        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM contracts WHERE contract_number = ? LIMIT 1",
                (str(contract_no),),
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                return row[0]
        except Exception:
            return None

        return None

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
        pass

    def _split_time_block(self, tb: str):
        tbs = (tb or "").strip()
        if not tbs:
            return "", ""
        if "-" in tbs:
            a, b = (tbs.split("-", 1) + [""])[:2]
            return (a or "").strip(), (b or "").strip()
        if ":" in tbs:
            return tbs, ""
        return tbs, ""

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

    def _setup_tables(self):
        if hasattr(self, "tbl_grid"):
            try:
                self.tbl_grid.setProperty("no_zebra", True)
            except Exception:
                pass
            self.tbl_grid.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.tbl_grid.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.tbl_grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            self.tbl_grid.setAlternatingRowColors(False)
            self.tbl_grid.verticalHeader().setVisible(False)
            self.tbl_grid.horizontalHeader().setHighlightSections(False)

            # Respect Designer columns; only set headers if none.
            if self.tbl_grid.columnCount() == 0:
                headers = ["ROTA", "GİRİŞ SAATİ", "ÇIKIŞ SAATİ", "ARAÇ PLAKASI", "ŞOFÖR"]
                self.tbl_grid.setColumnCount(len(headers))
                self.tbl_grid.setHorizontalHeaderLabels(headers)

            self._tbl_grid_cols = self._resolve_tbl_grid_columns()
            h = self.tbl_grid.horizontalHeader()
            h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            if self._tbl_grid_cols.get("rota") is not None:
                h.setSectionResizeMode(int(self._tbl_grid_cols["rota"]), QHeaderView.ResizeMode.Stretch)
            for k in ("giris", "cikis", "plaka", "kpst", "sofor"):
                if self._tbl_grid_cols.get(k) is not None:
                    h.setSectionResizeMode(int(self._tbl_grid_cols[k]), QHeaderView.ResizeMode.ResizeToContents)

    def _resolve_tbl_grid_columns(self):
        if not hasattr(self, "tbl_grid"):
            return {}
        tbl = self.tbl_grid
        cols = {}
        try:
            for c in range(tbl.columnCount()):
                it = tbl.horizontalHeaderItem(c)
                txt = (it.text() if it is not None else "")
                key = (txt or "").strip().upper()
                if key == "ROTA":
                    cols["rota"] = c
                elif key in ("GİRİŞ SAATİ", "GIRIS SAATI", "GİRİŞ", "GIRIS"):
                    cols["giris"] = c
                elif key in ("ÇIKIŞ SAATİ", "CIKIS SAATI", "ÇIKIŞ", "CIKIS"):
                    cols["cikis"] = c
                elif key in ("ARAÇ PLAKASI", "ARAC PLAKASI", "ARAÇ", "ARAC"):
                    cols["plaka"] = c
                elif key in ("KPST.", "KPST", "KAPASITE"):
                    cols["kpst"] = c
                elif key in ("ŞOFÖR", "SOFOR", "SÜRÜCÜ", "SURUCU"):
                    cols["sofor"] = c
        except Exception:
            return cols

        # Backward compatible defaults
        if "rota" not in cols:
            cols["rota"] = 0
        if "giris" not in cols:
            cols["giris"] = 1
        if "cikis" not in cols:
            cols["cikis"] = 2
        if "plaka" not in cols:
            cols["plaka"] = 3
        if "sofor" not in cols:
            cols["sofor"] = 4
        return cols

    def _setup_connections(self):
        if hasattr(self, "cmb_musteri"):
            self.cmb_musteri.currentIndexChanged.connect(self._on_customer_changed)
        if hasattr(self, "cmb_sozlesme"):
            self.cmb_sozlesme.currentIndexChanged.connect(self._on_contract_changed)
            try:
                self.cmb_sozlesme.activated.connect(self._on_contract_changed)
            except Exception:
                pass
        if hasattr(self, "cmb_service_type"):
            self.cmb_service_type.currentIndexChanged.connect(self._reload_grid)
            try:
                self.cmb_service_type.activated.connect(self._reload_grid)
            except Exception:
                pass
            try:
                self.cmb_service_type.currentTextChanged.connect(self._reload_grid)
            except Exception:
                pass

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

        if hasattr(self, "btn_yenile"):
            self.btn_yenile.clicked.connect(self._reload_grid)
        if hasattr(self, "btn_temizle"):
            self.btn_temizle.clicked.connect(self._clear_inputs)
        if hasattr(self, "btn_ekle"):
            self.btn_ekle.clicked.connect(self._add_to_grid)
        if hasattr(self, "btn_cikar"):
            self.btn_cikar.clicked.connect(self._remove_selected_grid_rows)
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
        self._selected_contract_id = self._resolve_contract_id()
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
        v = self.cmb_service_type.currentData()
        if v is None:
            try:
                v = (self.cmb_service_type.currentText() or "").strip()
            except Exception:
                v = None
        if isinstance(v, str) and v.strip().lower().startswith("seç"):
            return None
        return v

    def _load_kalemler_from_contract(self, contract_id: int, service_type: str):
        self._ensure_route_params_table()
        self._selected_route_map = {}
        self._kalem_model.clear()

        rows = []
        st_values = [str(x) for x in self._service_type_values(str(service_type)) if str(x or "").strip()]
        if not st_values:
            self._apply_kalem_filter()
            return
        placeholders = ",".join(["?" for _ in st_values])
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            q = (
                "SELECT id, COALESCE(route_name,''), COALESCE(stops,''), COALESCE(movement_type,''), distance_km "
                "FROM route_params "
                f"WHERE contract_id = ? AND service_type IN ({placeholders}) AND COALESCE(route_name,'') <> '' "
                "ORDER BY id ASC"
            )
            cursor.execute(q, tuple([int(contract_id)] + st_values))
            rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            rows = []
            key = ("kalem_sql", int(contract_id), str(service_type))
            if getattr(self, "_last_kalem_warn_key", None) != key:
                self._last_kalem_warn_key = key
                QMessageBox.critical(
                    self,
                    "Hata",
                    "Kalem (rota) sorgusu çalıştırılamadı.\n"
                    f"Sözleşme ID: {contract_id}\n"
                    f"Hizmet Tipi: {service_type}\n\n"
                    f"Hata: {str(e)}",
                )

        for rid, rname, stops_txt, movement_type, km in rows:
            rid_s = str(rid)
            self._selected_route_map[rid_s] = {
                "route_name": (rname or ""),
                "stops": (stops_txt or ""),
                "movement_type": (movement_type or ""),
                "distance_km": km,
            }
            parts = [p for p in [str(rname or ""), str(stops_txt or ""), str(movement_type or "")] if str(p).strip()]
            disp = " | ".join(parts)
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

        for r in range(self._kalem_model.rowCount()):
            it = self._kalem_model.item(r)
            txt = (it.text() if it is not None else "") or ""
            hide = bool(q) and (q not in txt.lower())
            try:
                self.list_kalemler.setRowHidden(r, hide)
            except Exception:
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
        if self._opening_trips_dialog:
            return
        if not self._selected_contract_id or not self._service_type():
            return
        route_id = self._selected_route_id()
        if not route_id:
            return
        self._open_trips_dialog(str(route_id))

    def _open_trips_dialog(self, route_id: str):
        if not self._selected_contract_id or not self._service_type():
            return

        contract_id = int(self._selected_contract_id)
        service_type = str(self._service_type())
        month = self._month_key()

        route_rec = self._selected_route_map.get(str(route_id), {})
        route_name_txt = str(route_rec.get("route_name") or "")
        stops_txt = str(route_rec.get("stops") or "")
        movement_type_txt = str(route_rec.get("movement_type") or "")
        rota_disp_parts = [p for p in [route_name_txt, stops_txt, movement_type_txt] if str(p).strip()]
        rota_disp = " | ".join(rota_disp_parts)

        self._load_vehicle_driver_maps()

        dlg = QDialog(self)
        try:
            uic.loadUi(get_ui_path("trips_dialog.ui"), dlg)
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"trips_dialog.ui yüklenemedi:\n{str(e)}")
            return

        try:
            if route_name_txt:
                dlg.setWindowTitle(route_name_txt)
        except Exception:
            pass

        try:
            lbl2 = getattr(dlg, "lbl_atama_text", None)
            if lbl2 is not None and route_name_txt:
                lbl2.setText(
                    "<html><head/><body><p>İŞ KALEMİ: <b>"
                    + str(route_name_txt)
                    + "</b></p><p>İŞ KALEMİ İÇİN ARAÇ VE SÜRÜCÜ ATAMASI YAPIN</p></body></html>"
                )
        except Exception:
            pass

        cmb_v = getattr(dlg, "cmb_arac_sec", None)
        cmb_d = getattr(dlg, "cmb_surucu_sec", None)
        if cmb_v is not None:
            try:
                cmb_v.setFixedWidth(200)
            except Exception:
                pass
            cmb_v.clear()
            cmb_v.addItem("Seçiniz...", None)
            for vcode, plate in self._vehicle_map.items():
                cmb_v.addItem(str(plate), str(vcode))
        if cmb_d is not None:
            try:
                cmb_d.setFixedWidth(200)
            except Exception:
                pass
            cmb_d.clear()
            cmb_d.addItem("Seçiniz...", None)
            for did, name in self._driver_map.items():
                cmb_d.addItem(str(name), str(did))

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

        for chk, cg, cc in pairs:
            if chk is None:
                continue
            if cg is not None:
                try:
                    cg.setFixedWidth(70)
                except Exception:
                    pass
            if cc is not None:
                try:
                    cc.setFixedWidth(70)
                except Exception:
                    pass

            def _mk_toggle(_cg, _cc):
                def _toggle(state):
                    en = bool(state)
                    if _cg is not None:
                        _cg.setEnabled(en)
                    if _cc is not None:
                        _cc.setEnabled(en)

                return _toggle

            try:
                chk.stateChanged.connect(_mk_toggle(cg, cc))
            except Exception:
                pass

        existing_pairs = []
        existing_vid = None
        existing_did = None
        try:
            if hasattr(self, "tbl_grid"):
                cols = self._resolve_tbl_grid_columns()
                self._tbl_grid_cols = cols
                c_rota = int(cols.get("rota", 0))
                c_g = int(cols.get("giris", 1))
                c_c = int(cols.get("cikis", 2))
                for r in range(self.tbl_grid.rowCount()):
                    it_rota = self.tbl_grid.item(r, c_rota)
                    if it_rota is None:
                        continue

                    rid2 = it_rota.data(Qt.ItemDataRole.UserRole + 1)
                    if str(rid2 or "") != str(route_id):
                        continue
                    tb2 = it_rota.data(Qt.ItemDataRole.UserRole + 2)
                    g2 = (self.tbl_grid.item(r, c_g).text().strip() if self.tbl_grid.item(r, c_g) else "")
                    c2 = (self.tbl_grid.item(r, c_c).text().strip() if self.tbl_grid.item(r, c_c) else "")
                    if not tb2 and (g2 or c2):
                        tb2 = f"{g2}-{c2}" if (g2 or c2) else ""
                    if not tb2:
                        continue
                    g_s, c_s = self._split_time_block(str(tb2 or ""))
                    if g_s or c_s:
                        existing_pairs.append((g_s, c_s))
                    if existing_vid is None:
                        vv = it_rota.data(Qt.ItemDataRole.UserRole + 3)
                        if vv not in (None, ""):
                            existing_vid = str(vv)
                    if existing_did is None:
                        dd = it_rota.data(Qt.ItemDataRole.UserRole + 4)
                        if dd not in (None, ""):
                            existing_did = str(dd)
        except Exception:
            existing_pairs = []

        if not existing_pairs:
            try:
                conn = self.db.connect()
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT time_block, vehicle_id, driver_id
                    FROM trip_plan
                    WHERE contract_id=? AND route_params_id=? AND month=? AND service_type=?
                    """,
                    (contract_id, int(route_id), month, service_type),
                )
                for tb, vid, did in cur.fetchall() or []:
                    g_s, c_s = self._split_time_block(str(tb or ""))
                    if g_s or c_s:
                        existing_pairs.append((g_s, c_s))
                    if existing_vid is None and vid not in (None, ""):
                        existing_vid = str(vid)
                    if existing_did is None and did not in (None, ""):
                        existing_did = str(did)
                conn.close()
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass

        if cmb_v is not None and existing_vid:
            idx = cmb_v.findData(existing_vid)
            if idx >= 0:
                cmb_v.setCurrentIndex(idx)
        if cmb_d is not None and existing_did:
            idx = cmb_d.findData(existing_did)
            if idx >= 0:
                cmb_d.setCurrentIndex(idx)

        def _combo_set_text(cmb, txt: str):
            if cmb is None:
                return
            v = (txt or "").strip()
            if not v:
                return
            try:
                idx = cmb.findText(v)
                if idx >= 0:
                    cmb.setCurrentIndex(idx)
                else:
                    cmb.setEditText(v)
            except Exception:
                pass

        for i, (chk, cg, cc) in enumerate(pairs):
            if chk is None:
                continue
            g_s = ""
            c_s = ""
            if i < len(existing_pairs):
                g_s, c_s = existing_pairs[i]
            _combo_set_text(cg, g_s)
            _combo_set_text(cc, c_s)
            try:
                chk.setChecked(bool(g_s or c_s))
            except Exception:
                pass

        btn_atama = getattr(dlg, "btn_atama", None)
        if btn_atama is not None:
            try:
                btn_atama.clicked.connect(
                    lambda: QMessageBox.information(
                        self,
                        "Bilgi",
                        "Bu atamalar ekran üzerinde görünür. Kalıcı olması için Seferler ekranında KAYDET'e basınız.",
                    )
                )
            except Exception:
                pass

        btn_save = getattr(dlg, "btn_kaydet", None)
        if btn_save is None:
            return

        def _save():
            vid = cmb_v.currentData() if cmb_v is not None else None
            did = cmb_d.currentData() if cmb_d is not None else None

            def _cmb_text_or_selected(cmb):
                if cmb is None:
                    return ""
                try:
                    v = (cmb.currentText() or "").strip()
                except Exception:
                    v = ""
                if v:
                    return v
                try:
                    idx = cmb.currentIndex()
                    if idx is None:
                        idx = -1
                    if 0 <= idx < cmb.count():
                        return (cmb.itemText(idx) or "").strip()
                except Exception:
                    return ""
                return ""

            chosen_pairs = []
            for chk, cg, cc in pairs:
                if chk is None or not chk.isChecked():
                    continue
                gt = _cmb_text_or_selected(cg)
                ct = _cmb_text_or_selected(cc)
                if gt and self._parse_time(gt) is None:
                    QMessageBox.warning(self, "Uyarı", f"Saat formatı geçersiz: {gt} (HH:MM)")
                    return
                if ct and self._parse_time(ct) is None:
                    QMessageBox.warning(self, "Uyarı", f"Saat formatı geçersiz: {ct} (HH:MM)")
                    return
                if gt or ct:
                    chosen_pairs.append((gt, ct))

            try:
                if hasattr(self, "tbl_grid"):
                    cols = self._resolve_tbl_grid_columns()
                    self._tbl_grid_cols = cols
                    c_rota = int(cols.get("rota", 0))
                    del_rows = []
                    for r in range(self.tbl_grid.rowCount()):
                        it_rota = self.tbl_grid.item(r, c_rota)
                        rid2 = it_rota.data(Qt.ItemDataRole.UserRole + 1) if it_rota else None
                        if str(rid2 or "") == str(route_id):
                            del_rows.append(r)
                    for r in sorted(del_rows, reverse=True):
                        self.tbl_grid.removeRow(r)
            except Exception:
                pass

            plate = self._vehicle_map.get(str(vid or ""), "")
            cap = self._vehicle_capacity_map.get(str(vid or ""), 0)
            dname = self._driver_map.get(str(did or ""), "")
            cols = self._resolve_tbl_grid_columns()
            self._tbl_grid_cols = cols
            c_rota = int(cols.get("rota", 0))
            c_g = int(cols.get("giris", 1))
            c_c = int(cols.get("cikis", 2))
            c_p = int(cols.get("plaka", 3))
            c_s = int(cols.get("sofor", 4))
            c_k = cols.get("kpst")
            for gt, ct in chosen_pairs:
                rr = self.tbl_grid.rowCount()
                self.tbl_grid.insertRow(rr)

                it_g = QTableWidgetItem(str(gt or ""))
                it_c = QTableWidgetItem(str(ct or ""))
                it_v = QTableWidgetItem(str(plate or ""))
                it_k = QTableWidgetItem(str(cap if cap is not None else ""))
                it_d = QTableWidgetItem(str(dname or ""))
                it_rota = QTableWidgetItem(str(rota_disp or route_name_txt or ""))
                items = [it_rota, it_g, it_c, it_v, it_d]
                if c_k is not None:
                    items = [it_rota, it_g, it_c, it_v, it_k, it_d]
                for it in items:
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)

                # Data-roles: route_id / time_block / vehicle_id / driver_id
                rid_s = str(route_id)
                tb_val = f"{gt}-{ct}"
                for it in items:
                    it.setData(Qt.ItemDataRole.UserRole + 1, rid_s)
                    it.setData(Qt.ItemDataRole.UserRole + 2, str(tb_val or ""))
                    it.setData(Qt.ItemDataRole.UserRole + 3, (None if vid in (None, "") else str(vid)))
                    it.setData(Qt.ItemDataRole.UserRole + 4, (None if did in (None, "") else str(did)))

                self.tbl_grid.setItem(rr, c_rota, it_rota)
                self.tbl_grid.setItem(rr, c_g, it_g)
                self.tbl_grid.setItem(rr, c_c, it_c)
                self.tbl_grid.setItem(rr, c_p, it_v)
                if c_k is not None:
                    self.tbl_grid.setItem(rr, int(c_k), it_k)
                self.tbl_grid.setItem(rr, c_s, it_d)

            try:
                self._group_tbl_grid_by_rota()
            except Exception:
                pass

            QMessageBox.information(
                self,
                "Bilgi",
                "Değişiklikler tabloya aktarıldı. Kalıcı olması için Seferler ekranında KAYDET'e basınız.",
            )
            try:
                dlg.accept()
            except Exception:
                pass

        try:
            btn_save.clicked.connect(_save)
        except Exception:
            pass

        self._opening_trips_dialog = True
        try:
            dlg.exec()
        finally:
            self._opening_trips_dialog = False

    def _time_pairs(self):
        # Removed legacy time_g1/time_c1 default-widget logic usage
        return []

    def _clear_inputs(self):
        if hasattr(self, "txt_kalem_sec"):
            self.txt_kalem_sec.clear()
        if hasattr(self, "cmb_arac_sec"):
            self.cmb_arac_sec.setCurrentIndex(0)
        if hasattr(self, "cmb_surucu_sec"):
            self.cmb_surucu_sec.setCurrentIndex(0)

    def _add_to_grid(self):
        # Excel akışı: sefer tipleri ve saatler ana ekranda değil, trips_dialog.ui üzerinden girilir.
        # Bu buton varsa, seçili iş kalemi için dialog'u açarak planlama yapılmasını sağlar.
        route_id = self._selected_route_id()
        if not route_id:
            QMessageBox.information(self, "Bilgi", "Önce iş kalemi (hat) seçiniz.")
            return
        self._open_trips_dialog(str(route_id))

    def _remove_selected_grid_rows(self):
        if not hasattr(self, "tbl_grid"):
            return
        rows = sorted({it.row() for it in self.tbl_grid.selectedItems()}, reverse=True)
        if not rows:
            return
        for r in rows:
            self.tbl_grid.removeRow(r)

    def _delete_selected_table_rows(self):
        # UI uyumluluğu: bazı ekranlarda buton adı btn_satir_sil ve eski kod
        # _delete_selected_table_rows metodunu bekliyor. Bu projede tablolar
        # farklı isimlerle (tbl_grid / table_sefer) bulunabildiği için wrapper.
        if hasattr(self, "tbl_grid"):
            self._remove_selected_grid_rows()
            return
        if hasattr(self, "table_sefer"):
            rows = sorted({it.row() for it in self.table_sefer.selectedItems()}, reverse=True)
            if not rows:
                return
            for r in rows:
                self.table_sefer.removeRow(r)
            return

    def _delete_all_table_rows(self):
        if not hasattr(self, "tbl_grid"):
            return

        msg = QMessageBox.question(
            self,
            "Onay",
            "Tüm sefer satırları silinsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if msg != QMessageBox.StandardButton.Yes:
            return
        self.tbl_grid.setRowCount(0)

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
        if not hasattr(self, "tbl_grid") or self.tbl_grid.rowCount() == 0:
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

            for r in range(self.tbl_grid.rowCount()):
                cols = self._resolve_tbl_grid_columns()
                self._tbl_grid_cols = cols
                c_rota = int(cols.get("rota", 0))
                it_rota = self.tbl_grid.item(r, c_rota)
                if it_rota is None:
                    continue

                rid = it_rota.data(Qt.ItemDataRole.UserRole + 1)
                tb = it_rota.data(Qt.ItemDataRole.UserRole + 2)
                vid = it_rota.data(Qt.ItemDataRole.UserRole + 3)
                did = it_rota.data(Qt.ItemDataRole.UserRole + 4)

                if not rid:
                    continue

                # Excel akışı: DB'de time_block 'HH:MM-HH:MM' formatında tutulur.
                tb_s = (str(tb or "").strip() if tb is not None else "")
                g_txt = (self.tbl_grid.item(r, int(cols.get("giris", 1))).text().strip() if self.tbl_grid.item(r, int(cols.get("giris", 1))) else "")
                c_txt = (self.tbl_grid.item(r, int(cols.get("cikis", 2))).text().strip() if self.tbl_grid.item(r, int(cols.get("cikis", 2))) else "")
                if (not tb_s) and (g_txt or c_txt):
                    tb_s = f"{g_txt}-{c_txt}" if (g_txt or c_txt) else ""
                if not tb_s:
                    continue
                g_s, c_s = self._split_time_block(tb_s)
                if g_s and self._parse_time(g_s) is None:
                    QMessageBox.warning(self, "Uyarı", f"Saat formatı geçersiz: {g_s} (HH:MM)")
                    return
                if c_s and self._parse_time(c_s) is None:
                    QMessageBox.warning(self, "Uyarı", f"Saat formatı geçersiz: {c_s} (HH:MM)")
                    return
                tb_s = f"{g_s}-{c_s}".strip("-")
                if "-" not in tb_s:
                    tb_s = f"{g_s}-{c_s}"

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
        if not hasattr(self, "tbl_grid"):
            return

        if not self._reload_debug_printed:
            try:
                print("[Trips] _reload_grid called")
            except Exception:
                pass

        if hasattr(self, "list_kalemler"):
            try:
                self.list_kalemler.setModel(self._kalem_model)
            except Exception:
                pass

        # Header'ı koru
        if self.tbl_grid.columnCount() == 0:
            headers = ["ROTA", "GİRİŞ SAATİ", "ÇIKIŞ SAATİ", "ARAÇ PLAKASI", "ŞOFÖR"]
            self.tbl_grid.setColumnCount(len(headers))
            self.tbl_grid.setHorizontalHeaderLabels(headers)

        self._tbl_grid_cols = self._resolve_tbl_grid_columns()

        self._load_vehicle_driver_maps()

        contract_id = self._resolve_contract_id()
        self._selected_contract_id = contract_id
        service_type = self._service_type()
        month = self._month_key()

        self.tbl_grid.setRowCount(0)
        self._selected_route_map = {}
        self._kalem_model.clear()

        if not contract_id or not service_type:
            return

        # Kalem listesi
        self._load_kalemler_from_contract(int(contract_id), str(service_type))

        if self._kalem_model.rowCount() == 0:
            key = (int(contract_id), str(service_type))
            if self._last_kalem_warn_key != key:
                self._last_kalem_warn_key = key
                QMessageBox.information(
                    self,
                    "Bilgi",
                    "Bu sözleşme ve hizmet tipi için rota kaydı bulunamadı.\n"
                    f"Sözleşme ID: {contract_id}\n"
                    f"Hizmet Tipi: {service_type}",
                )

        plan_map = self._load_plan_map(int(contract_id), month, str(service_type))

        planned_rids = set()
        try:
            planned_rids = {str(rid) for (rid, _tb) in (plan_map or {}).keys()}
        except Exception:
            planned_rids = set()

        # Kalem text + renk
        for r in range(self._kalem_model.rowCount()):
            it = self._kalem_model.item(r)
            rid = None if it is None else it.data(Qt.ItemDataRole.UserRole)
            rid_s = str(rid) if rid is not None else ""
            route_rec = self._selected_route_map.get(rid_s, {}) if rid_s else {}
            rname = str(route_rec.get("route_name") or "")
            stops_txt = str(route_rec.get("stops") or "")
            mtype = str(route_rec.get("movement_type") or "")
            rota_parts = [p for p in [rname, stops_txt, mtype] if str(p).strip()]
            rota_disp = " | ".join(rota_parts)
            try:
                if it is not None and rota_disp:
                    it.setText(rota_disp)
            except Exception:
                pass
            try:
                if rid_s and rid_s in planned_rids:
                    it.setForeground(QColor(0, 128, 0))
                else:
                    it.setForeground(QColor(200, 0, 0))
            except Exception:
                pass

        if not plan_map:
            self._group_tbl_grid_by_rota()
            return

        for (rid, tb), rec in plan_map.items():
            route_rec = self._selected_route_map.get(str(rid), {})
            rname = str(route_rec.get("route_name") or "")
            stops_txt = str(route_rec.get("stops") or "")
            mtype = str(route_rec.get("movement_type") or "")
            rota_parts = [p for p in [rname, stops_txt, mtype] if str(p).strip()]
            rota_disp = " | ".join(rota_parts)

            tb_s = str(tb or "")
            g_txt, c_txt = self._split_time_block(str(tb_s))

            vid = rec.get("vehicle_id")
            did = rec.get("driver_id")
            plate = self._vehicle_map.get(str(vid or ""), "")
            cap = self._vehicle_capacity_map.get(str(vid or ""), 0)
            dname = self._driver_map.get(str(did or ""), "")

            rows_to_add = []
            rows_to_add.append(
                {
                    "rid": str(rid),
                    "tb_s": tb_s,
                    "g_txt": g_txt,
                    "c_txt": c_txt,
                    "vid": vid,
                    "did": did,
                    "plate": plate,
                    "cap": cap,
                    "dname": dname,
                    "rota_disp": str(rota_disp or rname or ""),
                }
            )

            rows_to_add.sort(key=lambda x: (str(x.get("rota_disp") or ""), str(x.get("tb_s") or "")))

            for rec in rows_to_add:
                rr = self.tbl_grid.rowCount()
                self.tbl_grid.insertRow(rr)

                it_g = QTableWidgetItem(str(rec.get("g_txt") or ""))
                it_c = QTableWidgetItem(str(rec.get("c_txt") or ""))
                it_v = QTableWidgetItem(str(rec.get("plate") or ""))
                it_k = QTableWidgetItem(str(rec.get("cap") if rec.get("cap") is not None else ""))
                it_d = QTableWidgetItem(str(rec.get("dname") or ""))
                it_rota = QTableWidgetItem(str(rec.get("rota_disp") or ""))
                items = [it_rota, it_g, it_c, it_v, it_d]
                if self._tbl_grid_cols.get("kpst") is not None:
                    items = [it_rota, it_g, it_c, it_v, it_k, it_d]
                for it in items:
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)

                # Data-roles: route_id / time_block / vehicle_id / driver_id
                rid_s = str(rec.get("rid") or "")
                tb_s = str(rec.get("tb_s") or "")
                vid = rec.get("vid")
                did = rec.get("did")
                for it in items:
                    it.setData(Qt.ItemDataRole.UserRole + 1, rid_s)
                    it.setData(Qt.ItemDataRole.UserRole + 2, tb_s)
                    it.setData(Qt.ItemDataRole.UserRole + 3, (None if vid is None else str(vid)))
                    it.setData(Qt.ItemDataRole.UserRole + 4, (None if did is None else str(did)))

                self.tbl_grid.setItem(rr, int(self._tbl_grid_cols.get("rota", 0)), it_rota)
                self.tbl_grid.setItem(rr, int(self._tbl_grid_cols.get("giris", 1)), it_g)
                self.tbl_grid.setItem(rr, int(self._tbl_grid_cols.get("cikis", 2)), it_c)
                self.tbl_grid.setItem(rr, int(self._tbl_grid_cols.get("plaka", 3)), it_v)
                if self._tbl_grid_cols.get("kpst") is not None:
                    self.tbl_grid.setItem(rr, int(self._tbl_grid_cols.get("kpst")), it_k)
                self.tbl_grid.setItem(rr, int(self._tbl_grid_cols.get("sofor", 4)), it_d)

        self._group_tbl_grid_by_rota()

    def _group_tbl_grid_by_rota(self):
        if not hasattr(self, "tbl_grid"):
            return
        tbl = self.tbl_grid

        # Clear previous spans
        try:
            tbl.clearSpans()
        except Exception:
            pass

        start = 0
        last_txt = None
        for r in range(tbl.rowCount() + 1):
            txt = ""
            if r < tbl.rowCount():
                it = tbl.item(r, int(self._resolve_tbl_grid_columns().get("rota", 0)))
                txt = str((it.text() if it is not None else "") or "")

            if r == 0:
                last_txt = txt

            if r == tbl.rowCount() or txt != last_txt:
                span_len = r - start
                if span_len > 1 and str(last_txt or ""):
                    try:
                        tbl.setSpan(start, int(self._resolve_tbl_grid_columns().get("rota", 0)), span_len, 1)
                    except Exception:
                        pass

                    for rr in range(start + 1, r):
                        try:
                            it2 = tbl.item(rr, int(self._resolve_tbl_grid_columns().get("rota", 0)))
                            if it2 is not None:
                                it2.setText("")
                        except Exception:
                            pass

                    try:
                        it0 = tbl.item(start, int(self._resolve_tbl_grid_columns().get("rota", 0)))
                        if it0 is not None:
                            it0.setTextAlignment(int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft))
                    except Exception:
                        pass

                start = r
                last_txt = txt

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
            c_plaka = int(self._resolve_tbl_grid_columns().get("plaka", 3))
            if c < c_plaka:
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