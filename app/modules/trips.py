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

        self._assignment_ready = False

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
        if hasattr(self, "tbl_grid"):
            self.tbl_grid.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.tbl_grid.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.tbl_grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            self.tbl_grid.setAlternatingRowColors(True)
            self.tbl_grid.verticalHeader().setVisible(False)
            self.tbl_grid.horizontalHeader().setHighlightSections(False)
            self.tbl_grid.horizontalHeader().setStretchLastSection(False)

            headers = ["Güzergah", "Blok", "Giriş", "Çıkış", "Araç", "Şoför"]
            self.tbl_grid.setColumnCount(len(headers))
            self.tbl_grid.setHorizontalHeaderLabels(headers)
            h = self.tbl_grid.horizontalHeader()
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
            cursor.execute(
                """
                SELECT id, COALESCE(route_name,''), distance_km
                FROM route_params
                WHERE contract_id = ? AND service_type = ? AND COALESCE(route_name,'') <> ''
                ORDER BY id ASC
                """,
                (int(contract_id), str(service_type)),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            rows = []

        for rid, rname, km in rows:
            rid_s = str(rid)
            self._selected_route_map[rid_s] = {
                "route_name": (rname or ""),
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

    def _time_pairs(self):
        pairs = []
        for idx in (1, 2, 3):
            g = getattr(self, f"time_g{idx}", None)
            c = getattr(self, f"time_c{idx}", None)
            if g is None or c is None:
                continue
            pairs.append((idx, g, c))
        return pairs

    def _clear_inputs(self):
        if hasattr(self, "txt_kalem_sec"):
            self.txt_kalem_sec.clear()
        if hasattr(self, "cmb_arac_sec"):
            self.cmb_arac_sec.setCurrentIndex(0)
        if hasattr(self, "cmb_surucu_sec"):
            self.cmb_surucu_sec.setCurrentIndex(0)

    def _add_to_grid(self):
        if not hasattr(self, "tbl_grid"):
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

        route_id = self._selected_route_id()
        if not route_id:
            QMessageBox.information(self, "Bilgi", "Önce iş kalemi (hat) seçiniz.")
            return

        # Sefer satırı oluştururken araç/şoför seçimi bu satırlara gömülür.
        vid = self.cmb_arac_sec.currentData() if hasattr(self, "cmb_arac_sec") else None
        did = self.cmb_surucu_sec.currentData() if hasattr(self, "cmb_surucu_sec") else None

        route_name = self._selected_route_map.get(str(route_id), {}).get("route_name", "")
        plate = self._vehicle_map.get(str(vid or ""), "")
        dname = self._driver_map.get(str(did or ""), "")

        for idx, g, c in self._time_pairs():
            gtxt = g.time().toString("HH:mm")
            ctxt = c.time().toString("HH:mm")

            # Gidiş
            rr = self.tbl_grid.rowCount()
            self.tbl_grid.insertRow(rr)
            it_route = QTableWidgetItem(route_name)
            it_tb = QTableWidgetItem(f"G{idx}")
            it_g = QTableWidgetItem(gtxt)
            it_c = QTableWidgetItem("")
            it_v = QTableWidgetItem(plate)
            it_d = QTableWidgetItem(dname)
            for it in (it_route, it_tb, it_g, it_c, it_v, it_d):
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            it_tb.setData(Qt.ItemDataRole.UserRole + 1, str(route_id))
            it_tb.setData(Qt.ItemDataRole.UserRole + 2, f"G{idx}")
            it_tb.setData(Qt.ItemDataRole.UserRole + 3, (None if vid is None else str(vid)))
            it_tb.setData(Qt.ItemDataRole.UserRole + 4, (None if did is None else str(did)))
            self.tbl_grid.setItem(rr, 0, it_route)
            self.tbl_grid.setItem(rr, 1, it_tb)
            self.tbl_grid.setItem(rr, 2, it_g)
            self.tbl_grid.setItem(rr, 3, it_c)
            self.tbl_grid.setItem(rr, 4, it_v)
            self.tbl_grid.setItem(rr, 5, it_d)

            # Geliş
            rr2 = self.tbl_grid.rowCount()
            self.tbl_grid.insertRow(rr2)
            it_route2 = QTableWidgetItem(route_name)
            it_tb2 = QTableWidgetItem(f"C{idx}")
            it_g2 = QTableWidgetItem("")
            it_c2 = QTableWidgetItem(ctxt)
            it_v2 = QTableWidgetItem(plate)
            it_d2 = QTableWidgetItem(dname)
            for it in (it_route2, it_tb2, it_g2, it_c2, it_v2, it_d2):
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            it_tb2.setData(Qt.ItemDataRole.UserRole + 1, str(route_id))
            it_tb2.setData(Qt.ItemDataRole.UserRole + 2, f"C{idx}")
            it_tb2.setData(Qt.ItemDataRole.UserRole + 3, (None if vid is None else str(vid)))
            it_tb2.setData(Qt.ItemDataRole.UserRole + 4, (None if did is None else str(did)))
            self.tbl_grid.setItem(rr2, 0, it_route2)
            self.tbl_grid.setItem(rr2, 1, it_tb2)
            self.tbl_grid.setItem(rr2, 2, it_g2)
            self.tbl_grid.setItem(rr2, 3, it_c2)
            self.tbl_grid.setItem(rr2, 4, it_v2)
            self.tbl_grid.setItem(rr2, 5, it_d2)

    def _remove_selected_grid_rows(self):
        if not hasattr(self, "tbl_grid"):
            return
        rows = sorted({it.row() for it in self.tbl_grid.selectedItems()}, reverse=True)
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

        # Header'ı koru
        if self.tbl_grid.columnCount() == 0:
            headers = ["Güzergah", "Blok", "Giriş", "Çıkış", "Araç", "Şoför"]
            self.tbl_grid.setColumnCount(len(headers))
            self.tbl_grid.setHorizontalHeaderLabels(headers)

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

        for (rid, tb), rec in plan_map.items():
            route_name = self._selected_route_map.get(str(rid), {}).get("route_name", "")
            vid = rec.get("vehicle_id")
            did = rec.get("driver_id")
            plate = self._vehicle_map.get(str(vid or ""), "")
            dname = self._driver_map.get(str(did or ""), "")

            rr = self.table_sefer.rowCount()
            self.table_sefer.insertRow(rr)

            it_route = QTableWidgetItem(route_name)
            it_tb = QTableWidgetItem(str(tb or ""))
            it_g = QTableWidgetItem("")
            it_c = QTableWidgetItem("")
            it_v = QTableWidgetItem(plate)
            it_d = QTableWidgetItem(dname)
            for it in (it_route, it_stops, it_in, it_out, it_v, it_d):
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)

            # Data-roles: route_id / time_block / vehicle_id / driver_id
            it_tb.setData(Qt.ItemDataRole.UserRole + 1, str(rid))
            it_tb.setData(Qt.ItemDataRole.UserRole + 2, str(tb or ""))
            it_tb.setData(Qt.ItemDataRole.UserRole + 3, (None if vid is None else str(vid)))
            it_tb.setData(Qt.ItemDataRole.UserRole + 4, (None if did is None else str(did)))

            self.tbl_grid.setItem(rr, 0, it_route)
            self.tbl_grid.setItem(rr, 1, it_tb)
            self.tbl_grid.setItem(rr, 2, it_g)
            self.tbl_grid.setItem(rr, 3, it_c)
            self.tbl_grid.setItem(rr, 4, it_v)
            self.tbl_grid.setItem(rr, 5, it_d)

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