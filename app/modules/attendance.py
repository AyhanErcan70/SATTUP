
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
    QApplication,
    QDialog,
    QGridLayout,
    QHeaderView,
    QInputDialog,
    QComboBox,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QLabel,
    QLineEdit,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from app.core.db_manager import DatabaseManager
from app.utils.excel_utils import create_excel
from app.utils.style_utils import clear_all_styles
from config import get_ui_path


@dataclass(frozen=True)
class AttendanceContext:
    contract_id: int
    month: str
    service_type: str


class AttendanceApp(QWidget):
    def __init__(self, parent=None, user_data=None, db: DatabaseManager | None = None):
        super().__init__(parent)
        uic.loadUi(get_ui_path("attendance_window.ui"), self)
        clear_all_styles(self)

        self.user_data = user_data or {}
        self.db = db if db else DatabaseManager()

        self._suppress_tab_change = True

        self._selected_customer_id = None
        self._selected_contract_id = None
        self._active_month = ""
        self._embedded_bulk = None
        self._embedded_bulk_ctx = None

        self._init_filters()
        self._apply_active_month_defaults()
        self._setup_connections()
        self._refresh_lock_ui()
        self._suppress_tab_change = False

    def _apply_active_month_defaults(self):
        ym = str((self.user_data or {}).get("active_month") or "").strip()
        if not ym or "-" not in ym:
            try:
                ym = QDate.currentDate().toString("yyyy-MM")
            except Exception:
                ym = ""
        if not ym or "-" not in ym:
            return
        try:
            y_str, m_str = ym.split("-", 1)
            y = int(y_str)
            m = int(m_str)
        except Exception:
            return

        ay_map = {
            1: "OCAK",
            2: "ŞUBAT",
            3: "MART",
            4: "NİSAN",
            5: "MAYIS",
            6: "HAZİRAN",
            7: "TEMMUZ",
            8: "AĞUSTOS",
            9: "EYLÜL",
            10: "EKİM",
            11: "KASIM",
            12: "ARALIK",
        }
        ay_txt = ay_map.get(m)
        if not ay_txt:
            return

        self._active_month = f"{int(y):04d}-{int(m):02d}"

        if hasattr(self, "lbl_year"):
            try:
                self.lbl_year.setText(str(int(y)))
            except Exception:
                pass
        if hasattr(self, "lbl_month"):
            try:
                self.lbl_month.setText(str(ay_txt))
            except Exception:
                pass

    # ------------------------- UI wiring -------------------------
    def _setup_connections(self):
        if hasattr(self, "btn_onayla_kilitle"):
            self.btn_onayla_kilitle.clicked.connect(self._lock_period)

        if hasattr(self, "btn_onay_kaldir"):
            self.btn_onay_kaldir.clicked.connect(self._unlock_period)

        if hasattr(self, "btn_excele_aktar"):
            try:
                self.btn_excele_aktar.clicked.connect(self._export_excel)
            except Exception:
                pass

        if hasattr(self, "btn_yazdir"):
            try:
                self.btn_yazdir.clicked.connect(self._export_excel)
            except Exception:
                pass

        if hasattr(self, "sekmeli_form"):
            try:
                self.sekmeli_form.currentChanged.connect(self._on_tab_changed)
            except Exception:
                pass

        if hasattr(self, "tbl_toplu_puantaj"):
            try:
                self.tbl_toplu_puantaj.cellDoubleClicked.connect(lambda r, c: self._open_bulk_attendance())
            except Exception:
                pass

        if hasattr(self, "cmb_musteri"):
            self.cmb_musteri.currentIndexChanged.connect(self._on_customer_changed)
        if hasattr(self, "cmb_sozlesme"):
            self.cmb_sozlesme.currentIndexChanged.connect(self._on_contract_changed)
        if hasattr(self, "cmb_hizmet_turu"):
            self.cmb_hizmet_turu.currentIndexChanged.connect(self._on_service_type_changed)

        if hasattr(self, "btn_geri_don"):
            self.btn_geri_don.clicked.connect(self._return_to_main)

        self._reload_summary()

    def _apply_compact_table_combo(self, cmb: QComboBox, bg_color: str | None = None):
        try:
            if cmb is None:
                return
            try:
                cmb.setFixedHeight(22)
            except Exception:
                pass

            try:
                f = cmb.font()
                f.setPointSize(7)
                cmb.setFont(f)
                try:
                    v = cmb.view()
                    if v is not None:
                        v.setFont(f)
                except Exception:
                    pass
            except Exception:
                pass

            bg = f"background-color: {bg_color};" if bg_color else ""
            cmb.setStyleSheet(
                "QComboBox {"
                + bg
                + " padding: 1px 4px; min-height: 18px; border-radius: 4px; font-size: 7pt; }"
                + "QComboBox::drop-down { width: 14px; border: none; }"
            )
        except Exception:
            return

    def _render_toplu_puantaj_tab(self):
        if not hasattr(self, "tbl_toplu_puantaj"):
            return

        ctx = self._current_context()
        tbl = self.tbl_toplu_puantaj

        try:
            tbl.setAlternatingRowColors(True)
            tbl.verticalHeader().setVisible(False)
            tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        except Exception:
            pass

        headers = ["Rota", "Zaman", "Bilgi"]
        try:
            tbl.setColumnCount(len(headers))
            tbl.setHorizontalHeaderLabels(headers)
        except Exception:
            return

        if ctx is None:
            tbl.setRowCount(0)
            return

        st_values = self._service_type_values(ctx.service_type) or [str(ctx.service_type)]
        placeholders = ",".join(["?"] * len(st_values))

        rows = []
        try:
            conn = self.db.connect()
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT p.route_params_id,
                       p.time_block,
                       COALESCE(r.route_name,'')
                FROM trip_plan p
                LEFT JOIN route_params r ON r.id = p.route_params_id
                WHERE p.contract_id = ?
                  AND p.month = ?
                  AND p.service_type IN ({placeholders})
                GROUP BY p.route_params_id, p.time_block
                ORDER BY COALESCE(r.route_name,''), p.time_block
                """,
                (int(ctx.contract_id), str(ctx.month), *st_values),
            )
            rows = cur.fetchall() or []
            conn.close()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            rows = []

        tbl.setRowCount(0)
        for rid, tb, rn in rows:
            r = tbl.rowCount()
            tbl.insertRow(r)

            it_route = QTableWidgetItem(str(rn or ""))
            it_route.setData(Qt.ItemDataRole.UserRole, int(rid or 0))
            tbl.setItem(r, 0, it_route)

            it_tb = QTableWidgetItem(str(tb or ""))
            it_tb.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            tbl.setItem(r, 1, it_tb)

            it_info = QTableWidgetItem("Çift tıkla toplu puantaj")
            tbl.setItem(r, 2, it_info)

        try:
            tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        except Exception:
            pass

    def _on_tab_changed(self, index: int):
        if bool(getattr(self, "_suppress_tab_change", False)):
            return
        try:
            w = self.sekmeli_form.widget(int(index)) if hasattr(self, "sekmeli_form") else None
            name = w.objectName() if w is not None else ""
        except Exception:
            name = ""

        if name == "tab_plan":
            self._render_plan_tracking_tab()
        elif name == "tab_toplu":
            self._open_bulk_attendance(in_tab=True)
        else:
            self._reload_summary()

    # ------------------------- Context helpers -------------------------
    def _is_admin(self) -> bool:
        return (self.user_data or {}).get("role") == "admin"

    def _selected_month_key(self) -> str:
        if str(getattr(self, "_active_month", "") or "").strip():
            return str(self._active_month).strip()
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

    def _render_plan_tracking_tab(self):
        if not hasattr(self, "tbl_plan_takip"):
            return

        ctx = self._current_context()
        if ctx is None:
            try:
                self.tbl_plan_takip.setRowCount(0)
                self.tbl_plan_takip.setColumnCount(0)
            except Exception:
                pass
            return

        y, m = self._selected_year_month()
        days_in_month = QDate(y, m, 1).daysInMonth()
        start_date = QDate(y, m, 1).toString("yyyy-MM-dd")
        end_date = QDate(y, m, days_in_month).toString("yyyy-MM-dd")

        st_values = self._service_type_values(ctx.service_type) or [str(ctx.service_type)]

        planned_keys: set[tuple[int, str]] = set()
        try:
            conn = self.db.connect()
            cur = conn.cursor()
            placeholders = ",".join(["?"] * len(st_values))
            cur.execute(
                f"""
                SELECT route_params_id, time_block
                FROM trip_plan
                WHERE contract_id = ?
                  AND month = ?
                  AND service_type IN ({placeholders})
                """,
                (int(ctx.contract_id), str(ctx.month), *st_values),
            )
            rows = cur.fetchall() or []
            conn.close()
            planned_keys = {
                (int(r[0] or 0), str(r[1] or ""))
                for r in rows
                if int(r[0] or 0) and str(r[1] or "")
            }
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            planned_keys = set()

        planned_per_day = float(len(planned_keys))
        actual_per_day = {d: 0.0 for d in range(1, days_in_month + 1)}

        try:
            conn2 = self.db.connect()
            cur2 = conn2.cursor()
            placeholders = ",".join(["?"] * len(st_values))
            if planned_keys:
                cur2.execute(
                    f"""
                    SELECT trip_date, route_params_id, time_block, COALESCE(SUM(qty),0)
                    FROM trip_entries
                    WHERE contract_id = ?
                      AND service_type IN ({placeholders})
                      AND trip_date BETWEEN ? AND ?
                    GROUP BY trip_date, route_params_id, time_block
                    """,
                    (int(ctx.contract_id), *st_values, start_date, end_date),
                )
                for trip_date, rid, tb, qty_sum in (cur2.fetchall() or []):
                    try:
                        rid_i = int(rid or 0)
                        tb_s = str(tb or "")
                        if (rid_i, tb_s) not in planned_keys:
                            continue
                        qd = QDate.fromString(str(trip_date or ""), "yyyy-MM-dd")
                        if not qd.isValid():
                            continue
                        day = int(qd.day())
                        actual_per_day[day] = float(actual_per_day.get(day, 0) or 0) + float(qty_sum or 0)
                    except Exception:
                        continue
            else:
                cur2.execute(
                    f"""
                    SELECT trip_date, COALESCE(SUM(qty),0)
                    FROM trip_entries
                    WHERE contract_id = ?
                      AND service_type IN ({placeholders})
                      AND trip_date BETWEEN ? AND ?
                    GROUP BY trip_date
                    """,
                    (int(ctx.contract_id), *st_values, start_date, end_date),
                )
                for trip_date, qty_sum in (cur2.fetchall() or []):
                    try:
                        qd = QDate.fromString(str(trip_date or ""), "yyyy-MM-dd")
                        if not qd.isValid():
                            continue
                        day = int(qd.day())
                        actual_per_day[day] = float(actual_per_day.get(day, 0) or 0) + float(qty_sum or 0)
                    except Exception:
                        continue
            conn2.close()
        except Exception:
            try:
                conn2.close()
            except Exception:
                pass

        tbl = self.tbl_plan_takip
        try:
            tbl.setAlternatingRowColors(True)
            tbl.verticalHeader().setVisible(False)
            tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        except Exception:
            pass

        headers = ["Kalem"] + [str(d) for d in range(1, days_in_month + 1)]
        tbl.setColumnCount(len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.setRowCount(3)

        row_names = ["Planlanan", "Gerçekleşen", "Eksik"]
        for r, nm in enumerate(row_names):
            it = QTableWidgetItem(str(nm))
            it.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            tbl.setItem(r, 0, it)

        for day in range(1, days_in_month + 1):
            actual = float(actual_per_day.get(day, 0) or 0)
            planned = float(planned_per_day)
            missing = planned - actual
            if missing < 0:
                missing = 0.0

            for r, val in enumerate([planned, actual, missing]):
                itv = QTableWidgetItem(str(int(val) if float(val).is_integer() else val))
                itv.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if r == 2 and missing > 0:
                    itv.setBackground(QColor("#f8d7da"))
                tbl.setItem(r, day, itv)

        try:
            tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            for c in range(1, tbl.columnCount()):
                tbl.setColumnWidth(c, 32)
        except Exception:
            pass

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
            if hasattr(self, "btn_excele_aktar"):
                self.btn_excele_aktar.setEnabled(False)
            if hasattr(self, "btn_yazdir"):
                self.btn_yazdir.setEnabled(False)
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

        if hasattr(self, "btn_excele_aktar"):
            self.btn_excele_aktar.setEnabled(True)
        if hasattr(self, "btn_yazdir"):
            self.btn_yazdir.setEnabled(True)

    def _export_excel(self):
        ctx = self._current_context()
        if ctx is None:
            QMessageBox.warning(self, "Uyarı", "Müşteri / Sözleşme / Hizmet seçiniz.")
            return

        tab_name = "Puantaj"
        tbl = None
        try:
            if hasattr(self, "sekmeli_form") and self.sekmeli_form is not None:
                idx = int(self.sekmeli_form.currentIndex())
            else:
                idx = 0
        except Exception:
            idx = 0

        if idx == 0 and hasattr(self, "tbl_plan_takip"):
            tbl = self.tbl_plan_takip
            tab_name = "Plan Takip"
        elif idx == 1 and hasattr(self, "tbl_toplu_puantaj"):
            tbl = self.tbl_toplu_puantaj
            tab_name = "Toplu Puantaj"

        if tbl is None:
            QMessageBox.warning(self, "Uyarı", "Excel'e aktarılacak tablo bulunamadı.")
            return

        try:
            if int(tbl.rowCount()) <= 0:
                QMessageBox.information(self, "Bilgi", "Excel'e aktarılacak satır yok.")
                return
        except Exception:
            pass

        try:
            user_txt = str((self.user_data or {}).get("full_name") or (self.user_data or {}).get("username") or "")
        except Exception:
            user_txt = ""

        report_title = f"{tab_name} - {ctx.month}"
        create_excel(tbl, report_title=report_title, username=user_txt or "", parent=self)

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

    def _open_bulk_attendance(self, in_tab: bool = False):
        if self._is_period_locked():
            QMessageBox.information(self, "Bilgi", "Bu dönem kilitli. Toplu puantaj girişi yapılamaz.")
            return
        ctx = self._current_context()
        if ctx is None:
            QMessageBox.warning(self, "Uyarı", "Müşteri / Sözleşme / Hizmet seçiniz.")
            return

        ctx_key = (int(ctx.contract_id), str(ctx.month), str(ctx.service_type))

        st_values = self._service_type_values(ctx.service_type) or [str(ctx.service_type)]
        has_plan = self.db.has_trip_plan_for_context(int(ctx.contract_id), str(ctx.month), [str(x) for x in st_values])
        if not has_plan:
            QMessageBox.warning(
                self,
                "Uyarı",
                "Bu dönem için sefer planı bulunamadı.\n\nÖnce sefer planlamasını yapın veya girişte şablon kopyalama ile dönemi oluşturun.",
            )
            return

        if in_tab:
            try:
                host = self.tab_toplu if hasattr(self, "tab_toplu") else None
            except Exception:
                host = None
            if host is None:
                QMessageBox.warning(self, "Uyarı", "Toplu puantaj sekmesi bulunamadı.")
                return

            if self._embedded_bulk is not None and self._embedded_bulk_ctx == ctx_key:
                try:
                    self._embedded_bulk.setVisible(True)
                except Exception:
                    pass
                self._reload_summary()
                self._refresh_lock_ui()
                return

            cursor_set = False
            try:
                try:
                    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                    cursor_set = True
                except Exception:
                    cursor_set = False

                try:
                    if hasattr(self, "tbl_toplu_puantaj"):
                        self.tbl_toplu_puantaj.setVisible(False)
                except Exception:
                    pass

                try:
                    if self._embedded_bulk is not None:
                        self._embedded_bulk.setParent(None)
                        self._embedded_bulk.deleteLater()
                except Exception:
                    pass

                self._embedded_bulk = BulkAttendanceDialog(
                    parent=host,
                    db=self.db,
                    contract_id=int(ctx.contract_id),
                    service_type=str(ctx.service_type),
                    year_month=self._selected_year_month(),
                    embedded=True,
                )
                self._embedded_bulk_ctx = ctx_key

                try:
                    lay = host.layout()
                    if lay is not None:
                        lay.addWidget(self._embedded_bulk)
                except Exception:
                    pass

                self._reload_summary()
                self._refresh_lock_ui()
                return
            finally:
                if cursor_set:
                    try:
                        QApplication.restoreOverrideCursor()
                    except Exception:
                        pass

        dlg = BulkAttendanceDialog(
            parent=self,
            db=self.db,
            contract_id=int(ctx.contract_id),
            service_type=str(ctx.service_type),
            year_month=self._selected_year_month(),
            embedded=False,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._reload_summary()
            self._refresh_lock_ui()

    def _open_plan_tracking(self):
        ctx = self._current_context()
        if ctx is None:
            QMessageBox.warning(self, "Uyarı", "Müşteri / Sözleşme / Hizmet seçiniz.")
            return
        dlg = PlanTrackingDialog(
            parent=self,
            db=self.db,
            ctx=ctx,
            year_month=self._selected_year_month(),
            service_type_values=(self._service_type_values(ctx.service_type) or [str(ctx.service_type)]),
        )
        dlg.exec()



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
        try:
            if hasattr(self, "sekmeli_form") and hasattr(self, "tab_plan"):
                self.sekmeli_form.setCurrentWidget(self.tab_plan)
        except Exception:
            pass


class BulkAttendanceDialog(QDialog):
    def _apply_compact_table_combo(self, cmb: QComboBox, bg_color: str | None = None):
        try:
            if cmb is None:
                return
            try:
                cmb.setFixedHeight(22)
            except Exception:
                pass

            try:
                f = cmb.font()
                f.setPointSize(7)
                cmb.setFont(f)
                try:
                    v = cmb.view()
                    if v is not None:
                        v.setFont(f)
                except Exception:
                    pass
            except Exception:
                pass

            bg = f"background-color: {bg_color};" if bg_color else ""
            cmb.setStyleSheet(
                "QComboBox {"
                + bg
                + " padding: 1px 4px; min-height: 18px; border-radius: 4px; font-size: 7pt; }"
                + "QComboBox::drop-down { width: 14px; border: none; }"
            )
        except Exception:
            return

    def _parse_tr_float(self, txt: str) -> float:
        s = str(txt or "").strip()
        if not s:
            return 0.0
        s = s.replace(".", "")
        s = s.replace(",", ".")
        try:
            return float(s)
        except Exception:
            return 0.0

    def _format_tr_currency(self, val) -> str:
        try:
            x = float(val or 0)
        except Exception:
            x = 0.0
        try:
            s = f"{x:,.2f}"
            return s.replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return "0,00"

    def _apply_route_group_spans(self):
        def _route_info(rid: int) -> tuple[str, str]:
            try:
                for rr in self._route_rows:
                    if int(rr[0] or 0) == int(rid):
                        nm = str(rr[1] or "") if len(rr) > 1 else ""
                        st = str(rr[2] or "") if len(rr) > 2 else ""
                        return nm, st
            except Exception:
                pass
            return "", ""

        def _route_display(route_txt: str, stops_txt: str) -> str:
            rt = str(route_txt or "").strip()
            st = str(stops_txt or "").strip()
            if rt and st:
                return f"{rt}\n{st}"
            return rt or st

        try:
            self.table.clearSpans()
        except Exception:
            pass

        group_no = 0
        r = 0
        while r < self.table.rowCount():
            meta0 = self._row_meta[r] if r < len(self._row_meta) else None
            try:
                rid0 = int((meta0 or {}).get("route_params_id") or 0)
            except Exception:
                rid0 = 0

            route_txt, stops_txt = _route_info(rid0)

            span_len = 1
            rr = r + 1
            while rr < self.table.rowCount():
                meta2 = self._row_meta[rr] if rr < len(self._row_meta) else None
                try:
                    rid2 = int((meta2 or {}).get("route_params_id") or 0)
                except Exception:
                    rid2 = 0
                if rid2 != rid0:
                    break
                span_len += 1
                rr += 1

            group_no += 1
            try:
                it_sno = self.table.item(r, 0)
                if it_sno is None:
                    it_sno = QTableWidgetItem("")
                    self.table.setItem(r, 0, it_sno)
                it_sno.setText(str(group_no))
                it_sno.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                it_sno.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            except Exception:
                pass

            try:
                it_route0 = self.table.item(r, 1)
                if it_route0 is None:
                    it_route0 = QTableWidgetItem("")
                    self.table.setItem(r, 1, it_route0)
                it_route0.setText(_route_display(route_txt, stops_txt))
                it_route0.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                it_route0.setData(Qt.ItemDataRole.UserRole, int(rid0) if int(rid0 or 0) > 0 else None)
            except Exception:
                pass
            try:
                it_stops0 = self.table.item(r, self._col_stops)
                if it_stops0 is None:
                    it_stops0 = QTableWidgetItem("")
                    self.table.setItem(r, self._col_stops, it_stops0)
                it_stops0.setText(stops_txt)
                it_stops0.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            except Exception:
                pass

            if span_len > 1:
                try:
                    self.table.setSpan(r, 0, span_len, 1)
                    self.table.setSpan(r, 1, span_len, 1)
                    self.table.setSpan(r, self._col_stops, span_len, 1)
                except Exception:
                    pass

                for rdel in range(r + 1, r + span_len):
                    try:
                        self.table.takeItem(rdel, 0)
                        self.table.takeItem(rdel, 1)
                        self.table.takeItem(rdel, self._col_stops)
                    except Exception:
                        pass

            r += span_len

    def _movement_type_for_route(self, route_params_id: int) -> str:
        try:
            for rr in self._route_rows:
                if int(rr[0] or 0) == int(route_params_id):
                    if len(rr) > 4:
                        return str(rr[4] or "").strip()
                    if len(rr) > 3 and isinstance(rr[3], str):
                        return str(rr[3] or "").strip()
                    return ""
        except Exception:
            return ""
        return ""

    def _looks_like_double_time_text(self, txt: str) -> bool:
        t = str(txt or "").strip()
        if "-" not in t:
            return False
        left, right = (t.split("-", 1) + [""])[:2]
        left = left.strip()
        right = right.strip()
        if not left or not right:
            return False
        try:
            return (re.match(r"^\d{2}:\d{2}$", left) is not None) and (re.match(r"^\d{2}:\d{2}$", right) is not None)
        except Exception:
            return False

    def _split_row(self, row: int):
        if row < 0 or row >= self.table.rowCount():
            return

        meta = self._row_meta[row] if row < len(self._row_meta) else None
        try:
            rid = int((meta or {}).get("route_params_id") or 0)
        except Exception:
            rid = 0
        if rid <= 0:
            return

        mt = (self._movement_type_for_route(rid) or "").lower()
        is_cift = ("çift" in mt) or ("cift" in mt)
        if not is_cift:
            t_it = self.table.item(row, self._col_time_text)
            t_txt = (t_it.text() if t_it is not None else "")
            if self._looks_like_double_time_text(t_txt):
                is_cift = True

        if not is_cift:
            QMessageBox.information(self, "Bilgi", "Bu satır ÇİFT servis değil. Ayırma işlemi ÇİFT satırlar için tasarlandı.")
            return

        try:
            self.table.blockSignals(True)

            insert_at = row + 1
            self.table.insertRow(insert_at)

            for c in range(self.table.columnCount()):
                if c in (self._col_vehicle, self._col_driver):
                    w = self.table.cellWidget(row, c)
                    if w is None:
                        continue
                    if isinstance(w, QComboBox):
                        nw = QComboBox()
                        for i in range(w.count()):
                            nw.addItem(w.itemText(i), w.itemData(i))
                        nw.setCurrentIndex(w.currentIndex())
                        self._apply_compact_table_combo(nw)
                        self.table.setCellWidget(insert_at, c, nw)
                    continue

                it = self.table.item(row, c)
                if it is None:
                    continue
                nit = QTableWidgetItem(it.text())
                nit.setTextAlignment(it.textAlignment())
                nit.setFlags(it.flags())
                try:
                    nit.setBackground(it.background())
                except Exception:
                    pass
                self.table.setItem(insert_at, c, nit)

            if row < len(self._row_meta):
                self._row_meta.insert(insert_at, dict(self._row_meta[row] or {}))

            for rr in (row, insert_at):
                try:
                    t_it = self.table.item(rr, self._col_time_text)
                    if t_it is None:
                        t_it = QTableWidgetItem("")
                        self.table.setItem(rr, self._col_time_text, t_it)
                    t_it.setText("")
                    t_it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
                except Exception:
                    pass

            p_it = self.table.item(row, self._col_price)
            if p_it is not None:
                p = self._parse_tr_float(p_it.text() or "0")
                half = p / 2.0
                p_it.setText(self._format_tr_currency(half))
                p2 = self.table.item(insert_at, self._col_price)
                if p2 is not None:
                    p2.setText(self._format_tr_currency(half))

            try:
                if p_it is not None:
                    self._recalc_price_total_for_row(row)
                    self._recalc_price_total_for_row(insert_at)
            except Exception:
                pass

        finally:
            try:
                self.table.blockSignals(False)
            except Exception:
                pass

        self._apply_route_group_spans()

    def _merge_row(self, row: int):
        if row < 0 or row >= self.table.rowCount():
            return

        def _meta_at(r: int):
            return self._row_meta[r] if r >= 0 and r < len(self._row_meta) else None

        m0 = _meta_at(row) or {}
        try:
            rid0 = int(m0.get("route_params_id") or 0)
        except Exception:
            rid0 = 0
        tb0 = str(m0.get("time_block") or "").strip()
        if not rid0 or not tb0:
            return

        partner = None
        for cand in (row + 1, row - 1):
            if cand < 0 or cand >= self.table.rowCount():
                continue
            m1 = _meta_at(cand) or {}
            try:
                rid1 = int(m1.get("route_params_id") or 0)
            except Exception:
                rid1 = 0
            tb1 = str(m1.get("time_block") or "").strip()
            if rid1 == rid0 and tb1 == tb0:
                partner = cand
                break

        if partner is None:
            QMessageBox.information(self, "Bilgi", "Birleştirilecek eş satır bulunamadı.")
            return

        keep_row = min(row, partner)
        drop_row = max(row, partner)

        try:
            self.table.blockSignals(True)

            # Sum day values
            for d in range(1, self.days_in_month + 1):
                col = self._day_start + (d - 1)
                it_keep = self.table.item(keep_row, col)
                it_drop = self.table.item(drop_row, col)

                v0 = 0
                v1 = 0
                try:
                    t0 = (it_keep.text() if it_keep is not None else "").strip()
                    v0 = int(t0) if t0.isdigit() else 0
                except Exception:
                    v0 = 0
                try:
                    t1 = (it_drop.text() if it_drop is not None else "").strip()
                    v1 = int(t1) if t1.isdigit() else 0
                except Exception:
                    v1 = 0

                total = int(v0) + int(v1)
                if it_keep is None:
                    it_keep = QTableWidgetItem("")
                    it_keep.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    it_keep.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    self.table.setItem(keep_row, col, it_keep)
                it_keep.setText(str(total) if total > 0 else "")

            # Merge time text (keep first non-empty)
            try:
                it_t0 = self.table.item(keep_row, self._col_time_text)
                it_t1 = self.table.item(drop_row, self._col_time_text)
                t0 = (it_t0.text() if it_t0 is not None else "").strip()
                t1 = (it_t1.text() if it_t1 is not None else "").strip()
                if (not t0) and t1:
                    if it_t0 is None:
                        it_t0 = QTableWidgetItem("")
                        it_t0.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
                        self.table.setItem(keep_row, self._col_time_text, it_t0)
                    it_t0.setText(t1)
            except Exception:
                pass

            # Price: sum
            p0 = 0.0
            p1 = 0.0
            p_it0 = self.table.item(keep_row, self._col_price)
            p_it1 = self.table.item(drop_row, self._col_price)
            if p_it0 is not None:
                p0 = self._parse_tr_float(p_it0.text() or "0")
            if p_it1 is not None:
                p1 = self._parse_tr_float(p_it1.text() or "0")
            if p_it0 is None:
                p_it0 = QTableWidgetItem("0")
                p_it0.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(keep_row, self._col_price, p_it0)
            p_it0.setText(self._format_tr_currency(float(p0) + float(p1)))

            # Remove drop row
            self.table.removeRow(drop_row)
            if drop_row < len(self._row_meta):
                try:
                    self._row_meta.pop(drop_row)
                except Exception:
                    pass

            # Recalc totals/styles
            total_qty = 0
            for day_col in range(self._day_start, self._day_start + self.days_in_month):
                itx = self.table.item(keep_row, day_col)
                if itx and (itx.text() or "").strip().isdigit():
                    total_qty += int(itx.text().strip())
            t_item = self.table.item(keep_row, self._col_total_qty)
            if t_item is not None:
                t_item.setText(str(total_qty))
            self._recalc_price_total_for_row(keep_row)
            for d in range(1, self.days_in_month + 1):
                self._apply_day_cell_style(keep_row, self._day_start + (d - 1))

        finally:
            try:
                self.table.blockSignals(False)
            except Exception:
                pass

        self._apply_route_group_spans()
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
        parent,
        db: DatabaseManager,
        contract_id: int,
        service_type: str,
        year_month: tuple[int, int],
        embedded: bool = False,
    ):
        super().__init__(parent)
        self.db = db
        self.contract_id = int(contract_id)
        self.service_type = (service_type or "").strip()
        self.year, self.month = year_month

        self._embedded = bool(embedded)

        if not self._embedded:
            self.setWindowTitle("Toplu Puantaj")
            self.setWindowState(Qt.WindowState.WindowMaximized)
        else:
            try:
                self.setWindowFlags(Qt.WindowType.Widget)
            except Exception:
                pass

        self.days_in_month = QDate(self.year, self.month, 1).daysInMonth()
        self.max_days = 31
        self.month_key = f"{int(self.year)}-{int(self.month):02d}"

        self.table = QTableWidget(self)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)

        try:
            self.table.verticalHeader().setDefaultSectionSize(25)
        except Exception:
            pass

        try:
            f = self.table.font()
            if f.pointSize() > 0:
                f.setPointSize(max(7, f.pointSize() - 2))
                self.table.setFont(f)
            hf = self.table.horizontalHeader().font()
            if hf.pointSize() > 0:
                hf.setPointSize(max(7, hf.pointSize() - 2))
                self.table.horizontalHeader().setFont(hf)
        except Exception:
            pass

        headers = [
            "S\nNO",
            "GÜZERGAH\nDURAKLAR",
            "DURAKLAR",
            "ARAÇ +\nKPST",
            "ŞOFÖR",
            "GİRİŞ ÇIKIŞ\nSAATLERİ",
        ]
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
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        day_start = 6
        for i in range(day_start, day_start + self.max_days):
            h.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(i, 24)
        h.setSectionResizeMode(day_start + self.max_days, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(day_start + self.max_days + 1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(day_start + self.max_days + 2, QHeaderView.ResizeMode.ResizeToContents)

        try:
            self.table.setColumnWidth(0, 40)
            self.table.setColumnWidth(1, 120)
            self.table.setColumnWidth(2, 256)
            self.table.setColumnWidth(3, 110)
            self.table.setColumnWidth(4, 120)
            self.table.setColumnWidth(5, 120)
            self.table.setColumnWidth(self._col_total_qty, 55)
            self.table.setColumnWidth(self._col_price, 85)
            self.table.setColumnWidth(self._col_total_price, 95)
        except Exception:
            pass

        try:
            self.table.setColumnWidth(0, 35)
        except Exception:
            pass

        self._day_start = day_start
        self._col_total_qty = day_start + self.max_days
        self._col_price = day_start + self.max_days + 1
        self._col_total_price = day_start + self.max_days + 2

        self._col_vehicle = 3
        self._col_driver = 4
        self._col_time_text = 5
        self._col_stops = 2

        try:
            h.setSectionResizeMode(self._col_driver, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(self._col_driver, 120)
        except Exception:
            pass

        try:
            self.table.setColumnHidden(self._col_stops, True)
            self.table.setColumnWidth(self._col_stops, 0)
        except Exception:
            pass

        self._vehicle_map = {}
        self._driver_map = {}
        try:
            if hasattr(self.db, "get_araclar_list_with_capacity"):
                for vcode, plate, cap in self.db.get_araclar_list_with_capacity(only_active=True):
                    self._vehicle_map[str(vcode)] = (str(plate), int(cap or 0))
            else:
                for vcode, plate in self.db.get_araclar_list(only_active=True):
                    self._vehicle_map[str(vcode)] = (str(plate), 0)
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

        def _split_time_range(tb_val: str, max_minutes: int = 30) -> tuple[str, str] | None:
            t = str(tb_val or "").strip()
            if "-" not in t:
                return None
            left, right = (t.split("-", 1) + [""])[:2]
            left = left.strip()
            right = right.strip()
            if not left or not right:
                return None
            p1 = _parse_time(left)
            p2 = _parse_time(right)
            if p1 is None or p2 is None:
                return None

            # Only treat short ranges as entry/exit pairs.
            # Long ranges like 08:00-16:00 should not be auto-split.
            try:
                m1 = int(p1[0]) * 60 + int(p1[1])
                m2 = int(p2[0]) * 60 + int(p2[1])
                diff = abs(m2 - m1)
                diff = min(diff, 1440 - diff)  # handle crossing midnight
                if int(diff) > int(max_minutes):
                    return None
            except Exception:
                return None
            return left, right

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

        def _route_movement_type_by_id(route_params_id: int) -> str:
            try:
                conn = self.db.connect()
                if not conn:
                    return ""
                cur = conn.cursor()
                try:
                    cur.execute(
                        "SELECT COALESCE(movement_type,'') FROM route_params WHERE id = ? LIMIT 1",
                        (int(route_params_id),),
                    )
                    row = cur.fetchone()
                    return str((row[0] if row else "") or "").strip()
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
            except Exception:
                return ""

        def _route_is_tek(route_row) -> bool:
            try:
                if route_row is None:
                    return False
                rid = 0
                try:
                    rid = int(route_row[0] or 0)
                except Exception:
                    rid = 0
                mt = ""
                if len(route_row) > 4:
                    mt = str(route_row[4] or "")
                elif len(route_row) > 3 and isinstance(route_row[3], str):
                    mt = str(route_row[3] or "")
                if (not str(mt or "").strip()) and int(rid or 0) > 0:
                    mt = _route_movement_type_by_id(int(rid))
                mt = mt.strip().lower()
                if not mt:
                    return False
                # treat 'tek servis' as TEK
                if "tek" in mt and ("çift" not in mt and "cift" not in mt):
                    return True
                return False
            except Exception:
                return False

        def add_subrow(route_params_id: int, route_name: str, time_block: str, label: str, plan_time_block: str | None = None):
            row = self.table.rowCount()
            self.table.insertRow(row)

            try:
                self.table.setRowHeight(row, 25)
            except Exception:
                pass

            sno = QTableWidgetItem(str(row + 1))
            sno.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            sno.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, sno)

            stops_txt = ""
            try:
                for rr in self._route_rows:
                    if int(rr[0] or 0) == int(route_params_id):
                        stops_txt = str(rr[2] or "") if len(rr) > 2 else ""
                        break
            except Exception:
                stops_txt = ""

            r_item = QTableWidgetItem((str(route_name or "").strip() + ("\n" + str(stops_txt).strip() if str(stops_txt).strip() else "")).strip())
            r_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            r_item.setData(Qt.ItemDataRole.UserRole, int(route_params_id))
            self.table.setItem(row, 1, r_item)
            s_item = QTableWidgetItem(stops_txt)
            s_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(row, self._col_stops, s_item)

            cmb_v = QComboBox()
            cmb_v.addItem("Seçiniz...", None)
            for vcode, rec in self._vehicle_map.items():
                try:
                    plate, cap = rec
                except Exception:
                    plate, cap = str(rec), 0
                label_v = f"{plate} ({int(cap)})" if int(cap or 0) > 0 else str(plate)
                cmb_v.addItem(label_v, vcode)
            self._apply_compact_table_combo(cmb_v)
            self.table.setCellWidget(row, self._col_vehicle, cmb_v)

            cmb_d = QComboBox()
            cmb_d.addItem("Seçiniz...", None)
            for did, name in self._driver_map.items():
                cmb_d.addItem(name, did)
            self._apply_compact_table_combo(cmb_d)
            self.table.setCellWidget(row, self._col_driver, cmb_d)

            t_item = QTableWidgetItem(_time_text_for_time_block(label))
            t_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, self._col_time_text, t_item)

            for d in range(1, self.max_days + 1):
                col = self._day_start + (d - 1)
                it = QTableWidgetItem("")
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                if d > self.days_in_month:
                    it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    it.setBackground(QColor("#f0f0f0"))
                elif QDate(self.year, self.month, d).dayOfWeek() in (6, 7):
                    it.setBackground(self._bg_weekend)
                self.table.setItem(row, col, it)

            plan_tb = str(plan_time_block) if plan_time_block is not None else str(time_block)
            is_planned = (int(route_params_id), str(plan_tb)) in (self._planned_keys or set())
            if is_planned:
                planned_bg = QColor("#fff3cd")
                planned_font = QFont()
                planned_font.setBold(True)

                for cc in (0, 1, self._col_stops, self._col_time_text):
                    it0 = self.table.item(row, cc)
                    if it0 is not None:
                        it0.setBackground(planned_bg)
                        it0.setFont(planned_font)
                for cc in (self._col_vehicle, self._col_driver):
                    w = self.table.cellWidget(row, cc)
                    if w is not None:
                        try:
                            if isinstance(w, QComboBox):
                                self._apply_compact_table_combo(w, bg_color="#fff3cd")
                            else:
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
                    "plan_time_block": str(plan_tb),
                }
            )

        self.table.setRowCount(0)

        start_date = QDate(self.year, self.month, 1).toString("yyyy-MM-dd")
        end_date = QDate(self.year, self.month, self.days_in_month).toString("yyyy-MM-dd")

        self._planned_keys = _planned_keys_for_context(int(self.contract_id), self.month_key, str(self.service_type))

        if self._planned_keys:
            planned_by_route: dict[int, list[str]] = {}
            for _rid, tb in (self._planned_keys or set()):
                try:
                    rid_i = int(_rid or 0)
                except Exception:
                    rid_i = 0
                tbs = str(tb or "").strip()
                if not rid_i or not tbs:
                    continue
                planned_by_route.setdefault(rid_i, []).append(tbs)
            for rid_i, blocks in list(planned_by_route.items()):
                uniq = []
                seen = set()
                for b in blocks:
                    if b in seen:
                        continue
                    seen.add(b)
                    uniq.append(b)
                planned_by_route[rid_i] = sorted([str(x) for x in uniq if str(x)], key=_tb_sort_key)

            for row in self._route_rows:
                try:
                    rid = int(row[0] or 0)
                    rname = row[1] if len(row) > 1 else ""
                except Exception:
                    continue

                blocks = planned_by_route.get(int(rid), [])
                if not blocks:
                    continue

                has_range = False
                try:
                    for tb in blocks:
                        if _split_time_range(tb) is not None:
                            has_range = True
                            break
                except Exception:
                    has_range = False

                if _route_is_tek(row) or has_range:
                    # TEK SERVİS (or planned range blocks): expand 'HH:MM-HH:MM' into entry/exit rows.
                    for tb in blocks:
                        rng = _split_time_range(tb)
                        if rng is not None:
                            g, c = rng
                            add_subrow(int(rid), rname or "", str(g), str(g), str(tb))
                            add_subrow(int(rid), rname or "", str(c), str(c), str(tb))
                        else:
                            add_subrow(int(rid), rname or "", str(tb), str(tb))
                else:
                    for tb in blocks:
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

                if _route_is_tek(row):
                    # TEK SERVİS: default to entry/exit rows for up to 3 shifts
                    base_times = _time_blocks_for_context(int(self.contract_id), self.month_key, str(self.service_type))
                    base_times = sorted([str(x) for x in (base_times or []) if str(x)], key=_tb_sort_key)
                    for tb in base_times:
                        add_subrow(int(rid), rname or "", str(tb), str(tb))
                else:
                    for tb in time_blocks:
                        add_subrow(int(rid), rname or "", str(tb), str(tb))

        self.btn_save = QPushButton("KAYDET", self)
        self.btn_save.clicked.connect(self._save)

        lay = QVBoxLayout()
        lay.addWidget(self.table)
        lay.addWidget(self.btn_save)
        self.setLayout(lay)

        self._load_existing_entries()

        self._apply_route_group_spans()

        self.table.itemChanged.connect(self._recalc_row_total)

        try:
            self.table.cellDoubleClicked.connect(lambda r, c: self._open_day_popup(int(r)))
        except Exception:
            pass

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

        meta = self._row_meta[row] if row < len(self._row_meta) else None
        try:
            route_params_id = int((meta or {}).get("route_params_id") or 0)
        except Exception:
            route_params_id = 0
        if not route_params_id:
            return None

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
        if c == self._col_time_text:
            menu = QMenu(self)
            act_split = menu.addAction("Satırı Ayır (ÇİFT)")
            act_merge = menu.addAction("Satırı Birleştir")
            act = menu.exec(self.table.viewport().mapToGlobal(pos))
            if act == act_split:
                self._split_row(r)
            elif act == act_merge:
                self._merge_row(r)
            return

        if c < self._day_start or c >= self._day_start + self.max_days:
            return
        day_num = self._day_for_col(c)
        if day_num is None:
            return

        meta = self._row_meta[r] if r < len(self._row_meta) else None
        try:
            route_params_id = int((meta or {}).get("route_params_id") or 0)
        except Exception:
            route_params_id = 0
        if not route_params_id:
            return

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
        for vcode, rec in self._vehicle_map.items():
            try:
                plate, cap = rec
            except Exception:
                plate, cap = str(rec), 0
            label_v = f"{plate} ({int(cap)})" if int(cap or 0) > 0 else str(plate)
            cmb_v2.addItem(label_v, vcode)
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
                txtp = (item.text() or "").strip()
                self._parse_tr_float(txtp)
            except Exception:
                return
            item.setText(self._format_tr_currency(self._parse_tr_float(txtp)))
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

    def _open_day_popup(self, row: int):
        if row < 0 or row >= self.table.rowCount():
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Gün Değerleri")

        lay = QVBoxLayout(dlg)
        grid = QGridLayout()

        day_names = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
        for i, nm in enumerate(day_names):
            lab = QLabel(nm)
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(lab, 0, i)

        first_wd = int(QDate(self.year, self.month, 1).dayOfWeek())  # 1..7
        day_edits: dict[int, QLineEdit] = {}

        r0 = 1
        c0 = first_wd - 1
        for d in range(1, self.days_in_month + 1):
            rr = r0 + ((c0 + (d - 1)) // 7)
            cc = (c0 + (d - 1)) % 7

            ed = QLineEdit()
            ed.setFixedSize(32, 24)
            ed.setAlignment(Qt.AlignmentFlag.AlignCenter)
            try:
                txt = (self.table.item(row, self._day_start + (d - 1)).text() or "").strip()
            except Exception:
                txt = ""
            ed.setText(txt)
            day_edits[d] = ed
            grid.addWidget(ed, rr, cc)

        lay.addLayout(grid)

        btn_row = QHBoxLayout()
        btn_apply = QPushButton("GÜN DEĞERLERİNİ AKTAR")
        btn_cancel = QPushButton("Kapat")
        btn_row.addWidget(btn_apply)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_cancel)
        lay.addLayout(btn_row)

        def _apply():
            try:
                self.table.blockSignals(True)
                for d, ed in day_edits.items():
                    txt = (ed.text() or "").strip()
                    if txt and not txt.isdigit():
                        txt = ""
                    it = self.table.item(row, self._day_start + (d - 1))
                    if it is None:
                        it = QTableWidgetItem("")
                        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                        self.table.setItem(row, self._day_start + (d - 1), it)
                    it.setText(txt)
                    self._apply_day_cell_style(row, self._day_start + (d - 1))

                total = 0
                for day_col in range(self._day_start, self._day_start + self.days_in_month):
                    itx = self.table.item(row, day_col)
                    if itx and (itx.text() or "").strip().isdigit():
                        total += int(itx.text().strip())
                t_item = self.table.item(row, self._col_total_qty)
                if t_item is not None:
                    t_item.setText(str(total))
                self._recalc_price_total_for_row(row)
            finally:
                try:
                    self.table.blockSignals(False)
                except Exception:
                    pass
            dlg.accept()

        btn_apply.clicked.connect(_apply)
        btn_cancel.clicked.connect(dlg.reject)
        dlg.exec()

    def _recalc_price_total_for_row(self, row: int):
        t_item = self.table.item(row, self._col_total_qty)
        p_item = self.table.item(row, self._col_price)
        out_item = self.table.item(row, self._col_total_price)
        if t_item is None or p_item is None or out_item is None:
            return
        try:
            t = self._parse_tr_float(t_item.text() or "0")
        except Exception:
            t = 0.0
        try:
            p = self._parse_tr_float(p_item.text() or "0")
        except Exception:
            p = 0.0
        total = float(t) * float(p)
        out_item.setText(self._format_tr_currency(total))
        try:
            out_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        except Exception:
            pass

    def _load_existing_entries(self):
        start_date = QDate(self.year, self.month, 1).toString("yyyy-MM-dd")
        end_date = QDate(self.year, self.month, self.days_in_month).toString("yyyy-MM-dd")

        row_index_plan: dict[tuple[int, str], list[int]] = {}
        row_index_time: dict[tuple[int, str], list[int]] = {}
        for idx, meta in enumerate(self._row_meta):
            rid = int(meta.get("route_params_id") or 0)
            if rid <= 0:
                continue

            tb_plan = str(meta.get("plan_time_block") or "").strip()
            if tb_plan:
                row_index_plan.setdefault((rid, tb_plan), []).append(int(idx))

            tb_time = str(meta.get("time_block") or "").strip()
            if tb_time:
                row_index_time.setdefault((rid, tb_time), []).append(int(idx))

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
                    if len(row) > 4:
                        mt_r = row[4]
                    elif len(row) > 3 and isinstance(row[3], str):
                        mt_r = row[3]
                    else:
                        mt_r = ""
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

            for key, row_idxs in row_index_plan.items():
                pv, pd = plan_map.get(key, ("", ""))
                for row_idx in (row_idxs or []):
                    cmb_v = self.table.cellWidget(row_idx, self._col_vehicle)
                    cmb_d = self.table.cellWidget(row_idx, self._col_driver)
                    if cmb_v is not None and pv:
                        idx2 = cmb_v.findData(str(pv))
                        if idx2 >= 0:
                            cmb_v.setCurrentIndex(idx2)
                    if cmb_d is not None and pd:
                        idx2 = cmb_d.findData(str(pd))
                        if idx2 >= 0:
                            cmb_d.setCurrentIndex(idx2)

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
                rlist = row_index_time.get(key) or []

                try:
                    day = int(str(d_s)[-2:])
                except Exception:
                    day = 0
                if day < 1 or day > self.days_in_month:
                    continue
                col = self._day_start + (day - 1)

                for r in rlist:
                    self._apply_day_cell_style(int(r), col)

            for key, row_idxs in row_index_time.items():
                pr = price_map.get(key)
                if pr is None:
                    rp = route_default_price.get(int(key[0] or 0))
                    if rp is not None:
                        pr = rp
                    else:
                        pr = route_price_by_id.get(int(key[0] or 0))

                if pr is None:
                    continue

                for row_idx in (row_idxs or []):
                    p_item = self.table.item(int(row_idx), self._col_price)
                    if p_item is not None:
                        p_item.setText(self._format_tr_currency(pr))

            for route_params_id, trip_date, time_block, qty, time_text in rows:
                key = (int(route_params_id or 0), str(time_block or ""))
                rlist = row_index_time.get(key) or []
                if not rlist:
                    continue

                day = 0
                try:
                    day = int(str(trip_date)[-2:])
                except Exception:
                    day = 0
                if day < 1 or day > self.days_in_month:
                    continue

                col = self._day_start + (day - 1)
                try:
                    q = int(qty or 0)
                except Exception:
                    q = 0
                for r in rlist:
                    it = self.table.item(int(r), col)
                    if it is None:
                        continue
                    it.setText(str(q) if q != 0 else "")
                    self._apply_day_cell_style(int(r), col)

                    if (time_text or "").strip():
                        t_item = self.table.item(int(r), self._col_time_text)
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
                price = self._parse_tr_float(p_txt)
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

        if bool(getattr(self, "_embedded", False)):
            try:
                QMessageBox.information(self, "Bilgi", "Kayıt edildi.")
            except Exception:
                pass
            return

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


class PlanTrackingDialog(QDialog):
    def __init__(
        self,
        parent: QMainWindow,
        db: DatabaseManager,
        ctx: AttendanceContext,
        year_month: tuple[int, int],
        service_type_values: list[str],
    ):
        super().__init__(parent)
        self.db = db
        self.ctx = ctx
        self.year, self.month = year_month
        self.service_type_values = [str(x) for x in (service_type_values or []) if str(x).strip()]
        if not self.service_type_values:
            self.service_type_values = [str(ctx.service_type)]

        self.setWindowTitle("Plan Takip (Günlük)")
        self.setSizeGripEnabled(True)

        self.table = QTableWidget(self)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        try:
            self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        except Exception:
            pass
        try:
            self.table.verticalHeader().setDefaultSectionSize(25)
        except Exception:
            pass
        self.table.setAlternatingRowColors(True)

        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Gün", "Planlanan", "Gerçekleşen", "Eksik"])
        try:
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            self.table.horizontalHeader().setStretchLastSection(False)
        except Exception:
            pass

        btn_close = QPushButton("Kapat")
        btn_close.clicked.connect(self.accept)

        lay = QVBoxLayout()
        lay.addWidget(self.table)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(btn_close)
        lay.addLayout(footer)
        self.setLayout(lay)

        self._load()
        self._apply_compact_sizing()

    def _apply_compact_sizing(self):
        try:
            self.table.resizeColumnsToContents()
        except Exception:
            pass

        try:
            self.table.horizontalHeader().setMinimumSectionSize(10)
        except Exception:
            pass

        try:
            total_w = 0
            for c in range(self.table.columnCount()):
                total_w += int(self.table.columnWidth(c) or 0)

            frame_w = int(self.table.frameWidth() or 0) * 2
            vbar_w = 0
            try:
                vbar_w = int(self.table.verticalScrollBar().sizeHint().width() or 0)
            except Exception:
                vbar_w = 0

            total_w = total_w + frame_w + vbar_w + 60
        except Exception:
            total_w = 520

        try:
            header_h = int(self.table.horizontalHeader().height() or 0)
        except Exception:
            header_h = 30

        try:
            visible_rows = min(int(self.table.rowCount() or 0), 18)
        except Exception:
            visible_rows = 18

        rows_h = int(visible_rows) * 25
        total_h = header_h + rows_h + 90

        try:
            screen = QApplication.primaryScreen()
            if screen is not None:
                geom = screen.availableGeometry()
                max_w = int(geom.width() * 0.95)
                max_h = int(geom.height() * 0.95)
                total_w = min(total_w, max_w)
                total_h = min(total_h, max_h)
        except Exception:
            pass

        try:
            self.resize(int(total_w), int(total_h))
            self.setFixedWidth(int(total_w))
        except Exception:
            pass

    def _load(self):
        days_in_month = QDate(self.year, self.month, 1).daysInMonth()
        start_date = QDate(self.year, self.month, 1).toString("yyyy-MM-dd")
        end_date = QDate(self.year, self.month, days_in_month).toString("yyyy-MM-dd")

        planned_keys: set[tuple[int, str]] = set()
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            placeholders = ",".join(["?"] * len(self.service_type_values))
            cursor.execute(
                f"""
                SELECT route_params_id, time_block
                FROM trip_plan
                WHERE contract_id = ?
                  AND month = ?
                  AND service_type IN ({placeholders})
                """,
                (int(self.ctx.contract_id), str(self.ctx.month), *self.service_type_values),
            )
            rows = cursor.fetchall() or []
            conn.close()
            planned_keys = {
                (int(r[0] or 0), str(r[1] or ""))
                for r in rows
                if int(r[0] or 0) and str(r[1] or "")
            }
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            planned_keys = set()

        planned_per_day = len(planned_keys)

        actual_per_day = {d: 0.0 for d in range(1, days_in_month + 1)}
        try:
            conn2 = self.db.connect()
            cur2 = conn2.cursor()
            placeholders = ",".join(["?"] * len(self.service_type_values))
            if planned_keys:
                cur2.execute(
                    f"""
                    SELECT trip_date, route_params_id, time_block, COALESCE(SUM(qty),0)
                    FROM trip_entries
                    WHERE contract_id = ?
                      AND service_type IN ({placeholders})
                      AND trip_date BETWEEN ? AND ?
                    GROUP BY trip_date, route_params_id, time_block
                    """,
                    (int(self.ctx.contract_id), *self.service_type_values, start_date, end_date),
                )
                for trip_date, rid, tb, qty_sum in (cur2.fetchall() or []):
                    try:
                        rid_i = int(rid or 0)
                        tb_s = str(tb or "")
                        if (rid_i, tb_s) not in planned_keys:
                            continue
                        qd = QDate.fromString(str(trip_date or ""), "yyyy-MM-dd")
                        if not qd.isValid():
                            continue
                        day = int(qd.day())
                        actual_per_day[day] = float(actual_per_day.get(day, 0) or 0) + float(qty_sum or 0)
                    except Exception:
                        continue
            else:
                # Bu ay için plan yoksa bile girilmiş puantaj değerlerini gün gün göster.
                cur2.execute(
                    f"""
                    SELECT trip_date, COALESCE(SUM(qty),0)
                    FROM trip_entries
                    WHERE contract_id = ?
                      AND service_type IN ({placeholders})
                      AND trip_date BETWEEN ? AND ?
                    GROUP BY trip_date
                    """,
                    (int(self.ctx.contract_id), *self.service_type_values, start_date, end_date),
                )
                for trip_date, qty_sum in (cur2.fetchall() or []):
                    try:
                        qd = QDate.fromString(str(trip_date or ""), "yyyy-MM-dd")
                        if not qd.isValid():
                            continue
                        day = int(qd.day())
                        actual_per_day[day] = float(actual_per_day.get(day, 0) or 0) + float(qty_sum or 0)
                    except Exception:
                        continue
            conn2.close()
        except Exception:
            try:
                conn2.close()
            except Exception:
                pass

        self.table.setRowCount(0)
        for day in range(1, days_in_month + 1):
            actual = float(actual_per_day.get(day, 0) or 0)
            planned = float(planned_per_day)
            missing = planned - actual
            if missing < 0:
                missing = 0.0

            row = self.table.rowCount()
            self.table.insertRow(row)
            try:
                self.table.setRowHeight(row, 25)
            except Exception:
                pass

            it_day = QTableWidgetItem(str(day))
            it_day.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, it_day)

            it_p = QTableWidgetItem(str(int(planned) if planned.is_integer() else planned))
            it_p.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, it_p)

            it_a = QTableWidgetItem(str(int(actual) if actual.is_integer() else actual))
            it_a.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, it_a)

            it_m = QTableWidgetItem(str(int(missing) if missing.is_integer() else missing))
            it_m.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if missing > 0:
                it_m.setBackground(QColor("#f8d7da"))
            self.table.setItem(row, 3, it_m)
