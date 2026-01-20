
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from datetime import datetime

from PyQt6 import uic
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QInputDialog,
    QComboBox,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QLabel,
    QLineEdit,
    QHBoxLayout,
    QVBoxLayout,
)

from app.core.db_manager import DatabaseManager
from app.utils.style_utils import clear_all_styles
from config import get_ui_path


@dataclass(frozen=True)
class AttendanceContext:
    contract_id: int
    month: str
    service_type: str


class AttendanceApp(QMainWindow):
    def __init__(self, user_data=None, db_manager=None, parent=None):
        super().__init__(parent)
        uic.loadUi(get_ui_path("attendance_window.ui"), self)
        clear_all_styles(self)

        self.user_data = user_data or {}
        self.db = db_manager if db_manager else DatabaseManager()

        self._selected_customer_id = None
        self._selected_contract_id = None

        self._init_filters()
        self._setup_connections()
        self._refresh_lock_ui()

    # ------------------------- UI wiring -------------------------
    def _setup_connections(self):
        if hasattr(self, "btn_toplu_cetele"):
            self.btn_toplu_cetele.clicked.connect(self._open_bulk_attendance)

        if hasattr(self, "btn_onayla_kilitle"):
            self.btn_onayla_kilitle.clicked.connect(self._lock_period)

        if hasattr(self, "btn_onay_kaldir"):
            self.btn_onay_kaldir.clicked.connect(self._unlock_period)

        if hasattr(self, "btn_hesapla"):
            self.btn_hesapla.clicked.connect(self._reload_summary)
            try:
                print("[Attendance] btn_hesapla connected")
            except Exception:
                pass

        if hasattr(self, "cmb_yil"):
            self.cmb_yil.currentIndexChanged.connect(self._refresh_lock_ui)
        if hasattr(self, "cmb_ay"):
            self.cmb_ay.currentIndexChanged.connect(self._refresh_lock_ui)

        if hasattr(self, "cmb_musteri"):
            self.cmb_musteri.currentIndexChanged.connect(self._on_customer_changed)
        if hasattr(self, "cmb_sozlesme"):
            self.cmb_sozlesme.currentIndexChanged.connect(self._on_contract_changed)
        if hasattr(self, "cmb_hizmet_turu"):
            self.cmb_hizmet_turu.currentIndexChanged.connect(self._on_service_type_changed)

        if hasattr(self, "btn_geri_don"):
            self.btn_geri_don.clicked.connect(self._return_to_main)

    # ------------------------- Context helpers -------------------------
    def _is_admin(self) -> bool:
        return (self.user_data or {}).get("role") == "admin"

    def _selected_month_key(self) -> str:
        yil = ""
        ay = ""
        if hasattr(self, "cmb_yil") and self.cmb_yil.currentText():
            yil = self.cmb_yil.currentText().strip()
        if hasattr(self, "cmb_ay") and self.cmb_ay.currentText():
            ay = self.cmb_ay.currentText().strip()

        aylar = {
            "OCAK": "01",
            "ŞUBAT": "02",
            "MART": "03",
            "NİSAN": "04",
            "MAYIS": "05",
            "HAZİRAN": "06",
            "TEMMUZ": "07",
            "AĞUSTOS": "08",
            "EYLÜL": "09",
            "EKİM": "10",
            "KASIM": "11",
            "ARALIK": "12",
        }
        ay_no = aylar.get(ay.upper(), "01") if ay else "01"
        yil = yil or "2025"
        return f"{yil}-{ay_no}"

    def _selected_year_month(self) -> tuple[int, int]:
        ym = self._selected_month_key()
        try:
            y_str, m_str = ym.split("-", 1)
            return int(y_str), int(m_str)
        except Exception:
            return 2025, 1

    def _selected_service_type(self) -> str:
        if hasattr(self, "cmb_hizmet_turu") and self.cmb_hizmet_turu.currentData():
            return str(self.cmb_hizmet_turu.currentData())
        if hasattr(self, "cmb_hizmet_turu") and self.cmb_hizmet_turu.currentText():
            return self.cmb_hizmet_turu.currentText().strip()
        return ""

    def _service_type_values(self, service_type: str) -> list[str]:
        st = (service_type or "").strip()
        if not st:
            return []

        normalized = re.sub(r"\s+", " ", st.upper()).strip()

        mapping = {
            "PERSONEL": ["PERSONEL", "PERSONEL TAŞIMA", "PERSONEL TASIMA"],
            "PERSONEL TAŞIMA": ["PERSONEL TAŞIMA", "PERSONEL", "PERSONEL TASIMA"],
            "PERSONEL TASIMA": ["PERSONEL TASIMA", "PERSONEL TAŞIMA", "PERSONEL"],
            "ÖĞRENCİ": ["ÖĞRENCİ", "ÖĞRENCİ TAŞIMA", "OGRENCI TASIMA", "OGRENCI TAŞIMA"],
            "ÖĞRENCİ TAŞIMA": ["ÖĞRENCİ TAŞIMA", "ÖĞRENCİ", "OGRENCI TASIMA", "OGRENCI TAŞIMA"],
            "OGRENCI": ["OGRENCI", "OGRENCI TASIMA", "ÖĞRENCİ", "ÖĞRENCİ TAŞIMA"],
            "OGRENCI TASIMA": ["OGRENCI TASIMA", "OGRENCI TAŞIMA", "ÖĞRENCİ TAŞIMA", "ÖĞRENCİ"],
            "OGRENCI TAŞIMA": ["OGRENCI TAŞIMA", "OGRENCI TASIMA", "ÖĞRENCİ TAŞIMA", "ÖĞRENCİ"],
        }

        vals = mapping.get(normalized) or [st]
        out = []
        seen = set()
        for v in vals:
            v2 = (v or "").strip()
            if not v2:
                continue
            k = v2.upper()
            if k in seen:
                continue
            seen.add(k)
            out.append(v2)
        return out

    def _current_context(self) -> AttendanceContext | None:
        month = self._selected_month_key()
        contract_id = None
        if hasattr(self, "cmb_sozlesme"):
            contract_id = self.cmb_sozlesme.currentData()
        if not contract_id:
            return None

        service_type = (self._selected_service_type() or "").strip()
        if not service_type or service_type == "Seçiniz...":
            return None

        return AttendanceContext(contract_id=int(contract_id), month=month, service_type=service_type)

    def _is_period_locked(self) -> bool:
        ctx = self._current_context()
        if ctx is None:
            return False
        for st in self._service_type_values(ctx.service_type) or [ctx.service_type]:
            state = self.db.get_trip_period_lock(ctx.contract_id, ctx.month, st)
            if bool((state or {}).get("locked")):
                return True
        return False

    # ------------------------- Lock / unlock -------------------------
    def _refresh_lock_ui(self):
        ctx = self._current_context()
        if ctx is None:
            if hasattr(self, "btn_onayla_kilitle"):
                self.btn_onayla_kilitle.setEnabled(False)
            if hasattr(self, "btn_onay_kaldir"):
                self.btn_onay_kaldir.setEnabled(False)
                self.btn_onay_kaldir.setVisible(False)
            return

        locked = False
        for st in self._service_type_values(ctx.service_type) or [ctx.service_type]:
            state = self.db.get_trip_period_lock(ctx.contract_id, ctx.month, st)
            if bool((state or {}).get("locked")):
                locked = True
                break

        if hasattr(self, "btn_onayla_kilitle"):
            self.btn_onayla_kilitle.setVisible(not locked)
            self.btn_onayla_kilitle.setEnabled(not locked)

        if hasattr(self, "btn_onay_kaldir"):
            can_unlock = locked and self._is_admin()
            self.btn_onay_kaldir.setVisible(can_unlock)
            self.btn_onay_kaldir.setEnabled(can_unlock)

        if hasattr(self, "btn_toplu_cetele"):
            self.btn_toplu_cetele.setEnabled(not locked)

    def _lock_period(self):
        ctx = self._current_context()
        if ctx is None:
            QMessageBox.warning(self, "Uyarı", "Kilit için dönem seçiniz.")
            return

        if not self._validate_planned_entries_complete(ctx):
            return
        user_id = int((self.user_data or {}).get("id") or 0)
        ok = self.db.set_trip_period_locked(ctx.contract_id, ctx.month, ctx.service_type, user_id)
        if not ok:
            QMessageBox.critical(self, "Hata", "Dönem kilitlenemedi.")
            return
        QMessageBox.information(self, "Bilgi", "Dönem onaylandı ve kilitlendi.")
        self._refresh_lock_ui()

    def _validate_planned_entries_complete(self, ctx: AttendanceContext) -> bool:
        try:
            y_str, m_str = (ctx.month or "").split("-", 1)
            year = int(y_str)
            month = int(m_str)
        except Exception:
            return True

        days_in_month = QDate(year, month, 1).daysInMonth()
        start_date = QDate(year, month, 1).toString("yyyy-MM-dd")
        end_date = QDate(year, month, days_in_month).toString("yyyy-MM-dd")

        plan_rows = []
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            st_values = self._service_type_values(ctx.service_type) or [str(ctx.service_type)]
            placeholders = ",".join(["?"] * len(st_values))
            cursor.execute(
                f"""
                SELECT route_params_id, time_block
                FROM trip_plan
                WHERE contract_id = ? AND month = ? AND service_type IN ({placeholders})
                """,
                (int(ctx.contract_id), str(ctx.month), *st_values),
            )
            plan_rows = cursor.fetchall() or []
            conn.close()
        except Exception:
            plan_rows = []

        if not plan_rows:
            return True

        missing = []
        try:
            conn2 = self.db.connect()
            cur2 = conn2.cursor()
            st_values = self._service_type_values(ctx.service_type) or [str(ctx.service_type)]
            placeholders = ",".join(["?"] * len(st_values))
            for rid, tb in plan_rows:
                rid_i = int(rid or 0)
                tb_s = str(tb or "")
                if rid_i <= 0 or not tb_s:
                    continue
                cur2.execute(
                    f"""
                    SELECT trip_date
                    FROM trip_entries
                    WHERE contract_id = ?
                      AND route_params_id = ?
                      AND service_type IN ({placeholders})
                      AND time_block = ?
                      AND trip_date BETWEEN ? AND ?
                    """,
                    (
                        int(ctx.contract_id),
                        int(rid_i),
                        *st_values,
                        str(tb_s),
                        start_date,
                        end_date,
                    ),
                )
                existing_dates = {str(r[0] or "") for r in (cur2.fetchall() or [])}
                if len(existing_dates) >= days_in_month:
                    continue
                for day in range(1, days_in_month + 1):
                    d = QDate(year, month, day).toString("yyyy-MM-dd")
                    if d not in existing_dates:
                        missing.append((rid_i, tb_s, d))
                        if len(missing) >= 20:
                            break
                if len(missing) >= 20:
                    break
            conn2.close()
        except Exception:
            try:
                conn2.close()
            except Exception:
                pass
            return True

        if not missing:
            return True

        route_names = {}
        try:
            conn3 = self.db.connect()
            cur3 = conn3.cursor()
            st_values = self._service_type_values(ctx.service_type) or [str(ctx.service_type)]
            placeholders = ",".join(["?"] * len(st_values))
            cur3.execute(
                f"""
                SELECT id, COALESCE(route_name,'')
                FROM route_params
                WHERE contract_id = ? AND service_type IN ({placeholders})
                """,
                (int(ctx.contract_id), *st_values),
            )
            for rid, rn in cur3.fetchall() or []:
                try:
                    route_names[int(rid)] = str(rn or "")
                except Exception:
                    pass
            conn3.close()
        except Exception:
            route_names = {}

        lines = []
        for rid_i, tb_s, d in missing:
            rn = route_names.get(int(rid_i), str(rid_i))
            lines.append(f"{rn} / {tb_s} / {d}")

        QMessageBox.warning(
            self,
            "Uyarı",
            "Planlı satırlarda boş gün bırakılamaz. Eksik girişler var:\n\n" + "\n".join(lines),
        )
        return False

    def _unlock_period(self):
        if not self._is_admin():
            QMessageBox.warning(self, "Uyarı", "Onay kaldırma sadece admin yetkisiyle yapılır.")
            return
        ctx = self._current_context()
        if ctx is None:
            QMessageBox.warning(self, "Uyarı", "Kilit için dönem seçiniz.")
            return

        reason, ok = QInputDialog.getText(self, "Onay Kaldır", "Onay kaldırma sebebi:")
        if not ok:
            return
        admin_user_id = int((self.user_data or {}).get("id") or 0)
        ok2 = self.db.set_trip_period_unlocked(
            ctx.contract_id,
            ctx.month,
            ctx.service_type,
            admin_user_id,
            (reason or "").strip(),
        )
        if not ok2:
            QMessageBox.critical(self, "Hata", "Onay kaldırılamadı.")
            return
        QMessageBox.information(self, "Bilgi", "Onay kaldırıldı. Dönem tekrar düzenlenebilir.")
        self._refresh_lock_ui()

    # ------------------------- Data actions (placeholder) -------------------------
    def _reload_summary(self):
        if not hasattr(self, "lbl_ozet"):
            return
        try:
            self.lbl_ozet.setText("Yükleniyor...")
        except Exception:
            pass
        try:
            print("[Attendance] _reload_summary called")
        except Exception:
            pass
        ctx = self._current_context()
        if ctx is None:
            try:
                c_m = self.cmb_musteri.currentData() if hasattr(self, "cmb_musteri") else None
                c_s = self.cmb_sozlesme.currentData() if hasattr(self, "cmb_sozlesme") else None
                c_h = self._selected_service_type() if hasattr(self, "cmb_hizmet_turu") else None
                print(f"[Attendance] ctx=None müşteri={c_m} sözleşme={c_s} hizmet={c_h}")
            except Exception:
                pass
            self.lbl_ozet.setText("Müşteri / Sözleşme / Hizmet seçiniz")
            return

        y, m = self._selected_year_month()
        days_in_month = QDate(y, m, 1).daysInMonth()
        start_date = QDate(y, m, 1).toString("yyyy-MM-dd")
        end_date = QDate(y, m, days_in_month).toString("yyyy-MM-dd")
        total = 0
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            st_values = self._service_type_values(ctx.service_type) or [str(ctx.service_type)]
            placeholders = ",".join(["?"] * len(st_values))
            cursor.execute(
                f"""
                SELECT COALESCE(SUM(qty),0)
                FROM trip_entries
                WHERE contract_id = ?
                  AND service_type IN ({placeholders})
                  AND trip_date BETWEEN ? AND ?
                """,
                (int(ctx.contract_id), *st_values, start_date, end_date),
            )
            row = cursor.fetchone()
            conn.close()
            total = float((row or [0])[0] or 0)
        except Exception:
            total = 0

        locked = self._is_period_locked()
        lock_txt = "KİLİTLİ" if locked else "AÇIK"
        self.lbl_ozet.setText(f"Toplam Sefer: {total} | Durum: {lock_txt}")

    def _open_bulk_attendance(self):
        if self._is_period_locked():
            QMessageBox.information(self, "Bilgi", "Bu dönem kilitli. Toplu puantaj girişi yapılamaz.")
            return
        ctx = self._current_context()
        if ctx is None:
            QMessageBox.warning(self, "Uyarı", "Müşteri / Sözleşme / Hizmet seçiniz.")
            return

        dlg = BulkAttendanceDialog(
            parent=self,
            db=self.db,
            contract_id=ctx.contract_id,
            service_type=ctx.service_type,
            year_month=self._selected_year_month(),
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._reload_summary()
            self._refresh_lock_ui()

    # ------------------------- Navigation -------------------------
    def _return_to_main(self):
        p = self.parent()
        while p is not None:
            if hasattr(p, "mainStack"):
                try:
                    page_main = getattr(p, "page_main", None)
                    if page_main is not None:
                        p.mainStack.setCurrentWidget(page_main)
                except Exception:
                    pass
                break
            p = p.parent()

    # ------------------------- Filters -------------------------
    def _init_filters(self):
        if hasattr(self, "cmb_hizmet_turu"):
            self.cmb_hizmet_turu.blockSignals(True)
            self.cmb_hizmet_turu.clear()
            self.cmb_hizmet_turu.addItem("Seçiniz...", None)
            self.cmb_hizmet_turu.addItem("ÖĞRENCİ TAŞIMA", "ÖĞRENCİ TAŞIMA")
            self.cmb_hizmet_turu.addItem("PERSONEL TAŞIMA", "PERSONEL TAŞIMA")
            self.cmb_hizmet_turu.addItem("ARAÇ KİRALAMA", "ARAÇ KİRALAMA")
            self.cmb_hizmet_turu.addItem("DİĞER", "DİĞER")
            self.cmb_hizmet_turu.setCurrentIndex(0)
            self.cmb_hizmet_turu.blockSignals(False)

        if hasattr(self, "cmb_musteri"):
            self.cmb_musteri.blockSignals(True)
            self.cmb_musteri.clear()
            self.cmb_musteri.addItem("Seçiniz...", None)
            for cid, title in self.db.get_active_customers_list():
                self.cmb_musteri.addItem(title or "", int(cid))
            self.cmb_musteri.blockSignals(False)

        if hasattr(self, "cmb_sozlesme"):
            self.cmb_sozlesme.clear()
            self.cmb_sozlesme.addItem("Seçiniz...", None)

    def _on_customer_changed(self):
        self._selected_customer_id = self.cmb_musteri.currentData() if hasattr(self, "cmb_musteri") else None
        self._selected_contract_id = None
        if not hasattr(self, "cmb_sozlesme"):
            return
        self.cmb_sozlesme.blockSignals(True)
        self.cmb_sozlesme.clear()
        self.cmb_sozlesme.addItem("Seçiniz...", None)
        if self._selected_customer_id:
            rows = self.db.get_active_contracts_by_customer(int(self._selected_customer_id))
            for cid, cno, sdate, edate in rows:
                label = f"{cno or ''} ({(sdate or '').strip()} - {(edate or '').strip()})"
                self.cmb_sozlesme.addItem(label, int(cid))
        self.cmb_sozlesme.blockSignals(False)
        self._refresh_lock_ui()

    def _on_contract_changed(self):
        self._selected_contract_id = self.cmb_sozlesme.currentData() if hasattr(self, "cmb_sozlesme") else None
        if (self._selected_service_type() or "").strip() and (self._selected_service_type() or "").strip() != "Seçiniz...":
            self._reload_summary()
        self._refresh_lock_ui()

    def _on_service_type_changed(self):
        self._reload_summary()
        self._refresh_lock_ui()


class BulkAttendanceDialog(QDialog):
    def _extract_movement_type(self, rec: dict) -> str:
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
        return str(raw or "").strip().lower()

    def __init__(
        self,
        parent: QMainWindow,
        db: DatabaseManager,
        contract_id: int,
        service_type: str,
        year_month: tuple[int, int],
    ):
        super().__init__(parent)
        self.db = db
        self.contract_id = int(contract_id)
        self.service_type = (service_type or "").strip()
        self.year, self.month = year_month

        self.setWindowTitle("Toplu Puantaj")
        self.setWindowState(Qt.WindowState.WindowMaximized)

        self.days_in_month = QDate(self.year, self.month, 1).daysInMonth()
        self.max_days = 31
        self.month_key = f"{int(self.year)}-{int(self.month):02d}"

        self.table = QTableWidget(self)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)

        headers = ["KAPASİTE", "GÜZERGAH", "ARAÇ", "ŞOFÖR", "GİRİŞ ÇIKIŞ SAATLERİ"]
        for d in range(1, self.max_days + 1):
            if d <= self.days_in_month:
                qd = QDate(self.year, self.month, d)
                gun_adi = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"][qd.dayOfWeek() - 1]
                headers.append(f"{d}\n{gun_adi}")
            else:
                headers.append(str(d))
        headers.extend(["TOPLAM", "FİYAT", "TOPLAM"])

        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        day_start = 5
        for i in range(day_start, day_start + self.max_days):
            h.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(i, 30)
        h.setSectionResizeMode(day_start + self.max_days, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(day_start + self.max_days + 1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(day_start + self.max_days + 2, QHeaderView.ResizeMode.ResizeToContents)

        self._day_start = day_start
        self._col_total_qty = day_start + self.max_days
        self._col_price = day_start + self.max_days + 1
        self._col_total_price = day_start + self.max_days + 2

        self._col_vehicle = 2
        self._col_driver = 3
        self._col_time_text = 4

        self._vehicle_map = {}
        self._driver_map = {}
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

        self._route_rows = []
        try:
            st_values = AttendanceApp._service_type_values(self, self.service_type) or [self.service_type]
        except Exception:
            st_values = [self.service_type]
        for st in st_values:
            try:
                rows = self.db.get_route_params_for_contract(self.contract_id, str(st))
                if rows:
                    self._route_rows = rows
                    break
            except Exception:
                continue
        self._row_meta = []
        self._planned_keys = set()
        self._alloc_override_map = {}

        self._bg_weekend = QColor("#f0f0f0")
        self._bg_qty = QColor("#fff3cd")
        self._bg_override = QColor("#f8c291")

        def _fixed_time_blocks():
            return ["08:00", "08:15", "16:00", "16:15", "00:00", "00:15"]

        def _parse_time(s: str):
            txt = (s or "").strip()
            if not txt:
                return None
            parts = txt.split(":")
            if len(parts) != 2:
                return None
            if not parts[0].isdigit() or not parts[1].isdigit():
                return None
            hh = int(parts[0])
            mm = int(parts[1])
            if hh < 0 or hh > 23 or mm < 0 or mm > 59:
                return None
            return hh, mm

        def _add_minutes(hh: int, mm: int, add_min: int) -> str:
            total = (hh * 60 + mm + add_min) % (24 * 60)
            nh = total // 60
            nm = total % 60
            return f"{nh:02d}:{nm:02d}"

        def _get_custom_times(contract_id: int, month: str, service_type: str):
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
                    (int(contract_id), str(month), str(service_type)),
                )
                row = cursor.fetchone()
                conn.close()
            except Exception:
                row = None
            if not row:
                return None, None
            return (row[0] or "").strip(), (row[1] or "").strip()

        def _time_blocks_for_context(contract_id: int, month: str, service_type: str):
            blocks = list(_fixed_time_blocks())
            c1, c2 = _get_custom_times(contract_id, month, service_type)
            for ct in [c1, c2]:
                parsed = _parse_time(ct)
                if parsed is None:
                    continue
                hh, mm = parsed
                blocks.append(f"{hh:02d}:{mm:02d}")
                blocks.append(_add_minutes(hh, mm, 15))

            uniq = []
            seen = set()
            for b in blocks:
                bb = (b or "").strip()
                if not bb:
                    continue
                if bb in seen:
                    continue
                seen.add(bb)
                uniq.append(bb)
            return uniq

        def _legacy_time_blocks_for_month(start_date: str, end_date: str):
            try:
                conn = self.db.connect()
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT DISTINCT time_block
                    FROM trip_entries
                    WHERE contract_id = ?
                      AND service_type = ?
                      AND trip_date BETWEEN ? AND ?
                    """,
                    (int(self.contract_id), str(self.service_type), start_date, end_date),
                )
                out = [str(r[0] or "").strip() for r in (cursor.fetchall() or [])]
                conn.close()
                return [x for x in out if x]
            except Exception:
                return []

        def _planned_keys_for_context(contract_id: int, month: str, service_type: str):
            try:
                conn = self.db.connect()
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT route_params_id, time_block
                    FROM trip_plan
                    WHERE contract_id = ? AND month = ? AND service_type = ?
                    """,
                    (int(contract_id), str(month), str(service_type)),
                )
                rows = cursor.fetchall() or []
                conn.close()
                return {(int(r[0] or 0), str(r[1] or "")) for r in rows if int(r[0] or 0) and str(r[1] or "")}
            except Exception:
                return set()

        def _tb_sort_key(tb_val: str):
            tbs = str(tb_val or "").strip().upper()
            m = re.match(r"^([GC])(\d)$", tbs)
            if m:
                gc = 0 if m.group(1) == "G" else 1
                return (0, int(m.group(2)), gc)
            parsed = _parse_time(tbs)
            if parsed is not None:
                hh, mm = parsed
                return (1, hh * 60 + mm, 0)
            return (2, 9999, 0)

        def _time_text_for_time_block(tb_val: str) -> str:
            tbs = str(tb_val or "").strip().upper()
            m = re.match(r"^([GC])(\d)$", tbs)
            if m:
                idx = int(m.group(2))
                fixed = _fixed_time_blocks()
                if len(fixed) >= 6 and idx in (1, 2, 3):
                    gi = (idx - 1) * 2
                    ci = gi + 1
                    if m.group(1) == "G":
                        return str(fixed[gi])
                    return str(fixed[ci])
            parsed = _parse_time(tbs)
            if parsed is not None:
                hh, mm = parsed
                return f"{hh:02d}:{mm:02d}"
            return str(tb_val or "")

        def add_subrow(route_params_id: int, route_name: str, time_block: str, label: str):
            row = self.table.rowCount()
            self.table.insertRow(row)

            cap = QTableWidgetItem("")
            cap.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, cap)

            r_item = QTableWidgetItem(route_name or "")
            r_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            r_item.setData(Qt.ItemDataRole.UserRole, int(route_params_id))
            self.table.setItem(row, 1, r_item)

            cmb_v = QComboBox()
            cmb_v.addItem("Seçiniz...", None)
            for vcode, plate in self._vehicle_map.items():
                cmb_v.addItem(plate, vcode)
            self.table.setCellWidget(row, self._col_vehicle, cmb_v)

            cmb_d = QComboBox()
            cmb_d.addItem("Seçiniz...", None)
            for did, name in self._driver_map.items():
                cmb_d.addItem(name, did)
            self.table.setCellWidget(row, self._col_driver, cmb_d)

            t_item = QTableWidgetItem(_time_text_for_time_block(label))
            self.table.setItem(row, self._col_time_text, t_item)

            for d in range(1, self.max_days + 1):
                col = self._day_start + (d - 1)
                it = QTableWidgetItem("")
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if d > self.days_in_month:
                    it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    it.setBackground(QColor("#f0f0f0"))
                elif QDate(self.year, self.month, d).dayOfWeek() in (6, 7):
                    it.setBackground(self._bg_weekend)
                self.table.setItem(row, col, it)

            is_planned = (int(route_params_id), str(time_block)) in (self._planned_keys or set())
            if is_planned:
                planned_bg = QColor("#fff3cd")
                planned_font = QFont()
                planned_font.setBold(True)

                for cc in (0, 1, self._col_time_text):
                    it0 = self.table.item(row, cc)
                    if it0 is not None:
                        it0.setBackground(planned_bg)
                        it0.setFont(planned_font)
                for cc in (self._col_vehicle, self._col_driver):
                    w = self.table.cellWidget(row, cc)
                    if w is not None:
                        try:
                            w.setStyleSheet("background-color: #fff3cd;")
                        except Exception:
                            pass

            total_item = QTableWidgetItem("0")
            total_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            total_item.setBackground(QColor("#dfe6e9"))
            self.table.setItem(row, self._col_total_qty, total_item)

            price_item = QTableWidgetItem("0")
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, self._col_price, price_item)

            total_price_item = QTableWidgetItem("0")
            total_price_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            total_price_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            total_price_item.setBackground(QColor("#dfe6e9"))
            self.table.setItem(row, self._col_total_price, total_price_item)

            self._row_meta.append(
                {
                    "route_params_id": int(route_params_id),
                    "sub_index": 0,
                    "time_block": str(time_block),
                }
            )

        self.table.setRowCount(0)

        start_date = QDate(self.year, self.month, 1).toString("yyyy-MM-dd")
        end_date = QDate(self.year, self.month, self.days_in_month).toString("yyyy-MM-dd")

        self._planned_keys = _planned_keys_for_context(int(self.contract_id), self.month_key, str(self.service_type))

        if self._planned_keys:
            planned_blocks = sorted({str(tb) for _rid, tb in self._planned_keys if str(tb)}, key=_tb_sort_key)
            for row in self._route_rows:
                try:
                    rid = int(row[0] or 0)
                    rname = row[1] if len(row) > 1 else ""
                except Exception:
                    continue
                for tb in planned_blocks:
                    if (int(rid), str(tb)) in self._planned_keys:
                        add_subrow(int(rid), rname or "", str(tb), str(tb))
        else:
            time_blocks = ["G1", "C1", "G2", "C2", "G3", "C3"]
            legacy_blocks = _legacy_time_blocks_for_month(start_date, end_date)
            for lb in legacy_blocks:
                if lb not in time_blocks:
                    time_blocks.append(lb)
            time_blocks = sorted([str(x) for x in time_blocks if str(x)], key=_tb_sort_key)

            for row in self._route_rows:
                try:
                    rid = int(row[0] or 0)
                    rname = row[1] if len(row) > 1 else ""
                except Exception:
                    continue
                for tb in time_blocks:
                    add_subrow(int(rid), rname or "", str(tb), str(tb))

        self.btn_save = QPushButton("KAYDET", self)
        self.btn_save.clicked.connect(self._save)

        lay = QVBoxLayout()
        lay.addWidget(self.table)
        lay.addWidget(self.btn_save)
        self.setLayout(lay)

        self._load_existing_entries()

        self.table.itemChanged.connect(self._recalc_row_total)

        try:
            # Context menu events come from the viewport in QTableWidget
            self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.table.customContextMenuRequested.connect(self._open_cell_menu)
            self.table.viewport().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.table.viewport().customContextMenuRequested.connect(self._open_cell_menu)
        except Exception:
            pass

    def _day_for_col(self, col: int) -> int | None:
        if col < self._day_start or col >= self._day_start + self.max_days:
            return None
        day_num = (col - self._day_start) + 1
        if day_num < 1 or day_num > self.days_in_month:
            return None
        return day_num

    def _is_weekend_day(self, day_num: int) -> bool:
        try:
            return QDate(self.year, self.month, int(day_num)).dayOfWeek() in (6, 7)
        except Exception:
            return False

    def _override_key(self, row: int, col: int):
        day_num = self._day_for_col(col)
        if day_num is None:
            return None
        it_route = self.table.item(row, 1)
        if it_route is None:
            return None
        route_params_id = it_route.data(Qt.ItemDataRole.UserRole)
        if not route_params_id:
            return None
        meta = self._row_meta[row] if row < len(self._row_meta) else None
        time_block = str((meta or {}).get("time_block") or "").strip()
        if not time_block:
            return None
        trip_date = QDate(self.year, self.month, day_num).toString("yyyy-MM-dd")
        return int(route_params_id), str(time_block), str(trip_date)

    def _apply_day_cell_style(self, row: int, col: int):
        day_num = self._day_for_col(col)
        if day_num is None:
            return
        it = self.table.item(row, col)
        if it is None:
            return

        key = self._override_key(row, col)
        has_override = False
        if key is not None:
            rec = self._alloc_override_map.get(key) or {}
            has_override = bool(rec.get("is_override"))

        txt = (it.text() or "").strip()
        has_qty = bool(txt.isdigit() and int(txt) > 0)

        if has_override:
            it.setBackground(self._bg_override)
            return
        if has_qty:
            it.setBackground(self._bg_qty)
            return
        if self._is_weekend_day(day_num):
            it.setBackground(self._bg_weekend)
            return
        it.setBackground(QColor("#ffffff"))

    def _open_cell_menu(self, pos):
        it = None
        try:
            it = self.table.itemAt(pos)
        except Exception:
            it = None

        if it is not None:
            r = it.row()
            c = it.column()
        else:
            # Fallback for cases where itemAt fails (e.g. click on empty area)
            try:
                r = self.table.rowAt(pos.y())
                c = self.table.columnAt(pos.x())
            except Exception:
                return
            if r < 0 or c < 0:
                return
        if c < self._day_start or c >= self._day_start + self.max_days:
            return
        day_num = self._day_for_col(c)
        if day_num is None:
            return

        it_route = self.table.item(r, 1)
        if it_route is None:
            return
        route_params_id = it_route.data(Qt.ItemDataRole.UserRole)
        if not route_params_id:
            return

        meta = self._row_meta[r] if r < len(self._row_meta) else None
        time_block = str((meta or {}).get("time_block") or "")
        if not time_block:
            return

        # Apply to selected day cells on the same row (range support)
        selected_cols = set()
        try:
            for sit in self.table.selectedItems() or []:
                if sit is None:
                    continue
                if sit.row() != r:
                    continue
                cc = sit.column()
                if cc < self._day_start or cc >= self._day_start + self.max_days:
                    continue
                dd = (cc - self._day_start) + 1
                if dd < 1 or dd > self.days_in_month:
                    continue
                selected_cols.add(cc)
        except Exception:
            selected_cols = set()
        if not selected_cols:
            selected_cols = {c}

        selected_days = sorted({(cc - self._day_start) + 1 for cc in selected_cols})
        selected_dates = [QDate(self.year, self.month, d).toString("yyyy-MM-dd") for d in selected_days]
        first_trip_date = selected_dates[0]
        key = (int(route_params_id), str(time_block), str(first_trip_date))

        default_vehicle_id = None
        default_driver_id = None
        cmb_v = self.table.cellWidget(r, self._col_vehicle)
        cmb_d = self.table.cellWidget(r, self._col_driver)
        if cmb_v is not None:
            default_vehicle_id = cmb_v.currentData()
        if cmb_d is not None:
            default_driver_id = cmb_d.currentData()

        current = self._alloc_override_map.get(key) or {}
        cur_vehicle_id = current.get("vehicle_id")
        cur_driver_id = current.get("driver_id")
        cur_note = current.get("note") or ""

        dlg = QDialog(self)
        if len(selected_dates) == 1:
            dlg.setWindowTitle(f"Günlük Atama / Not ({first_trip_date})")
        else:
            dlg.setWindowTitle(f"Günlük Atama / Not ({selected_dates[0]} .. {selected_dates[-1]})")
        lay = QVBoxLayout(dlg)

        if len(selected_dates) > 1:
            info = QLabel(f"Uygulanacak gün sayısı: {len(selected_dates)}")
            lay.addWidget(info)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Araç:"))
        cmb_v2 = QComboBox()
        cmb_v2.addItem("Varsayılan", "__DEFAULT__")
        for vcode, plate in self._vehicle_map.items():
            cmb_v2.addItem(plate, vcode)
        row1.addWidget(cmb_v2)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Şoför:"))
        cmb_d2 = QComboBox()
        cmb_d2.addItem("Varsayılan", "__DEFAULT__")
        for did, name in self._driver_map.items():
            cmb_d2.addItem(name, did)
        row2.addWidget(cmb_d2)
        lay.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Not:"))
        txt_note = QLineEdit()
        txt_note.setText(str(cur_note))
        row3.addWidget(txt_note)
        lay.addLayout(row3)

        btns = QHBoxLayout()
        btn_clear = QPushButton("Temizle")
        btn_cancel = QPushButton("Vazgeç")
        btn_ok = QPushButton("Kaydet")
        btns.addWidget(btn_clear)
        btns.addStretch(1)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        lay.addLayout(btns)

        def _prefill_combo(cmb: QComboBox, value, default_value):
            val = value if value is not None and str(value).strip() else "__DEFAULT__"
            if val == "__DEFAULT__" and default_value is not None and str(default_value).strip():
                val = str(default_value)
            idx = cmb.findData(str(val))
            if idx >= 0:
                cmb.setCurrentIndex(idx)

        _prefill_combo(cmb_v2, cur_vehicle_id, default_vehicle_id)
        _prefill_combo(cmb_d2, cur_driver_id, default_driver_id)

        def _apply(clear_only: bool = False):
            if clear_only:
                for trip_date in selected_dates:
                    k = (int(route_params_id), str(time_block), str(trip_date))
                    if k in self._alloc_override_map:
                        del self._alloc_override_map[k]
                for cc in selected_cols:
                    self._mark_day_override_cell(r, cc, None)
                dlg.accept()
                return

            vsel = cmb_v2.currentData()
            dsel = cmb_d2.currentData()
            note = (txt_note.text() or "").strip()

            if vsel == "__DEFAULT__":
                vsel = default_vehicle_id
            if dsel == "__DEFAULT__":
                dsel = default_driver_id

            if (not vsel) and (not dsel) and (not note):
                for trip_date in selected_dates:
                    k = (int(route_params_id), str(time_block), str(trip_date))
                    if k in self._alloc_override_map:
                        del self._alloc_override_map[k]
                for cc in selected_cols:
                    self._mark_day_override_cell(r, cc, None)
                dlg.accept()
                return

            is_override = False
            if vsel is not None and str(vsel).strip() and default_vehicle_id is not None and str(default_vehicle_id).strip():
                if str(vsel) != str(default_vehicle_id):
                    is_override = True
            if dsel is not None and str(dsel).strip() and default_driver_id is not None and str(default_driver_id).strip():
                if str(dsel) != str(default_driver_id):
                    is_override = True
            if note:
                is_override = True

            for trip_date in selected_dates:
                self._alloc_override_map[(int(route_params_id), str(time_block), str(trip_date))] = {
                    "vehicle_id": vsel,
                    "driver_id": dsel,
                    "note": note,
                    "is_override": bool(is_override),
                }
            for cc in selected_cols:
                self._mark_day_override_cell(r, cc, note)
            dlg.accept()

        btn_ok.clicked.connect(lambda: _apply(clear_only=False))
        btn_cancel.clicked.connect(dlg.reject)
        btn_clear.clicked.connect(lambda: _apply(clear_only=True))

        dlg.exec()

    def _mark_day_override_cell(self, row: int, col: int, note_text: str | None):
        it = self.table.item(row, col)
        if it is None:
            return
        if note_text is None:
            it.setToolTip("")
            self._apply_day_cell_style(row, col)
            return
        it.setToolTip((note_text or "").strip())
        self._apply_day_cell_style(row, col)

    def _recalc_row_total(self, item: QTableWidgetItem):
        if item is None:
            return
        r = item.row()
        c = item.column()
        if c in (0, 1, self._col_vehicle, self._col_driver, self._col_time_text, self._col_total_qty, self._col_total_price):
            return

        if c == self._col_price:
            try:
                txtp = (item.text() or "").strip().replace(",", ".")
                float(txtp) if txtp else 0.0
            except Exception:
                item.setText("0")
            self._recalc_price_total_for_row(r)
            return

        if c < self._day_start or c >= self._day_start + self.max_days:
            return

        day_num = (c - self._day_start) + 1
        if day_num > self.days_in_month:
            try:
                item.setText("")
            except Exception:
                pass
            return

        txt = (item.text() or "").strip()
        if txt and (not txt.isdigit()):
            item.setText("")
            self._apply_day_cell_style(r, c)
            return
        if txt and int(txt) < 0:
            item.setText("")
            self._apply_day_cell_style(r, c)
            return

        total = 0
        for day_col in range(self._day_start, self._day_start + self.days_in_month):
            it = self.table.item(r, day_col)
            if it and (it.text() or "").strip().isdigit():
                total += int(it.text().strip())
        t_item = self.table.item(r, self._col_total_qty)
        if t_item is not None:
            t_item.setText(str(total))

        self._recalc_price_total_for_row(r)
        self._apply_day_cell_style(r, c)

    def _recalc_price_total_for_row(self, row: int):
        t_item = self.table.item(row, self._col_total_qty)
        p_item = self.table.item(row, self._col_price)
        out_item = self.table.item(row, self._col_total_price)
        if t_item is None or p_item is None or out_item is None:
            return
        try:
            qty = int((t_item.text() or "0").strip() or 0)
        except Exception:
            qty = 0
        try:
            price = float((p_item.text() or "0").strip().replace(",", ".") or 0)
        except Exception:
            price = 0.0
        out_item.setText(str(int(qty * price) if price.is_integer() else round(qty * price, 2)))

    def _load_existing_entries(self):
        start_date = QDate(self.year, self.month, 1).toString("yyyy-MM-dd")
        end_date = QDate(self.year, self.month, self.days_in_month).toString("yyyy-MM-dd")

        row_index = {}
        for idx, meta in enumerate(self._row_meta):
            key = (int(meta.get("route_params_id") or 0), str(meta.get("time_block") or ""))
            if key[0] and key[1]:
                row_index[key] = idx

        rows = []
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT route_params_id, trip_date, time_block, qty, COALESCE(time_text,'')
                FROM trip_entries
                WHERE contract_id = ?
                  AND service_type = ?
                  AND trip_date BETWEEN ? AND ?
                """,
                (int(self.contract_id), str(self.service_type), start_date, end_date),
            )
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            rows = []

        alloc_rows = []
        try:
            alloc_rows = self.db.get_trip_allocations_for_range(self.contract_id, self.service_type, start_date, end_date)
        except Exception:
            alloc_rows = []

        if not rows:
            rows = []

        price_rows = []
        try:
            price_rows = self.db.get_trip_prices_for_month(self.contract_id, self.month_key, self.service_type)
        except Exception:
            price_rows = []

        price_map = {}
        for rpid, tblock, price in price_rows or []:
            try:
                price_map[(int(rpid or 0), str(tblock or ""))] = float(price or 0.0)
            except Exception:
                price_map[(int(rpid or 0), str(tblock or ""))] = 0.0

        route_default_price = {}
        for (rpid, _tb), pr in price_map.items():
            if int(rpid or 0) <= 0:
                continue
            if int(rpid) in route_default_price:
                continue
            try:
                route_default_price[int(rpid)] = float(pr or 0.0)
            except Exception:
                route_default_price[int(rpid)] = 0.0

        def _norm_route_name(s: str) -> str:
            txt = (s or "").strip().lower()
            if not txt:
                return ""
            txt = re.sub(r"\s+", "", txt)
            txt = re.sub(r"[^0-9a-zçğıöşü]", "", txt)
            return txt

        def _norm_route_variants(s: str):
            base = _norm_route_name(s)
            out = []
            if base:
                out.append(base)
                if base.endswith("v") and len(base) > 1:
                    out.append(base[:-1])
                else:
                    out.append(base + "v")
            uniq = []
            seen = set()
            for x in out:
                if x and x not in seen:
                    seen.add(x)
                    uniq.append(x)
            return uniq

        contract_price_by_name = {}
        contract_price_by_norm = {}
        contract_price_by_name_mt = {}
        contract_price_by_norm_mt = {}
        ambiguous_names = set()
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COALESCE(price_matrix_json,'') FROM contracts WHERE id = ? LIMIT 1",
                (int(self.contract_id),),
            )
            row = cursor.fetchone()
            conn.close()
            price_json = (row[0] if row else "") or ""
        except Exception:
            price_json = ""

        if price_json:
            try:
                parsed = json.loads(price_json)
            except Exception:
                parsed = []
            if isinstance(parsed, list):
                for rec in parsed:
                    guz = str((rec or {}).get("guzergah") or "").strip().lower()
                    if not guz:
                        continue
                    st = str(
                        (rec or {}).get("_service_type")
                        or (rec or {}).get("service_type")
                        or ""
                    ).strip()
                    if st and st.lower() != str(self.service_type).strip().lower():
                        continue
                    mt = self._extract_movement_type(rec or {})
                    try:
                        pr = float((rec or {}).get("fiyat") or 0.0)
                    except Exception:
                        pr = 0.0

                    # route_name-only price is only safe when guzergah is unique.
                    # If the same guzergah appears multiple times (typically different movement types),
                    # we mark it ambiguous and disable route_name-only fallback for it.
                    if guz in contract_price_by_name:
                        ambiguous_names.add(guz)
                    else:
                        contract_price_by_name[guz] = pr

                    for ng in _norm_route_variants(guz):
                        if not ng:
                            continue
                        if ng in contract_price_by_norm:
                            ambiguous_names.add(guz)
                        else:
                            contract_price_by_norm[ng] = pr

                    contract_price_by_name_mt[(guz, mt)] = pr
                    for ng in _norm_route_variants(guz):
                        nk = (ng, mt)
                        if ng and nk not in contract_price_by_norm_mt:
                            contract_price_by_norm_mt[nk] = pr

        route_price_by_id = {}
        if contract_price_by_name or contract_price_by_norm or contract_price_by_name_mt or contract_price_by_norm_mt:
            for row in self._route_rows:
                try:
                    rid = row[0]
                    rname = row[1] if len(row) > 1 else ""
                    mt_r = row[3] if len(row) > 3 else ""
                except Exception:
                    continue
                try:
                    rpid = int(rid)
                except Exception:
                    continue
                rn = (rname or "").strip().lower()
                if not rn:
                    continue
                mt_rn = (mt_r or "").strip().lower()
                pr = None
                if mt_rn and (rn, mt_rn) in contract_price_by_name_mt:
                    pr = float(contract_price_by_name_mt.get((rn, mt_rn)) or 0.0)
                elif rn in contract_price_by_name and rn not in ambiguous_names:
                    pr = float(contract_price_by_name.get(rn) or 0.0)
                else:
                    for nrn in _norm_route_variants(rn):
                        if mt_rn:
                            nk = (nrn, mt_rn)
                            if nrn and nk in contract_price_by_norm_mt:
                                pr = float(contract_price_by_norm_mt.get(nk) or 0.0)
                                break
                        if nrn and nrn in contract_price_by_norm and rn not in ambiguous_names:
                            pr = float(contract_price_by_norm.get(nrn) or 0.0)
                            break
                    if pr is None:
                        nrn0 = _norm_route_name(rn)
                        if nrn0:
                            if mt_rn:
                                for (k_norm, k_mt), v_pr in contract_price_by_norm_mt.items():
                                    if k_mt != mt_rn:
                                        continue
                                    if nrn0 in k_norm or k_norm in nrn0:
                                        pr = float(v_pr or 0.0)
                                        break
                            if pr is None and rn not in ambiguous_names:
                                for k_norm, v_pr in contract_price_by_norm.items():
                                    if nrn0 in k_norm or k_norm in nrn0:
                                        pr = float(v_pr or 0.0)
                                        break
                if pr is not None:
                    route_price_by_id[rpid] = pr

        if not rows and not price_map and not route_default_price and not route_price_by_id:
            pass

        plan_map = {}
        try:
            connp = self.db.connect()
            curp = connp.cursor()
            curp.execute(
                """
                SELECT route_params_id, time_block, vehicle_id, driver_id
                FROM trip_plan
                WHERE contract_id = ? AND month = ? AND service_type = ?
                """,
                (int(self.contract_id), str(self.month_key), str(self.service_type)),
            )
            for rid, tb, vid, did in curp.fetchall() or []:
                plan_map[(int(rid or 0), str(tb or ""))] = (str(vid) if vid is not None else "", str(did) if did is not None else "")
            connp.close()
        except Exception:
            try:
                connp.close()
            except Exception:
                pass
            plan_map = {}

        try:
            self.table.blockSignals(True)

            for key, row_idx in row_index.items():
                pv, pd = plan_map.get(key, ("", ""))
                cmb_v = self.table.cellWidget(row_idx, self._col_vehicle)
                cmb_d = self.table.cellWidget(row_idx, self._col_driver)
                if cmb_v is not None and pv:
                    idx = cmb_v.findData(str(pv))
                    if idx >= 0:
                        cmb_v.setCurrentIndex(idx)
                if cmb_d is not None and pd:
                    idx = cmb_d.findData(str(pd))
                    if idx >= 0:
                        cmb_d.setCurrentIndex(idx)

            self._alloc_override_map = {}
            for rpid, trip_date, time_block, vehicle_id, driver_id, _qty0, _ttext0, note0 in alloc_rows or []:
                rid_i = int(rpid or 0)
                tb_s = str(time_block or "").strip()
                d_s = str(trip_date or "").strip()
                if rid_i <= 0 or not tb_s or not d_s:
                    continue
                pv, pd = plan_map.get((rid_i, tb_s), ("", ""))
                is_override = False
                if vehicle_id is not None and str(vehicle_id).strip() and str(vehicle_id) != str(pv):
                    is_override = True
                if driver_id is not None and str(driver_id).strip() and str(driver_id) != str(pd):
                    is_override = True
                if (note0 or "").strip():
                    is_override = True

                self._alloc_override_map[(rid_i, tb_s, d_s)] = {
                    "vehicle_id": vehicle_id,
                    "driver_id": driver_id,
                    "note": (note0 or "").strip(),
                    "is_override": bool(is_override),
                }

                key = (rid_i, tb_s)
                r = row_index.get(key)
                if r is None:
                    continue

                try:
                    day = int(str(d_s)[-2:])
                except Exception:
                    day = 0
                if day < 1 or day > self.days_in_month:
                    continue
                col = self._day_start + (day - 1)

                self._apply_day_cell_style(r, col)

            for key, row_idx in row_index.items():
                pr = price_map.get(key)
                if pr is None:
                    rp = route_default_price.get(int(key[0] or 0))
                    if rp is not None:
                        pr = rp
                    else:
                        pr = route_price_by_id.get(int(key[0] or 0))

                if pr is None:
                    continue

                p_item = self.table.item(row_idx, self._col_price)
                if p_item is not None:
                    p_item.setText(str(int(pr)) if float(pr).is_integer() else str(pr))

            for route_params_id, trip_date, time_block, qty, time_text in rows:
                key = (int(route_params_id or 0), str(time_block or ""))
                r = row_index.get(key)
                if r is None:
                    continue

                day = 0
                try:
                    day = int(str(trip_date)[-2:])
                except Exception:
                    day = 0
                if day < 1 or day > self.days_in_month:
                    continue

                col = self._day_start + (day - 1)
                it = self.table.item(r, col)
                if it is None:
                    continue
                try:
                    q = int(qty or 0)
                except Exception:
                    q = 0
                it.setText(str(q) if q != 0 else "")
                self._apply_day_cell_style(r, col)

                if (time_text or "").strip():
                    t_item = self.table.item(r, self._col_time_text)
                    if t_item is not None:
                        if not (t_item.text() or "").strip() or (t_item.text() or "").strip() in ("GİRİŞ", "ÇIKIŞ"):
                            t_item.setText((time_text or "").strip())

            for r in range(self.table.rowCount()):
                total = 0
                for day_col in range(self._day_start, self._day_start + self.days_in_month):
                    it = self.table.item(r, day_col)
                    if it and (it.text() or "").strip().isdigit():
                        total += int(it.text().strip())
                t_item = self.table.item(r, self._col_total_qty)
                if t_item is not None:
                    t_item.setText(str(total))
                self._recalc_price_total_for_row(r)
                for day_col in range(self._day_start, self._day_start + self.days_in_month):
                    self._apply_day_cell_style(r, day_col)
        finally:
            try:
                self.table.blockSignals(False)
            except Exception:
                pass

    def _save(self):
        soru = QMessageBox.question(
            self,
            "Onay",
            "Puantaj kaydedilsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if soru != QMessageBox.StandardButton.Yes:
            return

        self._saving = True
        try:
            self.btn_save.setEnabled(False)
        except Exception:
            pass
        try:
            self.table.setEnabled(False)
        except Exception:
            pass

        start_date = QDate(self.year, self.month, 1).toString("yyyy-MM-dd")
        end_date = QDate(self.year, self.month, self.days_in_month).toString("yyyy-MM-dd")

        existing_entries = set()
        existing_prices = set()
        existing_allocations = set()
        try:
            conn0 = self.db.connect()
            cur0 = conn0.cursor()
            cur0.execute(
                """
                SELECT route_params_id, trip_date, time_block
                FROM trip_entries
                WHERE contract_id=? AND service_type=? AND trip_date BETWEEN ? AND ?
                """,
                (int(self.contract_id), str(self.service_type), start_date, end_date),
            )
            for rid0, d0, tb0 in cur0.fetchall() or []:
                existing_entries.add((int(rid0 or 0), str(d0 or ""), str(tb0 or "")))

            cur0.execute(
                """
                SELECT route_params_id, time_block
                FROM trip_prices
                WHERE contract_id=? AND month=? AND service_type=?
                """,
                (int(self.contract_id), str(self.month_key), str(self.service_type)),
            )
            for rid0, tb0 in cur0.fetchall() or []:
                existing_prices.add((int(rid0 or 0), str(tb0 or "")))

            cur0.execute(
                """
                SELECT route_params_id, trip_date, time_block
                FROM trip_allocations
                WHERE contract_id=? AND service_type=? AND trip_date BETWEEN ? AND ?
                """,
                (int(self.contract_id), str(self.service_type), start_date, end_date),
            )
            for rid0, d0, tb0 in cur0.fetchall() or []:
                existing_allocations.add((int(rid0 or 0), str(d0 or ""), str(tb0 or "")))
            conn0.close()
        except Exception:
            existing_entries = set()
            existing_prices = set()
            existing_allocations = set()

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        price_rows = []
        entry_rows = []
        alloc_rows = []

        for r in range(self.table.rowCount()):
            rid = None
            it_route = self.table.item(r, 1)
            if it_route is not None:
                rid = it_route.data(Qt.ItemDataRole.UserRole)
            if not rid:
                continue

            meta = self._row_meta[r] if r < len(self._row_meta) else None
            time_block = str((meta or {}).get("time_block") or "GUN")
            is_planned = (int(rid), str(time_block)) in (self._planned_keys or set())

            time_text = ""
            it_time = self.table.item(r, self._col_time_text)
            if it_time is not None:
                time_text = (it_time.text() or "").strip()

            cmb_v = self.table.cellWidget(r, self._col_vehicle)
            cmb_d = self.table.cellWidget(r, self._col_driver)
            vehicle_id = cmb_v.currentData() if cmb_v is not None else None
            driver_id = cmb_d.currentData() if cmb_d is not None else None

            p_item = self.table.item(r, self._col_price)
            p_txt = ((p_item.text() if p_item else "") or "").strip()
            try:
                price = float(p_txt.replace(",", ".") or 0)
            except Exception:
                price = 0.0

            if price != 0.0 or (int(rid), time_block) in existing_prices:
                price_rows.append(
                    (
                        int(self.contract_id),
                        int(rid),
                        str(self.month_key),
                        str(self.service_type),
                        str(time_block),
                        float(price),
                        now,
                    )
                )

            for day in range(1, self.days_in_month + 1):
                col = self._day_start + (day - 1)
                it = self.table.item(r, col)
                val = (it.text() or "").strip() if it else ""
                qty = int(val) if val.isdigit() else 0
                trip_date = QDate(self.year, self.month, day).toString("yyyy-MM-dd")
                key = (int(rid), str(trip_date), str(time_block))
                if is_planned or qty != 0 or key in existing_entries:
                    entry_rows.append(
                        (
                            int(self.contract_id),
                            int(rid),
                            str(trip_date),
                            str(self.service_type),
                            str(time_block),
                            int(qty),
                            str(time_text),
                            now,
                            now,
                        )
                    )

                key2 = (int(rid), str(trip_date), str(time_block))
                if is_planned or qty != 0 or key2 in existing_allocations:
                    override = self._alloc_override_map.get((int(rid), str(time_block), str(trip_date))) or {}
                    v2 = override.get("vehicle_id", vehicle_id)
                    d2 = override.get("driver_id", driver_id)
                    note2 = (override.get("note") or "").strip()
                    alloc_rows.append(
                        (
                            int(self.contract_id),
                            int(rid),
                            str(trip_date),
                            str(self.service_type),
                            str(time_block),
                            d2,
                            v2,
                            float(qty),
                            str(time_text),
                            note2,
                            now,
                            now,
                        )
                    )

        try:
            conn = self.db.connect()
            cur = conn.cursor()
            cur.execute("BEGIN")

            if price_rows:
                cur.executemany(
                    """
                    INSERT INTO trip_prices (
                        contract_id, route_params_id, month, service_type, time_block, price, updated_at
                    ) VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(contract_id, route_params_id, month, service_type, time_block)
                    DO UPDATE SET price=excluded.price, updated_at=excluded.updated_at
                    """,
                    price_rows,
                )

            if entry_rows:
                cur.executemany(
                    """
                    INSERT INTO trip_entries (
                        contract_id, route_params_id, trip_date, service_type, time_block,
                        qty, time_text, created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(contract_id, route_params_id, trip_date, service_type, time_block)
                    DO UPDATE SET qty=excluded.qty, time_text=excluded.time_text, updated_at=excluded.updated_at
                    """,
                    entry_rows,
                )

            if alloc_rows:
                cur.executemany(
                    """
                    INSERT INTO trip_allocations (
                        contract_id, route_params_id, trip_date, service_type, time_block,
                        driver_id, vehicle_id, qty, time_text, note, created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(contract_id, route_params_id, trip_date, service_type, time_block)
                    DO UPDATE SET
                        driver_id=excluded.driver_id,
                        vehicle_id=excluded.vehicle_id,
                        qty=excluded.qty,
                        time_text=excluded.time_text,
                        note=excluded.note,
                        updated_at=excluded.updated_at
                    """,
                    alloc_rows,
                )

            conn.commit()
            conn.close()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            QMessageBox.critical(self, "Hata", "Bazı kayıtlar yazılamadı.")
            return
        finally:
            self._saving = False

        self.accept()

    def closeEvent(self, event):
        if bool(getattr(self, "_saving", False)):
            try:
                event.ignore()
            except Exception:
                pass
            return
        try:
            super().closeEvent(event)
        except Exception:
            try:
                event.accept()
            except Exception:
                pass

