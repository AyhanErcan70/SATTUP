
from __future__ import annotations

from dataclasses import dataclass
import json
import re
import unicodedata
from datetime import datetime

from PyQt6 import uic
from PyQt6.QtCore import Qt, QDate, QTimer, QSignalBlocker
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
    QCheckBox,
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
from config import get_ui_path


def _norm_month_key(m: str) -> str:
    ms = str(m or "").strip()
    if not ms:
        return ms
    try:
        a, b = ms.split("-", 1)
        y = int(a)
        mm = int(b)
        return f"{y:04d}-{mm:02d}"
    except Exception:
        return ms


def _parse_hhmm(txt: str):
    m = re.match(r"^(\d{1,2}):(\d{2})$", (txt or "").strip())
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2))
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        return None
    return hh, mm


def _tb_sort_key_0700(tb_val: str):
    tbs = str(tb_val or "").strip().upper()
    m = re.match(r"^([GC])(\d)$", tbs)
    if m:
        gc = 0 if m.group(1) == "G" else 1
        return (0, int(m.group(2)), gc)

    t0 = tbs
    if "-" in t0:
        t0 = (t0.split("-", 1) + [""])[0].strip()

    parsed = _parse_hhmm(t0)
    if parsed is not None:
        hh, mm = parsed
        try:
            minutes = int(hh) * 60 + int(mm)
        except Exception:
            minutes = 999999
        if minutes < (7 * 60):
            minutes += 24 * 60
        return (1, minutes, 0)

    return (2, 999999, 0)


@dataclass(frozen=True)
class AttendanceContext:
    contract_id: int
    month: str
    service_type: str


class AttendanceApp(QWidget):
    def __init__(self, parent=None, user_data=None, db: DatabaseManager | None = None):
        super().__init__(parent)
        uic.loadUi(get_ui_path("attendance_window.ui"), self)
        self.setObjectName("main_form")

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

        try:
            if hasattr(self, "sekmeli_form") and hasattr(self, "tab_plan"):
                self.sekmeli_form.setCurrentWidget(self.tab_plan)
        except Exception:
            pass

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

        if hasattr(self, "btn_ay_kapat"):
            try:
                self.btn_ay_kapat.clicked.connect(self._close_month)
            except Exception:
                pass

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

    def _close_month(self):
        month = str(self._selected_month_key() or "").strip()
        if not month or "-" not in month:
            QMessageBox.warning(self, "Uyarı", "Ay kapatma için dönem seçiniz.")
            return

        try:
            from app.core.db_manager import DatabaseManager

            db = DatabaseManager()
            conn = db.connect()
            if not conn:
                QMessageBox.critical(self, "Hata", "Veritabanına bağlanılamadı.")
                return

            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(1)
                FROM trip_period_lock
                WHERE month = ? AND COALESCE(locked,0) = 0
                """,
                (str(month),),
            )
            unlocked_cnt = int((cur.fetchone() or [0])[0] or 0)

            cur.execute(
                """
                SELECT COUNT(1)
                FROM hakedis
                WHERE period = ?
                  AND UPPER(COALESCE(status,'')) NOT IN ('ONAYLANDI','FATURALANDI')
                """,
                (str(month),),
            )
            pending_hakedis_cnt = int((cur.fetchone() or [0])[0] or 0)

            conn.close()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            QMessageBox.critical(self, "Hata", "Ay kapatma kontrolü sırasında hata oluştu.")
            return

        if unlocked_cnt > 0 or pending_hakedis_cnt > 0:
            msg = (
                f"Ay kapatılamaz: {month}\n\n"
                f"- Kilitlenmemiş dönem kaydı: {unlocked_cnt}\n"
                f"- Onaylanmamış/Faturalanmamış hakediş: {pending_hakedis_cnt}\n\n"
                "Eksikleri tamamlayıp tekrar deneyiniz."
            )
            QMessageBox.warning(self, "Uyarı", msg)
            return

        user_id = int((self.user_data or {}).get("id") or 0)
        try:
            ok = self.db.set_period_closed(str(month), user_id)
        except Exception:
            ok = False
        if not ok:
            QMessageBox.critical(self, "Hata", "Ay kapatma işlemi kaydedilemedi.")
            return

        QMessageBox.information(self, "Bilgi", f"Ay kapatıldı: {month}")

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

            cmb.setProperty("no_zebra", True)
            cmb.setAlternatingRowColors(False)
        except Exception:
            return

    def _render_toplu_puantaj_tab(self):
        if not hasattr(self, "tbl_toplu_puantaj"):
            return

        ctx = self._current_context()
        tbl = self.tbl_toplu_puantaj

        try:
            try:
                tbl.setProperty("no_zebra", True)
            except Exception:
                pass
            tbl.setAlternatingRowColors(False)
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
                (int(ctx.contract_id), str(_norm_month_key(ctx.month)), *st_values),
            )
            rows = cur.fetchall() or []

            if not rows:
                try:
                    cur.execute(
                        """
                        SELECT p.route_params_id,
                               p.time_block,
                               COALESCE(r.route_name,'')
                        FROM trip_plan p
                        LEFT JOIN route_params r ON r.id = p.route_params_id
                        WHERE p.contract_id = ?
                          AND p.month = ?
                        GROUP BY p.route_params_id, p.time_block
                        ORDER BY COALESCE(r.route_name,''), p.time_block
                        """,
                        (int(ctx.contract_id), str(_norm_month_key(ctx.month))),
                    )
                    rows = cur.fetchall() or []
                except Exception:
                    rows = []

            conn.close()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            rows = []

        # Ensure deterministic ordering for multiple time_blocks per route:
        # 07:00 is treated as day start, so 08:00.. comes before 00:00..
        try:
            rows = sorted(
                rows,
                key=lambda x: (
                    str(x[2] or ""),
                    _tb_sort_key_0700(str(x[1] or "")),
                    int(x[0] or 0),
                ),
            )
        except Exception:
            pass

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

        month_key = _norm_month_key(str(ctx.month))

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
                (int(ctx.contract_id), str(month_key), *st_values),
            )
            rows = cur.fetchall() or []

            if not rows:
                try:
                    cur.execute(
                        """
                        SELECT route_params_id, time_block
                        FROM trip_plan
                        WHERE contract_id = ?
                          AND month = ?
                        """,
                        (int(ctx.contract_id), str(month_key)),
                    )
                    rows = cur.fetchall() or []
                except Exception:
                    rows = []

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
            try:
                tbl.horizontalHeader().setMinimumSectionSize(20)
            except Exception:
                pass
            for c in range(1, tbl.columnCount()):
                tbl.setColumnWidth(c, 40)
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
        raw = (service_type or "").strip()
        if not raw:
            return []

        # Keep this in sync with Trips module logic: service_type values in DB can vary
        # by underscores and TAŞIMA/TASIMA spelling.
        s = raw.upper().replace("_", " ")
        s = re.sub(r"\s+", " ", s).strip()
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
        # Add common variants (raw, normalized with spaces, underscore form, TASIMA form)
        for v in (raw, s, s2, s.replace(" ", "_"), s2.replace(" ", "_")):
            vv = (v or "").strip()
            if vv and vv not in vals:
                vals.append(vv)
        return vals

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
            QMessageBox.warning(self, "Uyarı", "   Müşteri / Sözleşme / Hizmet seçiniz.")
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
            tab_name = "Toplu Puantaj"
            # Prefer exporting the embedded detailed bulk puantaj grid (if active)
            # instead of the summary list table.
            try:
                if getattr(self, "_embedded_bulk", None) is not None:
                    bulk = self._embedded_bulk
                    if getattr(bulk, "table", None) is not None and bool(bulk.isVisible()):
                        tbl = bulk.table
                    else:
                        tbl = self.tbl_toplu_puantaj
                else:
                    tbl = self.tbl_toplu_puantaj
            except Exception:
                tbl = self.tbl_toplu_puantaj

        if tbl is None:
            QMessageBox.warning(self, "Uyarı", "Excel'e aktarılacak tablo bulunamadı.")
            return

        try:
            if int(tbl.rowCount()) <= 0:
                QMessageBox.information(self, "Bilgi", "Excel'e aktarılacak satır yok.")
                return
        except Exception:
            pass

        # For Toplu Puantaj detailed grid: exclude completely empty rows from export.
        try:
            if tab_name == "Toplu Puantaj" and getattr(self, "_embedded_bulk", None) is not None:
                bulk = self._embedded_bulk
                if bulk is not None and getattr(bulk, "table", None) is not None and tbl is bulk.table:
                    day_start = int(getattr(bulk, "_day_start", 0) or 0)
                    days_in_month = int(getattr(bulk, "days_in_month", 0) or 0)
                    col_total_qty = int(getattr(bulk, "_col_total_qty", 0) or 0)
                    col_total_price = int(getattr(bulk, "_col_total_price", 0) or 0)
                    col_time_text = int(getattr(bulk, "_col_time_text", 0) or 0)

                    def _txt_at(r0: int, c0: int) -> str:
                        try:
                            it0 = tbl.item(int(r0), int(c0))
                            return str(it0.text() if it0 is not None else "").strip()
                        except Exception:
                            return ""

                    def _tr_float(s0: str) -> float:
                        try:
                            t = str(s0 or "").strip()
                            if not t:
                                return 0.0
                            t = t.replace("₺", "").replace("TL", "")
                            t = t.replace(" ", "")
                            # Remove thousands separator and convert decimal comma
                            t = t.replace(".", "").replace(",", ".")
                            return float(t)
                        except Exception:
                            return 0.0

                    def _has_any_data(r0: int) -> bool:
                        # Any day cell with a non-zero value (qty)
                        has_qty = False
                        try:
                            for d0 in range(0, max(0, int(days_in_month))):
                                c0 = int(day_start) + int(d0)
                                t0 = _txt_at(r0, c0)
                                if not t0:
                                    continue
                                # Qty is expected numeric. Non-numeric entries count as data.
                                try:
                                    if int(str(t0).strip()) > 0:
                                        has_qty = True
                                        break
                                except Exception:
                                    has_qty = True
                                    break
                        except Exception:
                            pass

                        if has_qty:
                            return True

                        # Total price must be > 0 to be exported.
                        try:
                            tp = _txt_at(r0, col_total_price)
                            if _tr_float(tp) > 0.0:
                                return True
                        except Exception:
                            pass

                        return False

                    export_table = QTableWidget()
                    export_table.setColumnCount(int(tbl.columnCount()))
                    try:
                        export_table.setHorizontalHeaderLabels(
                            [tbl.horizontalHeaderItem(i).text() for i in range(int(tbl.columnCount()))]
                        )
                    except Exception:
                        pass

                    out_r = 0
                    for r in range(int(tbl.rowCount())):
                        if not _has_any_data(int(r)):
                            continue
                        export_table.insertRow(out_r)
                        for c in range(int(tbl.columnCount())):
                            export_table.setItem(out_r, c, QTableWidgetItem(_txt_at(int(r), int(c))))
                        out_r += 1

                    if int(export_table.rowCount()) <= 0:
                        QMessageBox.information(self, "Bilgi", "Excel'e aktarılacak satır yok.")
                        return

                    tbl = export_table
        except Exception:
            pass

        try:
            user_txt = str((self.user_data or {}).get("full_name") or (self.user_data or {}).get("username") or "")
        except Exception:
            user_txt = ""

        report_title = f"{tab_name} - {ctx.month}"
        meta = None
        try:
            cust_name = ""
            if hasattr(self, "cmb_musteri") and self.cmb_musteri is not None:
                cust_name = str(self.cmb_musteri.currentText() or "").strip()
                if cust_name.lower().startswith("seçiniz"):
                    cust_name = ""
            meta = {"customer_name": cust_name, "month": str(ctx.month or "").strip()}
        except Exception:
            meta = None

        create_excel(tbl, report_title=report_title, username=user_txt or "", parent=self, meta=meta)

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
        conn2 = None
        try:
            conn2 = self.db.connect()
            if conn2 is None:
                return True
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
                        missing.append((int(rid_i), str(tb_s), str(d)))
        except Exception:
            missing = []
        finally:
            try:
                if conn2 is not None:
                    conn2.close()
            except Exception:
                pass

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
        ctx = self._current_context()
        if ctx is None:
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
                    try:
                        self._embedded_bulk.refresh_from_db()
                    except Exception:
                        pass
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
            try:
                if self._embedded_bulk is not None and self._embedded_bulk_ctx == ctx_key:
                    self._embedded_bulk.refresh_from_db()
            except Exception:
                pass
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
    def _official_holiday_set(self, year: int) -> set[str]:
        # Fixed-date official holidays (Turkey). Stored as ISO yyyy-MM-dd strings.
        out = set()
        try:
            fixed = [
                (1, 1),   # 1 Ocak
                (4, 23),  # 23 Nisan
                (5, 1),   # 1 Mayıs
                (5, 19),  # 19 Mayıs
                (7, 15),  # 15 Temmuz
                (8, 30),  # 30 Ağustos
                (10, 29), # 29 Ekim
            ]
            for m, d in fixed:
                qd = QDate(int(year), int(m), int(d))
                if qd.isValid():
                    out.add(qd.toString("yyyy-MM-dd"))
        except Exception:
            return set()
        return out

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
        except Exception:
            return

    def _parse_tr_float(self, txt: str) -> float:
        s = str(txt or "").strip()
        if not s:
            return 0.0
        s = s.replace("₺", "")
        s = s.replace("TL", "")
        s = s.replace(" ", "")
        s = s.replace(".", "")
        s = s.replace(",", ".")
        try:
            return float(s)
        except Exception:
            return 0.0

    def _row_day_qty_sum(self, r: int) -> int:
        total = 0
        try:
            for day_col in range(self._day_start, self._day_start + self.days_in_month):
                it = self.table.item(int(r), int(day_col))
                v = (it.text() or "").strip() if it is not None else ""
                if v.isdigit():
                    total += int(v)
        except Exception:
            return 0
        return int(total)

    def _row_total_price(self, r: int) -> float:
        try:
            it_tp = self.table.item(int(r), int(self._col_total_price))
            tp_txt = (it_tp.text() or "").strip() if it_tp is not None else ""
            return float(self._parse_tr_float(tp_txt))
        except Exception:
            return 0.0

    def _row_has_any_override(self, r: int) -> bool:
        try:
            meta = self._row_meta[int(r)] if int(r) < len(self._row_meta) else None
            rid_i = int((meta or {}).get("route_params_id") or 0)
            tb_s = str((meta or {}).get("time_block") or "").strip()
            ln_i = int((meta or {}).get("line_no") or 0)
        except Exception:
            rid_i, tb_s, ln_i = 0, "", 0

        if rid_i <= 0 or (not tb_s):
            return False
        try:
            for day in range(1, self.days_in_month + 1):
                trip_date = QDate(self.year, self.month, day).toString("yyyy-MM-dd")
                k0 = (int(rid_i), str(tb_s), str(trip_date), int(ln_i))
                rec0 = (self._alloc_override_map or {}).get(k0) or {}
                # For empty-row UX, only treat explicit notes as "meaningful" overrides.
                # Vehicle/driver deviations can be operational and should not prevent row from being considered empty.
                if bool((rec0.get("note") or "").strip()):
                    return True
        except Exception:
            return False
        return False

    def _row_is_empty_for_user(self, r: int) -> bool:
        # Empty means: no entered qty on any day AND total price is 0 AND no overrides.
        try:
            if self._row_day_qty_sum(int(r)) > 0:
                return False
            if self._row_total_price(int(r)) > 0.0:
                return False
            if self._row_has_any_override(int(r)):
                return False
        except Exception:
            return False
        return True

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

    def _manual_row_indexes(self) -> list[int]:
        out: list[int] = []
        try:
            for r in range(self.table.rowCount()):
                meta = self._row_meta[r] if r < len(self._row_meta) else None
                try:
                    rid_i = int((meta or {}).get("route_params_id") or 0)
                except Exception:
                    rid_i = 0
                if int(rid_i or 0) <= 0:
                    out.append(int(r))
        except Exception:
            return []
        return out

    def _init_manual_row(self, row: int):
        try:
            self.table.setRowHeight(int(row), 25)
        except Exception:
            pass

        sno = QTableWidgetItem("")
        sno.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        sno.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(int(row), 0, sno)

        r_item = QTableWidgetItem("")
        r_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
        r_item.setData(Qt.ItemDataRole.UserRole, None)
        self.table.setItem(int(row), 1, r_item)

        s_item = QTableWidgetItem("")
        s_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.table.setItem(int(row), int(self._col_stops), s_item)

        v_item = QTableWidgetItem("")
        v_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
        v_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        v_item.setData(Qt.ItemDataRole.UserRole, None)
        self.table.setItem(int(row), int(self._col_vehicle), v_item)

        d_item = QTableWidgetItem("")
        d_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
        d_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        d_item.setData(Qt.ItemDataRole.UserRole, None)
        self.table.setItem(int(row), int(self._col_driver), d_item)

        mt_item = QTableWidgetItem("")
        mt_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
        mt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(int(row), int(self._col_movement), mt_item)

        t_item = QTableWidgetItem("")
        t_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
        t_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(int(row), int(self._col_time_text), t_item)

        for day in range(1, int(self.max_days) + 1):
            col = int(self._day_start) + (int(day) - 1)
            it_day = QTableWidgetItem("")
            it_day.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_day.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(int(row), int(col), it_day)
            if int(day) <= int(self.days_in_month):
                try:
                    self._apply_day_cell_style(int(row), int(col))
                except Exception:
                    pass

        total_item = QTableWidgetItem("0")
        total_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        total_item.setBackground(QColor("#dfe6e9"))
        self.table.setItem(int(row), int(self._col_total_qty), total_item)

        price_item = QTableWidgetItem("0")
        price_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
        price_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        try:
            price_item.setData(Qt.ItemDataRole.UserRole, float(0.0))
        except Exception:
            pass
        self.table.setItem(int(row), int(self._col_price), price_item)

        total_price_item = QTableWidgetItem("0")
        total_price_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        total_price_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        total_price_item.setBackground(QColor("#dfe6e9"))
        self.table.setItem(int(row), int(self._col_total_price), total_price_item)

        # meta
        while int(row) >= len(self._row_meta):
            self._row_meta.append({})
        self._row_meta[int(row)] = {
            "route_params_id": 0,
            "sub_index": 0,
            "line_no": 0,
            "time_block": "MANUAL",
            "plan_time_block": "",
            "is_manual": True,
        }

    def _add_manual_row(self):
        try:
            cur = len(self._manual_row_indexes())
        except Exception:
            cur = 0
        if int(cur) >= int(getattr(self, "_max_manual_rows", 5)):
            QMessageBox.information(self, "Bilgi", f"En fazla {int(self._max_manual_rows)} manuel satır ekleyebilirsiniz.")
            return

        try:
            self.table.blockSignals(True)
        except Exception:
            pass
        try:
            row = int(self.table.rowCount())
            self.table.insertRow(int(row))
            self._init_manual_row(int(row))
        finally:
            try:
                self.table.blockSignals(False)
            except Exception:
                pass
        self._apply_route_group_spans()

    def _delete_selected_manual_row(self):
        r = -1
        try:
            it = self.table.currentItem()
            if it is not None:
                r = int(it.row())
        except Exception:
            r = -1
        if r < 0 or r >= self.table.rowCount():
            return

        meta = self._row_meta[r] if r < len(self._row_meta) else None
        try:
            rid_i = int((meta or {}).get("route_params_id") or 0)
        except Exception:
            rid_i = 0
        if int(rid_i or 0) > 0:
            QMessageBox.information(self, "Bilgi", "Sadece manuel satırlar silinebilir.")
            return

        soru = QMessageBox.question(
            self,
            "Onay",
            "Seçili manuel satır silinsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if soru != QMessageBox.StandardButton.Yes:
            return

        try:
            self.table.blockSignals(True)
        except Exception:
            pass
        try:
            self.table.removeRow(int(r))
            if int(r) < len(self._row_meta):
                try:
                    self._row_meta.pop(int(r))
                except Exception:
                    pass
        finally:
            try:
                self.table.blockSignals(False)
            except Exception:
                pass
        self._apply_route_group_spans()

    def _load_manual_rows(self):
        try:
            rows = self.db.get_bulk_puantaj_manual_rows(int(self.contract_id), str(self.month_key), str(self.service_type))
        except Exception:
            rows = []

        if not rows:
            return

        try:
            self.table.blockSignals(True)
        except Exception:
            pass
        try:
            for sort_order, guz, vehicle_id, driver_id, movement_type, time_text, unit_price, day_qty_json in rows or []:
                row = int(self.table.rowCount())
                self.table.insertRow(int(row))
                self._init_manual_row(int(row))

                it_route = self.table.item(int(row), 1)
                if it_route is not None:
                    it_route.setText(str(guz or ""))
                    it_route.setData(Qt.ItemDataRole.UserRole, None)

                it_mt = self.table.item(int(row), int(self._col_movement))
                if it_mt is not None:
                    it_mt.setText(str(movement_type or "").strip().upper())

                it_tt = self.table.item(int(row), int(self._col_time_text))
                if it_tt is not None:
                    it_tt.setText(str(time_text or ""))

                # vehicle/driver labels (if known id) otherwise raw text
                itv = self.table.item(int(row), int(self._col_vehicle))
                if itv is not None and vehicle_id is not None and str(vehicle_id).strip():
                    rec = (self._vehicle_map or {}).get(str(vehicle_id))
                    if rec is not None:
                        try:
                            plate, cap = rec
                        except Exception:
                            plate, cap = str(rec), 0
                        label_v = f"{plate} ({int(cap)})" if int(cap or 0) > 0 else str(plate)
                        itv.setText(str(label_v))
                        itv.setData(Qt.ItemDataRole.UserRole, str(vehicle_id))
                    else:
                        itv.setText(str(vehicle_id))
                        itv.setData(Qt.ItemDataRole.UserRole, None)

                itd = self.table.item(int(row), int(self._col_driver))
                if itd is not None and driver_id is not None and str(driver_id).strip():
                    nm = (self._driver_map or {}).get(str(driver_id))
                    if nm is not None:
                        itd.setText(str(nm))
                        itd.setData(Qt.ItemDataRole.UserRole, str(driver_id))
                    else:
                        itd.setText(str(driver_id))
                        itd.setData(Qt.ItemDataRole.UserRole, None)

                # day qty
                day_map = {}
                try:
                    day_map = json.loads(day_qty_json) if str(day_qty_json or "").strip() else {}
                except Exception:
                    day_map = {}
                if not isinstance(day_map, dict):
                    day_map = {}
                for k, v in (day_map or {}).items():
                    try:
                        day = int(k)
                        qty = int(v)
                    except Exception:
                        continue
                    if day < 1 or day > int(self.days_in_month):
                        continue
                    col = int(self._day_start) + (day - 1)
                    it_day = self.table.item(int(row), int(col))
                    if it_day is not None:
                        it_day.setText(str(qty) if int(qty) > 0 else "")
                        try:
                            self._apply_day_cell_style(int(row), int(col))
                        except Exception:
                            pass

                # price
                itp = self.table.item(int(row), int(self._col_price))
                if itp is not None:
                    try:
                        pf = float(unit_price or 0.0)
                    except Exception:
                        pf = 0.0
                    itp.setText(self._format_tr_currency(pf))
                    try:
                        itp.setData(Qt.ItemDataRole.UserRole, float(pf))
                    except Exception:
                        pass

                # totals
                try:
                    total = int(self._row_day_qty_sum(int(row)))
                    t_item = self.table.item(int(row), int(self._col_total_qty))
                    if t_item is not None:
                        t_item.setText(str(total))
                except Exception:
                    pass
                try:
                    self._recalc_price_total_for_row(int(row))
                except Exception:
                    pass
        finally:
            try:
                self.table.blockSignals(False)
            except Exception:
                pass


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

            # Manual rows (route_params_id <= 0) should never be merged/spanned.
            # Treat them as a one-line group.
            if int(rid0 or 0) <= 0:
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
                r += 1
                continue

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
        # Normalize dash variants (en-dash/em-dash/minus) to '-' so planned labels are detected consistently.
        t = self._norm_dash_text(t)
        if "-" not in t:
            return False
        parts = [p.strip() for p in t.split("-", 1)]
        if len(parts) != 2:
            return False
        a, b = parts
        if not a or not b:
            return False
        try:
            return (re.match(r"^\d{2}:\d{2}$", a) is not None) and (re.match(r"^\d{2}:\d{2}$", b) is not None)
        except Exception:
            return False

    def _norm_dash_text(self, s: str) -> str:
        try:
            t = str(s or "")
            # common dash/minus variants
            t = t.replace("–", "-").replace("—", "-").replace("−", "-")
            # non-breaking hyphen
            t = t.replace("‑", "-")
            # normalize whitespace
            t = t.replace("\u00A0", " ")
            # zero width characters sometimes sneak into copied/pasted text
            t = t.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
            return t
        except Exception:
            return str(s or "")

    def _is_planned_time_label(self, txt: str) -> bool:
        """Return True if txt looks like a planned time range label (contains 2 times)."""
        try:
            t = self._norm_dash_text(str(txt or "")).strip()
            if not t:
                return False
            # If the text contains two time patterns (HH:MM or HH.MM), treat it as planned label.
            # Avoid word-boundary checks because UI text may contain invisible separators.
            times = re.findall(r"\d{1,2}\s*[:\.]\s*\d{2}", t)
            return len(times) >= 2
        except Exception:
            return False

    def _norm_tr_text(self, s: str) -> str:
        """Normalize Turkish text for robust comparisons (e.g. CİFT -> cift).

        We remove combining marks introduced by dotted I lowercasing and unify diacritics.
        """
        try:
            t = str(s or "")
            t = unicodedata.normalize("NFKD", t)
            t = "".join(ch for ch in t if not unicodedata.combining(ch))
            return t.casefold().strip()
        except Exception:
            return str(s or "").strip().lower()

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

        # Do not allow re-splitting: if this row is already a split row (line_no>0)
        # or if the same (route_params_id,time_block) already has any split rows.
        try:
            cur_ln = int((meta or {}).get("line_no") or 0)
        except Exception:
            cur_ln = 0
        tb_cur = str((meta or {}).get("time_block") or "").strip()
        if cur_ln > 0:
            QMessageBox.information(self, "Bilgi", "Bu satır zaten bölünmüş (split) bir satır. Tekrar ayıramazsınız.")
            return
        try:
            if rid > 0 and tb_cur:
                for m in (self._row_meta or []):
                    try:
                        if int((m or {}).get("route_params_id") or 0) != int(rid):
                            continue
                        if str((m or {}).get("time_block") or "").strip() != tb_cur:
                            continue
                        if int((m or {}).get("line_no") or 0) > 0:
                            QMessageBox.information(self, "Bilgi", "Bu satır daha önce split edilerek bölünmüş. Aynı satırı tekrar ayıramazsınız.")
                            return
                    except Exception:
                        continue
        except Exception:
            pass

        # Prefer the movement type shown in the UI row; it is the most reliable indicator for this row.
        is_cift = False
        try:
            mt_item = self.table.item(int(row), self._col_movement)
            mt_txt = self._norm_tr_text(mt_item.text() if mt_item is not None else "")
            is_cift = ("cift" in mt_txt)
        except Exception:
            is_cift = False

        if not is_cift:
            mt = self._norm_tr_text(self._movement_type_for_route(rid) or "")
            is_cift = ("cift" in mt)
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
                it = self.table.item(row, c)
                if it is None:
                    continue
                nit = QTableWidgetItem(it.text())
                nit.setTextAlignment(it.textAlignment())
                nit.setFlags(it.flags())
                try:
                    nit.setData(Qt.ItemDataRole.UserRole, it.data(Qt.ItemDataRole.UserRole))
                except Exception:
                    pass
                try:
                    nit.setBackground(it.background())
                except Exception:
                    pass
                self.table.setItem(insert_at, c, nit)

            if row < len(self._row_meta):
                base_meta = dict(self._row_meta[row] or {})
                try:
                    base_ln = int(base_meta.get("line_no") or 0)
                except Exception:
                    base_ln = 0

                # Ensure base row has a stable line_no
                base_meta["line_no"] = int(base_ln)

                # New split row gets next available line_no for same (rid,time_block)
                try:
                    rid0 = int(base_meta.get("route_params_id") or 0)
                except Exception:
                    rid0 = 0
                tb0 = str(base_meta.get("time_block") or "").strip()
                max_ln = 0
                for m in (self._row_meta or []):
                    try:
                        if int((m or {}).get("route_params_id") or 0) != rid0:
                            continue
                        if str((m or {}).get("time_block") or "").strip() != tb0:
                            continue
                        max_ln = max(max_ln, int((m or {}).get("line_no") or 0))
                    except Exception:
                        continue
                new_meta = dict(base_meta)
                new_meta["line_no"] = int(max_ln + 1)

                # Update base meta in-place and insert new meta
                self._row_meta[row] = dict(base_meta)
                self._row_meta.insert(insert_at, new_meta)

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

            # Split model (yarım iş): keep qty as-is; halve unit price on both rows.
            try:
                p_it = self.table.item(row, self._col_price)
                if p_it is not None:
                    # Persist full unit price in UserRole to avoid repeated halving on reload/split.
                    try:
                        p_full = p_it.data(Qt.ItemDataRole.UserRole)
                    except Exception:
                        p_full = None
                    if p_full is None or (isinstance(p_full, str) and not str(p_full).strip()):
                        p_full = self._parse_tr_float(p_it.text() or "0")
                    try:
                        p_full_f = float(p_full or 0.0)
                    except Exception:
                        p_full_f = 0.0

                    half = p_full_f / 2.0
                    p_it.setData(Qt.ItemDataRole.UserRole, float(p_full_f))
                    p_it.setText(self._format_tr_currency(half))
                    p2 = self.table.item(insert_at, self._col_price)
                    if p2 is not None:
                        p2.setData(Qt.ItemDataRole.UserRole, float(p_full_f))
                        p2.setText(self._format_tr_currency(half))
            except Exception:
                pass

            try:
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

                total = max(int(v0), int(v1))
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

            # Price: restore full unit price from two half rows.
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
            if float(p0) > 0 and float(p1) > 0:
                p_full = float(p0) + float(p1)
            else:
                p_full = 2.0 * max(float(p0), float(p1))
            p_it0.setText(self._format_tr_currency(p_full))

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
            rec.get("movement_type_norm")
            or rec.get("pricing_category")
            or rec.get("gidis_gelis")
            or rec.get("movement_type")
            or rec.get("hareket_turu")
            or rec.get("hareket")
            or rec.get("hareketTuru")
            or rec.get("hareket_tipi")
            or rec.get("tip")
            or ""
        )
        s = str(raw or "").strip().lower()
        if "mesai" in s:
            return "fazla mesai"
        if "paket" in s or (("sabah" in s) and ("akşam" in s or "aksam" in s)):
            return "sabah-akşam"
        if "cift" in s or "çift" in s:
            return "tek servis"
        if "tek" in s:
            return "tek servis"
        if s == "teks" or s == "tekservis":
            return "tek servis"
        return s

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
        try:
            self.table.setProperty("no_zebra", True)
        except Exception:
            pass
        self.table.setAlternatingRowColors(False)

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
            "HAREKET\nTÜRÜ",
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
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        day_start = 7
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
            self.table.setColumnWidth(3, 90)
            self.table.setColumnWidth(4, 95)
            self.table.setColumnWidth(5, 80)
            self.table.setColumnWidth(6, 120)
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
        self._col_movement = 5
        self._col_time_text = 6
        self._col_stops = 2

        try:
            h.setSectionResizeMode(self._col_driver, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(self._col_driver, 95)
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

        self._bg_weekend = QColor("#cfcfcf")
        self._bg_holiday = QColor("#cfcfcf")
        self._bg_qty = QColor("#fff3cd")
        self._bg_override = QColor("#f8c291")

        self._official_holidays = self._official_holiday_set(int(self.year))

        self._max_manual_rows = 5

        try:
            for d in range(1, int(self.days_in_month) + 1):
                col = int(self._day_start) + (int(d) - 1)
                it_h = self.table.horizontalHeaderItem(col)
                if it_h is None:
                    continue
                if self._is_holiday_day(int(d)) or self._is_weekend_day(int(d)):
                    it_h.setBackground(self._bg_weekend)
        except Exception:
            pass

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
            return _tb_sort_key_0700(tb_val)

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

            plan_tb = (str(plan_time_block).strip() if plan_time_block is not None else "")
            if not plan_tb:
                plan_tb = str(time_block or "").strip()

            try:
                self.table.setRowHeight(row, 25)
            except Exception:
                pass

            sno = QTableWidgetItem(str(row + 1))
            sno.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            sno.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, sno)

            stops_txt = ""
            movement_type = ""
            try:
                for rr in self._route_rows:
                    if int(rr[0] or 0) == int(route_params_id):
                        stops_txt = str(rr[2] or "") if len(rr) > 2 else ""
                        # get_route_params_for_contract may return different shapes.
                        # Prefer movement_type column if present; fall back to older positions.
                        if len(rr) > 4:
                            movement_type = str(rr[4] or "")
                        elif len(rr) > 3 and isinstance(rr[3], str):
                            movement_type = str(rr[3] or "")
                        break
            except Exception:
                stops_txt = ""
                movement_type = ""

            parts = [p for p in [str(route_name or "").strip(), str(stops_txt).strip()] if str(p).strip()]
            r_item = QTableWidgetItem(" | ".join(parts))
            r_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            r_item.setData(Qt.ItemDataRole.UserRole, int(route_params_id))
            self.table.setItem(row, 1, r_item)
            s_item = QTableWidgetItem(stops_txt)
            s_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(row, self._col_stops, s_item)

            mt_item = QTableWidgetItem(str(movement_type or "").strip())
            mt_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            mt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, self._col_movement, mt_item)

            t_item = QTableWidgetItem(str(label or "").strip())
            t_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
            t_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, self._col_time_text, t_item)

            for day in range(1, self.max_days + 1):
                col = self._day_start + (day - 1)
                it_day = QTableWidgetItem("")
                it_day.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                it_day.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsEditable
                )
                self.table.setItem(row, col, it_day)
                if day <= self.days_in_month:
                    self._apply_day_cell_style(row, col)

            v_item = QTableWidgetItem("")
            v_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            v_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            v_item.setData(Qt.ItemDataRole.UserRole, None)
            self.table.setItem(row, self._col_vehicle, v_item)

            d_item = QTableWidgetItem("")
            d_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            d_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            d_item.setData(Qt.ItemDataRole.UserRole, None)
            self.table.setItem(row, self._col_driver, d_item)

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
                    "line_no": 0,
                    "time_block": str(time_block),
                    "plan_time_block": str(plan_tb),
                }
            )
        self.table.setRowCount(0)

        start_date = QDate(self.year, self.month, 1).toString("yyyy-MM-dd")
        end_date = QDate(self.year, self.month, self.days_in_month).toString("yyyy-MM-dd")
        try:
            self._planned_keys = _planned_keys_for_context(int(self.contract_id), self.month_key, str(self.service_type))
        except Exception:
            self._planned_keys = set()

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

        self.btn_add_manual = QPushButton("MANUEL SATIR EKLE", self)
        self.btn_add_manual.clicked.connect(self._add_manual_row)

        self.btn_del_manual = QPushButton("MANUEL SATIR SİL", self)
        self.btn_del_manual.clicked.connect(self._delete_selected_manual_row)

        try:
            self.btn_save.setFixedSize(140, 30)
        except Exception:
            pass

        lay = QVBoxLayout()
        lay.addWidget(self.table)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_add_manual)
        btn_row.addWidget(self.btn_del_manual)
        btn_row.addWidget(self.btn_save)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)
        self.setLayout(lay)

        self._load_existing_entries()

        try:
            self._load_manual_rows()
        except Exception:
            pass

        self._apply_route_group_spans()

        self.table.itemChanged.connect(self._recalc_row_total)

        try:
            QTimer.singleShot(0, self._enforce_bulk_column_widths)
            QTimer.singleShot(50, self._enforce_bulk_column_widths)
            QTimer.singleShot(250, self._enforce_bulk_column_widths)
        except Exception:
            pass

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

    def _is_holiday_day(self, day_num: int) -> bool:
        try:
            qd = QDate(self.year, self.month, int(day_num))
            if not qd.isValid():
                return False
            return qd.toString("yyyy-MM-dd") in (self._official_holidays or set())
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

        try:
            line_no = int((meta or {}).get("line_no") or 0)
        except Exception:
            line_no = 0
        trip_date = QDate(self.year, self.month, day_num).toString("yyyy-MM-dd")
        return int(route_params_id), str(time_block), str(trip_date), int(line_no)

    def _apply_day_cell_style(self, row: int, col: int):
        # Prevent recursion if style changes trigger itemChanged
        if bool(getattr(self, "_in_apply_day_cell_style", False)):
            return
        setattr(self, "_in_apply_day_cell_style", True)
        try:
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
                # Only highlight explicit user override notes.
                # Vehicle/driver deviations can be legitimate operational changes and were confusing in UI.
                has_override = bool((rec.get("note") or "").strip())

            txt = (it.text() or "").strip()
            has_qty = bool(txt.isdigit() and int(txt) > 0)

            def _set_bg(color: QColor):
                try:
                    with QSignalBlocker(self.table):
                        try:
                            it.setData(Qt.ItemDataRole.BackgroundRole, color)
                        except Exception:
                            pass
                        try:
                            it.setBackground(color)
                        except Exception:
                            pass
                except Exception:
                    try:
                        it.setData(Qt.ItemDataRole.BackgroundRole, color)
                    except Exception:
                        pass
                    try:
                        it.setBackground(color)
                    except Exception:
                        pass

            # Override note highlight should be visible even on weekends/holidays.
            if has_qty and has_override:
                _set_bg(self._bg_override)
                return
            if self._is_holiday_day(day_num) or self._is_weekend_day(day_num):
                _set_bg(self._bg_weekend)
                return
            if has_qty:
                _set_bg(self._bg_qty)
                return
            _set_bg(QColor("#ffffff"))

        finally:
            setattr(self, "_in_apply_day_cell_style", False)

    def _enforce_bulk_column_widths(self):
        try:
            h = self.table.horizontalHeader()
        except Exception:
            return

        try:
            h.setStretchLastSection(False)
        except Exception:
            pass

        try:
            h.setCascadingSectionResizes(False)
        except Exception:
            pass

        try:
            h.setSectionResizeMode(int(self._col_vehicle), QHeaderView.ResizeMode.Fixed)
            h.setSectionResizeMode(int(self._col_driver), QHeaderView.ResizeMode.Fixed)
            h.setSectionResizeMode(int(self._col_movement), QHeaderView.ResizeMode.Fixed)
        except Exception:
            pass

        try:
            self.table.setColumnWidth(int(self._col_vehicle), 90)
            self.table.setColumnWidth(int(self._col_driver), 95)
            self.table.setColumnWidth(int(self._col_movement), 80)
        except Exception:
            pass

        try:
            # Force via header too (some styles/layout passes can ignore setColumnWidth)
            h.resizeSection(int(self._col_vehicle), 90)
            h.resizeSection(int(self._col_driver), 95)
            h.resizeSection(int(self._col_movement), 80)
        except Exception:
            pass

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

        if c == self._col_movement:
            menu = QMenu(self)
            act_clear = menu.addAction("Hareket Türü Temizle")
            menu.addSeparator()
            act_tek = menu.addAction("TEK")
            act_cift = menu.addAction("ÇİFT")
            act_paket = menu.addAction("PAKET")
            act_mesai = menu.addAction("MESAİ")
            chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
            if chosen is None:
                return
            itx = self.table.item(r, self._col_movement)
            if itx is None:
                itx = QTableWidgetItem("")
                itx.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                itx.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, self._col_movement, itx)
            if chosen == act_clear:
                itx.setText("")
                return
            if chosen == act_tek:
                itx.setText("TEK")
            elif chosen == act_cift:
                itx.setText("ÇİFT")
            elif chosen == act_paket:
                itx.setText("PAKET")
            elif chosen == act_mesai:
                itx.setText("MESAİ")
            return

        if c in (self._col_vehicle, self._col_driver):
            menu = QMenu(self)
            if c == self._col_vehicle:
                act_clear = menu.addAction("Araç Temizle")
                menu.addSeparator()
                actions = []
                for vcode, rec in (self._vehicle_map or {}).items():
                    try:
                        plate, cap = rec
                    except Exception:
                        plate, cap = str(rec), 0
                    label_v = f"{plate} ({int(cap)})" if int(cap or 0) > 0 else str(plate)
                    a = menu.addAction(label_v)
                    a.setData(str(vcode))
                    actions.append(a)
                chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
                if chosen is None:
                    return
                itx = self.table.item(r, self._col_vehicle)
                if itx is None:
                    itx = QTableWidgetItem("")
                    itx.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    itx.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.table.setItem(r, self._col_vehicle, itx)
                if chosen == act_clear:
                    itx.setText("")
                    itx.setData(Qt.ItemDataRole.UserRole, None)
                    return
                v_id = str(chosen.data() or "")
                rec = (self._vehicle_map or {}).get(v_id)
                if rec is None:
                    return
                try:
                    plate, cap = rec
                except Exception:
                    plate, cap = str(rec), 0
                label_v = f"{plate} ({int(cap)})" if int(cap or 0) > 0 else str(plate)
                itx.setText(str(label_v))
                itx.setData(Qt.ItemDataRole.UserRole, v_id)
                return

            act_clear = menu.addAction("Şoför Temizle")
            menu.addSeparator()
            for did, name in (self._driver_map or {}).items():
                a = menu.addAction(str(name))
                a.setData(str(did))
            chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
            if chosen is None:
                return
            itx = self.table.item(r, self._col_driver)
            if itx is None:
                itx = QTableWidgetItem("")
                itx.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                itx.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r, self._col_driver, itx)
            if chosen == act_clear:
                itx.setText("")
                itx.setData(Qt.ItemDataRole.UserRole, None)
                return
            d_id = str(chosen.data() or "")
            nm = (self._driver_map or {}).get(d_id)
            if nm is None:
                return
            itx.setText(str(nm))
            itx.setData(Qt.ItemDataRole.UserRole, d_id)
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

        try:
            line_no = int((meta or {}).get("line_no") or 0)
        except Exception:
            line_no = 0

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
        key = (int(route_params_id), str(time_block), str(first_trip_date), int(line_no))

        default_vehicle_id = None
        default_driver_id = None
        itv0 = self.table.item(r, self._col_vehicle)
        itd0 = self.table.item(r, self._col_driver)
        if itv0 is not None:
            default_vehicle_id = itv0.data(Qt.ItemDataRole.UserRole)
        if itd0 is not None:
            default_driver_id = itd0.data(Qt.ItemDataRole.UserRole)

        current = self._alloc_override_map.get(key) or {}
        cur_vehicle_id = current.get("vehicle_id")
        cur_driver_id = current.get("driver_id")
        cur_note = current.get("note") or ""

        ceza_flag = "__CEZA_HATIRLAT__"

        def _note_has_flag(s: str) -> bool:
            return ceza_flag in (s or "")

        def _note_strip_flag(s: str) -> str:
            txt = (s or "")
            if ceza_flag not in txt:
                return txt.strip()
            out = txt.replace(ceza_flag, "")
            out = " ".join(out.split())
            return out.strip()

        def _note_apply_flag(s: str, enabled: bool) -> str:
            base = _note_strip_flag(s)
            if not enabled:
                return base
            if base:
                return f"{base} {ceza_flag}".strip()
            return ceza_flag

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
        txt_note.setText(str(_note_strip_flag(str(cur_note))))
        row3.addWidget(txt_note)
        lay.addLayout(row3)

        row4 = QHBoxLayout()
        chk_ceza = QCheckBox("Taşeron ceza hatırlat")
        try:
            chk_ceza.setChecked(bool(_note_has_flag(str(cur_note))))
        except Exception:
            pass
        row4.addWidget(chk_ceza)
        row4.addStretch(1)
        lay.addLayout(row4)

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
                    k = (int(route_params_id), str(time_block), str(trip_date), int(line_no))
                    if k in self._alloc_override_map:
                        del self._alloc_override_map[k]
                for cc in selected_cols:
                    self._mark_day_override_cell(r, cc, None)

                # Persist clear to DB immediately so reminders do not re-appear after reload
                try:
                    for trip_date in selected_dates:
                        try:
                            qd = QDate.fromString(str(trip_date), "yyyy-MM-dd")
                            day_num = int(qd.day()) if qd.isValid() else None
                        except Exception:
                            day_num = None
                        qty = 0
                        if day_num is not None:
                            col = self._day_start + (int(day_num) - 1)
                            itq = self.table.item(r, col)
                            txtq = (itq.text() or "").strip() if itq is not None else ""
                            qty = int(txtq) if txtq.isdigit() else 0
                        try:
                            conflict = self.db.find_allocation_conflict(
                                contract_id=int(self.contract_id),
                                route_params_id=int(route_params_id),
                                trip_date=str(trip_date),
                                service_type=str(self.service_type),
                                time_block=str(time_block),
                                line_no=int(line_no),
                                vehicle_id=default_vehicle_id,
                                driver_id=default_driver_id,
                                qty=float(qty),
                                time_text=str((self.table.item(r, self._col_time_text).text() if self.table.item(r, self._col_time_text) else "") or ""),
                                note="",
                            )
                        except Exception:
                            conflict = None
                        if conflict:
                            QMessageBox.critical(self, "Çakışma", "Aynı gün içinde araç/şoför saat çakışması olduğu için kayıt yapılamadı.")
                            return
                        self.db.upsert_trip_allocation(
                            contract_id=int(self.contract_id),
                            route_params_id=int(route_params_id),
                            trip_date=str(trip_date),
                            service_type=str(self.service_type),
                            time_block=str(time_block),
                            vehicle_id=default_vehicle_id,
                            driver_id=default_driver_id,
                            qty=float(qty),
                            time_text=str((self.table.item(r, self._col_time_text).text() if self.table.item(r, self._col_time_text) else "") or ""),
                            note="",
                            line_no=int(line_no),
                        )
                        try:
                            if default_vehicle_id is not None and str(default_vehicle_id).strip():
                                mv = int(self.db.get_vehicle_movements_for_day(int(self.contract_id), str(trip_date), default_vehicle_id) or 0)
                                if mv > 8:
                                    QMessageBox.warning(self, "Uyarı", f"Bu araç için {trip_date} tarihinde hareket sayısı {mv} oldu (limit: 8).")
                        except Exception:
                            pass
                except Exception:
                    pass

                dlg.accept()
                return

            vsel = cmb_v2.currentData()
            dsel = cmb_d2.currentData()
            note_ui = (txt_note.text() or "").strip()
            note = _note_apply_flag(note_ui, bool(chk_ceza.isChecked()))

            if vsel == "__DEFAULT__":
                vsel = default_vehicle_id
            if dsel == "__DEFAULT__":
                dsel = default_driver_id

            if (not vsel) and (not dsel) and (not note_ui) and (not chk_ceza.isChecked()):
                for trip_date in selected_dates:
                    k = (int(route_params_id), str(time_block), str(trip_date), int(line_no))
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
                self._alloc_override_map[(int(route_params_id), str(time_block), str(trip_date), int(line_no))] = {
                    "vehicle_id": vsel,
                    "driver_id": dsel,
                    "note": note,
                    "is_override": bool(is_override),
                }
            for cc in selected_cols:
                self._mark_day_override_cell(r, cc, note_ui)

            # Persist immediately to DB so module reload + hakediş reminder works without requiring main KAYDET.
            try:
                for trip_date in selected_dates:
                    try:
                        qd = QDate.fromString(str(trip_date), "yyyy-MM-dd")
                        day_num = int(qd.day()) if qd.isValid() else None
                    except Exception:
                        day_num = None
                    qty = 0
                    if day_num is not None:
                        col = self._day_start + (int(day_num) - 1)
                        itq = self.table.item(r, col)
                        txtq = (itq.text() or "").strip() if itq is not None else ""
                        qty = int(txtq) if txtq.isdigit() else 0
                    try:
                        conflict = self.db.find_allocation_conflict(
                            contract_id=int(self.contract_id),
                            route_params_id=int(route_params_id),
                            trip_date=str(trip_date),
                            service_type=str(self.service_type),
                            time_block=str(time_block),
                            line_no=int(line_no),
                            vehicle_id=vsel,
                            driver_id=dsel,
                            qty=float(qty),
                            time_text=str((self.table.item(r, self._col_time_text).text() if self.table.item(r, self._col_time_text) else "") or ""),
                            note=str(note),
                        )
                    except Exception:
                        conflict = None
                    if conflict:
                        QMessageBox.critical(self, "Çakışma", "Aynı gün içinde araç/şoför saat çakışması olduğu için kayıt yapılamadı.")
                        return
                    self.db.upsert_trip_allocation(
                        contract_id=int(self.contract_id),
                        route_params_id=int(route_params_id),
                        trip_date=str(trip_date),
                        service_type=str(self.service_type),
                        time_block=str(time_block),
                        vehicle_id=vsel,
                        driver_id=dsel,
                        qty=float(qty),
                        time_text=str((self.table.item(r, self._col_time_text).text() if self.table.item(r, self._col_time_text) else "") or ""),
                        note=str(note),
                        line_no=int(line_no),
                    )
                    try:
                        if vsel is not None and str(vsel).strip():
                            mv = int(self.db.get_vehicle_movements_for_day(int(self.contract_id), str(trip_date), vsel) or 0)
                            if mv > 8:
                                QMessageBox.warning(self, "Uyarı", f"Bu araç için {trip_date} tarihinde hareket sayısı {mv} oldu (limit: 8).")
                    except Exception:
                        pass
            except Exception:
                pass

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

        # Prevent recursion if itemChanged is triggered from within this handler
        if bool(getattr(self, "_in_recalc_row_total", False)):
            return
        setattr(self, "_in_recalc_row_total", True)

        try:
            # Defensive: if any key column indexes are not initialized properly, do nothing.
            # This also prevents accidental recursion when -1 indexes point to last column.
            try:
                if any(int(x) < 0 for x in (self._col_total_qty, self._col_total_price, self._col_price, self._day_start)):
                    return
            except Exception:
                return

            r = item.row()
            c = item.column()
            if c in (0, 1, self._col_vehicle, self._col_driver, self._col_time_text, self._col_total_qty, self._col_total_price):
                return

            if c == self._col_movement:
                # Normalize movement type to the allowed set if user typed it manually.
                try:
                    txtm = (item.text() or "").strip().upper()
                except Exception:
                    txtm = ""
                allowed = {"TEK", "ÇİFT", "PAKET", "MESAİ"}
                if txtm and txtm not in allowed:
                    try:
                        with QSignalBlocker(self.table):
                            item.setText("")
                    except Exception:
                        item.setText("")
                else:
                    try:
                        with QSignalBlocker(self.table):
                            item.setText(txtm)
                    except Exception:
                        item.setText(txtm)
                return

            if c == self._col_price:
                try:
                    txtp = (item.text() or "").strip()
                    self._parse_tr_float(txtp)
                except Exception:
                    return
                try:
                    with QSignalBlocker(self.table):
                        item.setText(self._format_tr_currency(self._parse_tr_float(txtp)))
                except Exception:
                    item.setText(self._format_tr_currency(self._parse_tr_float(txtp)))
                self._recalc_price_total_for_row(r)
                return

            if c < self._day_start or c >= self._day_start + self.max_days:
                return

            day_num = (c - self._day_start) + 1
            if day_num > self.days_in_month:
                try:
                    with QSignalBlocker(self.table):
                        item.setText("")
                except Exception:
                    pass
                return

            txt = (item.text() or "").strip()
            if txt and (not txt.isdigit()):
                try:
                    with QSignalBlocker(self.table):
                        item.setText("")
                except Exception:
                    pass
                try:
                    with QSignalBlocker(self.table):
                        self._apply_day_cell_style(r, c)
                except Exception:
                    self._apply_day_cell_style(r, c)
                return
            if txt and txt.isdigit() and int(txt) < 0:
                try:
                    with QSignalBlocker(self.table):
                        item.setText("")
                except Exception:
                    pass
                try:
                    with QSignalBlocker(self.table):
                        self._apply_day_cell_style(r, c)
                except Exception:
                    self._apply_day_cell_style(r, c)
                return

            total = 0
            for day_col in range(self._day_start, self._day_start + self.days_in_month):
                it = self.table.item(r, day_col)
                if it and (it.text() or "").strip().isdigit():
                    total += int(it.text().strip())
            t_item = self.table.item(r, self._col_total_qty)
            if t_item is not None:
                try:
                    with QSignalBlocker(self.table):
                        t_item.setText(str(total))
                except Exception:
                    t_item.setText(str(total))

            self._recalc_price_total_for_row(r)
            try:
                with QSignalBlocker(self.table):
                    self._apply_day_cell_style(r, c)
            except Exception:
                self._apply_day_cell_style(r, c)

        finally:
            setattr(self, "_in_recalc_row_total", False)

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
                ed.setMaxLength(1)
            except Exception:
                pass
            try:
                ed.setPlaceholderText(str(d))
            except Exception:
                pass
            try:
                txt = (self.table.item(row, self._day_start + (d - 1)).text() or "").strip()
            except Exception:
                txt = ""
            ed.setText(txt)
            day_edits[d] = ed
            grid.addWidget(ed, rr, cc)

        # auto-advance to next day on 1 char
        for d, ed in day_edits.items():
            def _mk_next(_d: int, _ed: QLineEdit):
                def _on_text(_txt: str):
                    t = str(_txt or "")
                    if len(t) >= 1:
                        try:
                            _ed.setText(t[:1])
                        except Exception:
                            pass
                        nd = int(_d) + 1
                        if nd in day_edits:
                            try:
                                day_edits[nd].setFocus()
                                day_edits[nd].selectAll()
                            except Exception:
                                pass
                return _on_text
            try:
                ed.textChanged.connect(_mk_next(int(d), ed))
            except Exception:
                pass

        lay.addLayout(grid)

        btn_row = QHBoxLayout()
        btn_apply = QPushButton("GÜN DEĞERLERİNİ AKTAR")
        btn_cancel = QPushButton("Kapat")
        try:
            btn_apply.setFixedHeight(25)
            btn_cancel.setFixedHeight(25)
        except Exception:
            pass
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

    def refresh_from_db(self):
        try:
            self.table.blockSignals(True)
        except Exception:
            pass

        try:
            for r in range(self.table.rowCount()):
                for day in range(1, self.days_in_month + 1):
                    col = self._day_start + (day - 1)
                    it = self.table.item(r, col)
                    if it is None:
                        continue
                    try:
                        it.setText("")
                    except Exception:
                        pass
                    try:
                        self._apply_day_cell_style(r, col)
                    except Exception:
                        pass

                try:
                    t_item = self.table.item(r, self._col_total_qty)
                    if t_item is not None:
                        t_item.setText("0")
                except Exception:
                    pass

                try:
                    tp_item = self.table.item(r, self._col_total_price)
                    if tp_item is not None:
                        tp_item.setText("0")
                except Exception:
                    pass
        finally:
            try:
                self.table.blockSignals(False)
            except Exception:
                pass

        try:
            self._load_existing_entries()
        except Exception:
            pass

        try:
            self._load_manual_rows()
        except Exception:
            pass

        try:
            self._apply_route_group_spans()
        except Exception:
            pass

    def _recalc_price_total_for_row(self, row: int):
        try:
            if any(int(x) < 0 for x in (self._col_total_qty, self._col_total_price, self._col_price)):
                return
        except Exception:
            return
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
        try:
            with QSignalBlocker(self.table):
                out_item.setText(self._format_tr_currency(total))
        except Exception:
            out_item.setText(self._format_tr_currency(total))
        try:
            out_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        except Exception:
            pass

    def _load_existing_entries(self):
        start_date = QDate(self.year, self.month, 1).toString("yyyy-MM-dd")
        end_date = QDate(self.year, self.month, self.days_in_month).toString("yyyy-MM-dd")

        rows = []
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            # line_no support (fallback to old schema if needed)
            try:
                cursor.execute(
                    """
                    SELECT route_params_id, trip_date, time_block, line_no, qty, COALESCE(time_text,'')
                    FROM trip_entries
                    WHERE contract_id = ?
                      AND service_type = ?
                      AND trip_date BETWEEN ? AND ?
                    ORDER BY route_params_id, time_block, trip_date, line_no
                    """,
                    (int(self.contract_id), str(self.service_type), start_date, end_date),
                )
                rows = cursor.fetchall()
            except Exception:
                cursor.execute(
                    """
                    SELECT route_params_id, trip_date, time_block, 0 as line_no, qty, COALESCE(time_text,'')
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

        # Allocations may contain split line_no rows even when trip_entries rows are missing.
        # Fetch early so we can reconstruct missing split UI rows from either source.
        alloc_rows = []
        try:
            alloc_rows = self.db.get_trip_allocations_for_range(self.contract_id, self.service_type, start_date, end_date)
        except Exception:
            alloc_rows = []

        # If some lines were split (ÇİFT) previously, their records are stored with line_no > 0.
        # The UI table is initially generated from trip_plan and doesn't know about these split rows.
        # Re-create missing split rows here so loaded values don't overwrite each other.
        try:
            needed_lines: dict[tuple[int, str], set[int]] = {}
            for route_params_id, _trip_date, time_block, line_no, _qty, _time_text in rows or []:
                try:
                    rid_i = int(route_params_id or 0)
                except Exception:
                    rid_i = 0
                tb_s = str(time_block or "").strip()
                try:
                    ln_i = int(line_no or 0)
                except Exception:
                    ln_i = 0
                if rid_i <= 0 or not tb_s:
                    continue
                needed_lines.setdefault((rid_i, tb_s), set()).add(int(ln_i))

            # Include line_nos from allocations too (important for split rows).
            for rpid, _trip_date, time_block, line_no, _vehicle_id, _driver_id, _qty0, _ttext0, _note0 in alloc_rows or []:
                try:
                    rid_i = int(rpid or 0)
                except Exception:
                    rid_i = 0
                tb_s = str(time_block or "").strip()
                try:
                    ln_i = int(line_no or 0)
                except Exception:
                    ln_i = 0
                if rid_i <= 0 or not tb_s:
                    continue
                needed_lines.setdefault((rid_i, tb_s), set()).add(int(ln_i))

            def _clone_row(src_row: int, insert_at: int):
                self.table.insertRow(insert_at)

                for c in range(self.table.columnCount()):
                    it = self.table.item(src_row, c)
                    if it is None:
                        continue
                    nit = QTableWidgetItem(it.text())
                    nit.setTextAlignment(it.textAlignment())
                    nit.setFlags(it.flags())
                    try:
                        nit.setBackground(it.background())
                    except Exception:
                        pass
                    try:
                        nit.setData(Qt.ItemDataRole.UserRole, it.data(Qt.ItemDataRole.UserRole))
                    except Exception:
                        pass
                    self.table.setItem(insert_at, c, nit)

            # Ensure all needed line_nos exist in UI
            for (rid_i, tb_s), ln_set in (needed_lines or {}).items():
                if not ln_set:
                    continue
                # Recompute current rows for this key each iteration.
                # Rows can be inserted during this loop, so any precomputed index becomes stale.
                existing_rows: list[int] = []
                for idx, meta in enumerate(self._row_meta or []):
                    try:
                        rid0 = int((meta or {}).get("route_params_id") or 0)
                    except Exception:
                        rid0 = 0
                    tb0 = str((meta or {}).get("time_block") or "").strip()
                    if int(rid0) == int(rid_i) and str(tb0) == str(tb_s):
                        existing_rows.append(int(idx))
                if not existing_rows:
                    continue

                # Existing UI rows might already include some line_no values (during this session).
                existing_ln = set()
                for rr in existing_rows:
                    try:
                        m = self._row_meta[int(rr)] if int(rr) < len(self._row_meta) else None
                        existing_ln.add(int((m or {}).get("line_no") or 0))
                    except Exception:
                        existing_ln.add(0)

                # Prefer base row (line_no=0) as clone source.
                base_row = int(existing_rows[0])
                try:
                    for rr in (existing_rows or []):
                        m0 = self._row_meta[int(rr)] if int(rr) < len(self._row_meta) else None
                        if int((m0 or {}).get("line_no") or 0) == 0:
                            base_row = int(rr)
                            break
                except Exception:
                    base_row = int(existing_rows[0])
                insert_at = base_row + 1

                for ln_i in sorted([int(x) for x in ln_set if int(x) >= 0]):
                    if ln_i in existing_ln:
                        continue

                    _clone_row(base_row, insert_at)

                    base_meta = dict(self._row_meta[base_row] or {}) if base_row < len(self._row_meta) else {}
                    new_meta = dict(base_meta)
                    new_meta["line_no"] = int(ln_i)
                    self._row_meta.insert(insert_at, new_meta)

                    # Split rows (line_no>0) should start with empty time_text unless DB has a value.
                    try:
                        if int(ln_i or 0) > 0:
                            t_it = self.table.item(int(insert_at), self._col_time_text)
                            if t_it is None:
                                t_it = QTableWidgetItem("")
                                self.table.setItem(int(insert_at), self._col_time_text, t_it)
                            t_it.setText("")
                            t_it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
                            try:
                                t_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                            except Exception:
                                pass
                    except Exception:
                        pass

                    insert_at += 1

            try:
                self._apply_route_group_spans()
            except Exception:
                pass
        except Exception:
            pass

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

        # alloc_rows already fetched above (used for split-row reconstruction).

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
                k = (int(rpid or 0), str(tblock or ""))
                v = float(price or 0.0)
                prev = price_map.get(k)
                if prev is None:
                    price_map[k] = v
                else:
                    price_map[k] = max(float(prev or 0.0), float(v or 0.0))
            except Exception:
                k = (int(rpid or 0), str(tblock or ""))
                if k not in price_map:
                    price_map[k] = 0.0

        route_default_price = {}
        for (rpid, _tb), pr in price_map.items():
            if int(rpid or 0) <= 0:
                continue
            try:
                cur = route_default_price.get(int(rpid))
                if cur is None:
                    route_default_price[int(rpid)] = float(pr or 0.0)
                else:
                    route_default_price[int(rpid)] = max(float(cur or 0.0), float(pr or 0.0))
            except Exception:
                if int(rpid) not in route_default_price:
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
                parsed = self.db.parse_contract_price_matrix_rows(str(price_json or ""), service_type=str(self.service_type))
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
                    itv = self.table.item(int(row_idx), self._col_vehicle)
                    itd = self.table.item(int(row_idx), self._col_driver)
                    if itv is not None and str(pv):
                        rec = (self._vehicle_map or {}).get(str(pv))
                        if rec is not None:
                            try:
                                plate, cap = rec
                            except Exception:
                                plate, cap = str(rec), 0
                            label_v = f"{plate} ({int(cap)})" if int(cap or 0) > 0 else str(plate)
                            itv.setText(str(label_v))
                            itv.setData(Qt.ItemDataRole.UserRole, str(pv))
                    if itd is not None and str(pd):
                        nm = (self._driver_map or {}).get(str(pd))
                        if nm is not None:
                            itd.setText(str(nm))
                            itd.setData(Qt.ItemDataRole.UserRole, str(pd))

            self._alloc_override_map = {}
            for rpid, trip_date, time_block, line_no, vehicle_id, driver_id, _qty0, _ttext0, note0 in alloc_rows or []:
                rid_i = int(rpid or 0)
                tb_s = str(time_block or "").strip()
                d_s = str(trip_date or "").strip()
                try:
                    ln_s = int(line_no or 0)
                except Exception:
                    ln_s = 0
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

                self._alloc_override_map[(rid_i, tb_s, d_s, ln_s)] = {
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

                # If this (route_params_id, time_block) has split rows (line_no>0), UI should display half price
                # (yarım iş), while trip_prices remains the full base unit price.
                has_split = False
                try:
                    for rr in (row_idxs or []):
                        mm = self._row_meta[int(rr)] if int(rr) < len(self._row_meta) else None
                        if int((mm or {}).get("line_no") or 0) > 0:
                            has_split = True
                            break
                except Exception:
                    has_split = False
                for row_idx in (row_idxs or []):
                    p_item = self.table.item(int(row_idx), self._col_price)
                    if p_item is not None:
                        is_cift_row = False
                        try:
                            mt_item = self.table.item(int(row_idx), self._col_movement)
                            mt_txt = self._norm_tr_text(mt_item.text() if mt_item is not None else "")
                            is_cift_row = ("cift" in mt_txt)
                        except Exception:
                            is_cift_row = False
                        if not bool(is_cift_row):
                            # Fallback: UI cell text can be empty/changed on reload; infer from route definition.
                            try:
                                mt2 = self._norm_tr_text(self._movement_type_for_route(int(key[0] or 0)) or "")
                                is_cift_row = ("cift" in mt2)
                            except Exception:
                                is_cift_row = False
                        if not bool(is_cift_row):
                            # Last resort: infer from time_text pattern if it looks like a double (entry+exit) label.
                            try:
                                t_it2 = self.table.item(int(row_idx), self._col_time_text)
                                t_txt2 = (t_it2.text() if t_it2 is not None else "")
                                if self._looks_like_double_time_text(t_txt2):
                                    is_cift_row = True
                            except Exception:
                                pass
                        # If DB stored an already-halved price for a split group, UI would show /4.
                        # Use contract/route fallback as the authoritative full unit price.
                        pr_full = float(pr)
                        try:
                            if bool(has_split) and bool(is_cift_row):
                                fb = route_price_by_id.get(int(key[0] or 0))
                                if fb is not None:
                                    try:
                                        pr_full = max(float(pr_full), float(fb))
                                    except Exception:
                                        pr_full = float(pr_full)
                        except Exception:
                            pr_full = float(pr)

                        pr_ui = (float(pr_full) / 2.0) if (has_split and is_cift_row) else float(pr_full)
                        # Store full unit price in UserRole to prevent /4 issues on repeated loads.
                        try:
                            p_item.setData(Qt.ItemDataRole.UserRole, float(pr_full))
                        except Exception:
                            pass
                        p_item.setText(self._format_tr_currency(pr_ui))

            def _row_for_line(rlist0: list[int], ln0: int) -> int | None:
                if not rlist0:
                    return None
                for rr in rlist0:
                    try:
                        mm = self._row_meta[int(rr)] if int(rr) < len(self._row_meta) else None
                        if int((mm or {}).get("line_no") or 0) == int(ln0 or 0):
                            return int(rr)
                    except Exception:
                        continue
                return int(rlist0[0])

            # Row-level allocation defaults (vehicle/driver) from any existing allocation record.
            alloc_row_defaults: dict[tuple[int, str, int], tuple[object, object]] = {}
            try:
                for rpid, _trip_date, tb0, ln0, vehicle_id, driver_id, _qty0, _ttext0, _note0 in alloc_rows or []:
                    try:
                        rid_i = int(rpid or 0)
                    except Exception:
                        rid_i = 0
                    tbs = str(tb0 or "").strip()
                    try:
                        lni = int(ln0 or 0)
                    except Exception:
                        lni = 0
                    if rid_i <= 0 or not tbs:
                        continue
                    if (vehicle_id is None or not str(vehicle_id).strip()) and (driver_id is None or not str(driver_id).strip()):
                        continue
                    alloc_row_defaults[(rid_i, tbs, lni)] = (vehicle_id, driver_id)
            except Exception:
                alloc_row_defaults = {}

            for route_params_id, trip_date, time_block, line_no, qty, time_text in rows:
                key = (int(route_params_id or 0), str(time_block or ""))
                rlist = row_index_time.get(key) or []
                if not rlist:
                    continue

                rr = _row_for_line(rlist, int(line_no or 0))
                if rr is None:
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

                it = self.table.item(int(rr), col)
                if it is None:
                    continue
                it.setText(str(q) if q != 0 else "")
                self._apply_day_cell_style(int(rr), col)

                if (time_text or "").strip():
                    t_item = self.table.item(int(rr), self._col_time_text)
                    if t_item is not None:
                        # Always prefer persisted time_text over planned label (e.g. '16:00-00:00')
                        t_item.setText((time_text or "").strip())

                # Apply row-level vehicle/driver defaults if present
                try:
                    k_def = (int(route_params_id or 0), str(time_block or "").strip(), int(line_no or 0))
                    vdid = alloc_row_defaults.get(k_def)
                    if vdid:
                        v_id, d_id = vdid
                        if v_id is not None and str(v_id).strip():
                            itv = self.table.item(int(rr), self._col_vehicle)
                            if itv is None:
                                itv = QTableWidgetItem("")
                                itv.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                                itv.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                                self.table.setItem(int(rr), self._col_vehicle, itv)
                            rec = (self._vehicle_map or {}).get(str(v_id))
                            if rec is not None:
                                try:
                                    plate, cap = rec
                                except Exception:
                                    plate, cap = str(rec), 0
                                label_v = f"{plate} ({int(cap)})" if int(cap or 0) > 0 else str(plate)
                                itv.setText(str(label_v))
                            itv.setData(Qt.ItemDataRole.UserRole, str(v_id))
                        if d_id is not None and str(d_id).strip():
                            itd = self.table.item(int(rr), self._col_driver)
                            if itd is None:
                                itd = QTableWidgetItem("")
                                itd.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                                itd.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                                self.table.setItem(int(rr), self._col_driver, itd)
                            nm = (self._driver_map or {}).get(str(d_id))
                            if nm is not None:
                                itd.setText(str(nm))
                            itd.setData(Qt.ItemDataRole.UserRole, str(d_id))
                except Exception:
                    pass

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

            try:
                split_keys = set()
                for r0 in range(self.table.rowCount()):
                    mm = self._row_meta[int(r0)] if int(r0) < len(self._row_meta) else None
                    try:
                        rid_i = int((mm or {}).get("route_params_id") or 0)
                    except Exception:
                        rid_i = 0
                    tb_s = str((mm or {}).get("time_block") or "").strip()
                    try:
                        ln_i = int((mm or {}).get("line_no") or 0)
                    except Exception:
                        ln_i = 0
                    if rid_i <= 0 or not tb_s or ln_i <= 0:
                        continue
                    mt_item = self.table.item(int(r0), self._col_movement)
                    mt_txt = self._norm_tr_text(mt_item.text() if mt_item is not None else "")
                    if ("cift" in mt_txt):
                        split_keys.add((rid_i, tb_s))

                for r in range(self.table.rowCount()):
                    meta = self._row_meta[r] if r < len(self._row_meta) else None
                    try:
                        rid_i = int((meta or {}).get("route_params_id") or 0)
                    except Exception:
                        rid_i = 0
                    tb_s = str((meta or {}).get("time_block") or "").strip()
                    try:
                        ln_i = int((meta or {}).get("line_no") or 0)
                    except Exception:
                        ln_i = 0

                    if rid_i <= 0 or not tb_s:
                        continue
                    if ln_i != 0:
                        continue
                    # TEK rows must never be treated as a base row of a split group.
                    try:
                        mt_item = self.table.item(int(r), self._col_movement)
                        mt_txt = self._norm_tr_text(mt_item.text() if mt_item is not None else "")
                        is_cift_row = ("cift" in mt_txt)
                    except Exception:
                        is_cift_row = False
                    if not is_cift_row:
                        continue
                    if (rid_i, tb_s) not in split_keys:
                        continue

                    # empty-row visibility is now controlled via a user prompt after load
            except Exception:
                pass
        finally:
            try:
                self.table.blockSignals(False)
            except Exception:
                pass

        # Prompt user about empty rows (planned but no entries) after load.
        try:
            empty_rows: list[int] = []
            nonempty_rows = 0
            for r in range(self.table.rowCount()):
                meta = self._row_meta[r] if r < len(self._row_meta) else None
                try:
                    rid_i = int((meta or {}).get("route_params_id") or 0)
                except Exception:
                    rid_i = 0
                tb_s = str((meta or {}).get("time_block") or "").strip()
                try:
                    ln_i = int((meta or {}).get("line_no") or 0)
                except Exception:
                    ln_i = 0

                is_empty = bool(self._row_is_empty_for_user(int(r)))
                if is_empty:
                    empty_rows.append(int(r))
                else:
                    nonempty_rows += 1

            if empty_rows and nonempty_rows > 0:
                q = QMessageBox.question(
                    self,
                    "Bilgi",
                    f"Bu dönem için veri girilmemiş {int(len(empty_rows))} satır var.\n\n"
                    "Bu boş satırlar ekranda yüklensin mi?\n\n"
                    "Evet: Boş satırları da göster\n"
                    "Hayır: Boş satırları gizle",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                hide_empty = (q == QMessageBox.StandardButton.No)
                for rr in empty_rows:
                    try:
                        self.table.setRowHidden(int(rr), bool(hide_empty))
                    except Exception:
                        pass
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

        # If there are empty (no trips entered) rows, warn user before saving.
        try:
            def _tr_float_local(s0: str) -> float:
                try:
                    t = str(s0 or "").strip()
                    if not t:
                        return 0.0
                    t = t.replace("₺", "").replace("TL", "")
                    t = t.replace(" ", "")
                    t = t.replace(".", "").replace(",", ".")
                    return float(t)
                except Exception:
                    return 0.0

            empty_rows = 0
            nonempty_rows = 0
            debug_suspects: list[str] = []
            for r in range(self.table.rowCount()):
                try:
                    if bool(self.table.isRowHidden(int(r))):
                        continue
                except Exception:
                    pass
                meta = self._row_meta[r] if r < len(self._row_meta) else None
                try:
                    rid_i = int((meta or {}).get("route_params_id") or 0)
                except Exception:
                    rid_i = 0
                tb_s = str((meta or {}).get("time_block") or "").strip()
                try:
                    ln_i = int((meta or {}).get("line_no") or 0)
                except Exception:
                    ln_i = 0

                is_empty = bool(self._row_is_empty_for_user(int(r)))
                if is_empty:
                    empty_rows += 1
                else:
                    nonempty_rows += 1

                # Collect debug info for rows that look empty by days/price but not counted as empty.
                try:
                    day_sum = int(self._row_day_qty_sum(int(r)))
                    tp_val = float(self._row_total_price(int(r)))
                    if (day_sum <= 0) and (tp_val <= 0.0) and (not is_empty):
                        debug_suspects.append(
                            f"satır={int(r)+1} neden=override rid={int(rid_i)} tb='{tb_s}'"
                        )
                    # Also capture cases where total price text parses as > 0 unexpectedly.
                    if tp_val > 0.0 and day_sum <= 0:
                        it_tp_dbg = self.table.item(int(r), int(self._col_total_price))
                        raw_tp = (it_tp_dbg.text() or "").strip() if it_tp_dbg is not None else ""
                        debug_suspects.append(
                            f"satır={int(r)+1} neden=tutar>0 tutar='{raw_tp}' rid={int(rid_i)} tb='{tb_s}'"
                        )
                except Exception:
                    pass

            if empty_rows > 0 and nonempty_rows > 0:
                try:
                    if debug_suspects:
                        debug_suspects = debug_suspects[:10]
                except Exception:
                    debug_suspects = []
                q = QMessageBox.question(
                    self,
                    "Uyarı",
                    f"Veri girilmemiş (boş) {int(empty_rows)} satır var.\n\n"
                    + (("\n".join(["Boş sayılmayan şüpheli satırlar:"] + debug_suspects) + "\n\n") if debug_suspects else "")
                    +
                    "Geri dönüp tamamlamak ister misiniz?\n\n"
                    "Evet: Geri dön (kaydetme)\n"
                    "Hayır: Boş satırları kabul et ve kaydet",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if q == QMessageBox.StandardButton.Yes:
                    return
        except Exception:
            pass

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
        existing_price_map: dict[tuple[int, str], float] = {}
        existing_allocations = set()
        try:
            conn0 = self.db.connect()
            cur0 = conn0.cursor()
            try:
                cur0.execute(
                    """
                    SELECT route_params_id, trip_date, time_block, line_no
                    FROM trip_entries
                    WHERE contract_id=? AND service_type=? AND trip_date BETWEEN ? AND ?
                    """,
                    (int(self.contract_id), str(self.service_type), start_date, end_date),
                )
                for rid0, d0, tb0, ln0 in cur0.fetchall() or []:
                    existing_entries.add((int(rid0 or 0), str(d0 or ""), str(tb0 or ""), int(ln0 or 0)))
            except Exception:
                cur0.execute(
                    """
                    SELECT route_params_id, trip_date, time_block
                    FROM trip_entries
                    WHERE contract_id=? AND service_type=? AND trip_date BETWEEN ? AND ?
                    """,
                    (int(self.contract_id), str(self.service_type), start_date, end_date),
                )
                for rid0, d0, tb0 in cur0.fetchall() or []:
                    existing_entries.add((int(rid0 or 0), str(d0 or ""), str(tb0 or ""), 0))

            cur0.execute(
                """
                SELECT route_params_id, time_block, price
                FROM trip_prices
                WHERE contract_id=? AND month=? AND service_type=?
                """,
                (int(self.contract_id), str(self.month_key), str(self.service_type)),
            )
            for rid0, tb0, pr0 in cur0.fetchall() or []:
                k0 = (int(rid0 or 0), str(tb0 or ""))
                existing_prices.add(k0)
                try:
                    existing_price_map[k0] = float(pr0 or 0.0)
                except Exception:
                    existing_price_map[k0] = 0.0

            try:
                cur0.execute(
                    """
                    SELECT route_params_id, trip_date, time_block, line_no
                    FROM trip_allocations
                    WHERE contract_id=? AND service_type=? AND trip_date BETWEEN ? AND ?
                    """,
                    (int(self.contract_id), str(self.service_type), start_date, end_date),
                )
                for rid0, d0, tb0, ln0 in cur0.fetchall() or []:
                    existing_allocations.add((int(rid0 or 0), str(d0 or ""), str(tb0 or ""), int(ln0 or 0)))
            except Exception:
                cur0.execute(
                    """
                    SELECT route_params_id, trip_date, time_block
                    FROM trip_allocations
                    WHERE contract_id=? AND service_type=? AND trip_date BETWEEN ? AND ?
                    """,
                    (int(self.contract_id), str(self.service_type), start_date, end_date),
                )
                for rid0, d0, tb0 in cur0.fetchall() or []:
                    existing_allocations.add((int(rid0 or 0), str(d0 or ""), str(tb0 or ""), 0))
            conn0.close()
        except Exception:
            existing_entries = set()
            existing_prices = set()
            existing_allocations = set()

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        price_rows = []
        price_write_map: dict[tuple[int, str], float] = {}
        entry_rows = []
        alloc_rows = []
        manual_payload: list[dict] = []
        empty_split_groups: list[tuple[int, str, int]] = []
        empty_hidden_groups: list[tuple[int, str, int]] = []

        # Determine which (route_params_id,time_block) keys are split in the current UI (any line_no>0).
        split_keys: set[tuple[int, str]] = set()
        try:
            for r0 in range(self.table.rowCount()):
                mm = self._row_meta[int(r0)] if int(r0) < len(self._row_meta) else None
                try:
                    rid_i = int((mm or {}).get("route_params_id") or 0)
                except Exception:
                    rid_i = 0
                tb_s = str((mm or {}).get("time_block") or "").strip()
                try:
                    ln_i = int((mm or {}).get("line_no") or 0)
                except Exception:
                    ln_i = 0
                if rid_i <= 0 or not tb_s or ln_i <= 0:
                    continue
                # Any row with line_no>0 indicates the (rid,time_block) group is split.
                # Whether it is ÇİFT is determined per-row later for price display/repair.
                split_keys.add((int(rid_i), str(tb_s)))
        except Exception:
            split_keys = set()

        for r in range(self.table.rowCount()):
            try:
                if self.table.isRowHidden(int(r)):
                    meta0 = self._row_meta[r] if r < len(self._row_meta) else None
                    try:
                        rid0 = int((meta0 or {}).get("route_params_id") or 0)
                    except Exception:
                        rid0 = 0
                    tb0 = str((meta0 or {}).get("time_block") or "").strip()
                    try:
                        ln0 = int((meta0 or {}).get("line_no") or 0)
                    except Exception:
                        ln0 = 0
                    if rid0 > 0 and tb0 and int(ln0) >= 0:
                        empty_hidden_groups.append((int(rid0), str(tb0), int(ln0)))
                    continue
            except Exception:
                pass

            meta = self._row_meta[r] if r < len(self._row_meta) else None
            rid = None
            it_route = self.table.item(r, 1)
            if it_route is not None:
                rid = it_route.data(Qt.ItemDataRole.UserRole)
            if not rid:
                try:
                    rid = int((meta or {}).get("route_params_id") or 0)
                except Exception:
                    rid = 0
            if not rid:
                # Manual row (no route_params_id) -> persist to bulk_puantaj_manual_rows only.
                try:
                    guz_txt = (it_route.text() or "").strip() if it_route is not None else ""
                except Exception:
                    guz_txt = ""
                itv = self.table.item(r, self._col_vehicle)
                itd = self.table.item(r, self._col_driver)
                vehicle_id = itv.data(Qt.ItemDataRole.UserRole) if itv is not None else None
                driver_id = itd.data(Qt.ItemDataRole.UserRole) if itd is not None else None
                if vehicle_id is None or (isinstance(vehicle_id, str) and not str(vehicle_id).strip()):
                    try:
                        vehicle_id = (itv.text() or "").strip() if itv is not None else None
                    except Exception:
                        vehicle_id = None
                if driver_id is None or (isinstance(driver_id, str) and not str(driver_id).strip()):
                    try:
                        driver_id = (itd.text() or "").strip() if itd is not None else None
                    except Exception:
                        driver_id = None
                mt_item = self.table.item(r, self._col_movement)
                mt_txt = (mt_item.text() or "").strip().upper() if mt_item is not None else ""
                tt_item = self.table.item(r, self._col_time_text)
                tt_txt = (tt_item.text() or "").strip() if tt_item is not None else ""
                p_item = self.table.item(r, self._col_price)
                p_txt = ((p_item.text() if p_item else "") or "").strip()
                try:
                    p_full = None
                    try:
                        if p_item is not None:
                            p_full = p_item.data(Qt.ItemDataRole.UserRole)
                    except Exception:
                        p_full = None
                    # Manual rows: UserRole is initialized to 0.0 and may stay stale.
                    # Prefer parsed text when it yields a positive value.
                    disp_price = 0.0
                    try:
                        disp_price = float(self._parse_tr_float(p_txt)) if str(p_txt).strip() else 0.0
                    except Exception:
                        disp_price = 0.0

                    if p_full is None or (isinstance(p_full, str) and not str(p_full).strip()):
                        unit_price = float(disp_price)
                    else:
                        try:
                            p_full_f = float(p_full or 0.0)
                        except Exception:
                            p_full_f = 0.0
                        unit_price = float(disp_price) if float(disp_price or 0.0) > 0.0 and float(p_full_f or 0.0) <= 0.0 else float(p_full_f)
                except Exception:
                    unit_price = 0.0

                day_map: dict[str, int] = {}
                try:
                    for day in range(1, int(self.days_in_month) + 1):
                        col = int(self._day_start) + (int(day) - 1)
                        itx = self.table.item(int(r), int(col))
                        v = (itx.text() or "").strip() if itx is not None else ""
                        if v.isdigit() and int(v) > 0:
                            day_map[str(int(day))] = int(v)
                except Exception:
                    day_map = {}

                has_any = bool(guz_txt or mt_txt or tt_txt or (str(vehicle_id or "").strip()) or (str(driver_id or "").strip()))
                has_any = bool(has_any or (float(unit_price or 0.0) > 0.0) or bool(day_map))
                if has_any:
                    manual_payload.append(
                        {
                            "sort_order": int(len(manual_payload)),
                            "guzergah": str(guz_txt),
                            "vehicle_id": (None if vehicle_id is None or not str(vehicle_id).strip() else str(vehicle_id)),
                            "driver_id": (None if driver_id is None or not str(driver_id).strip() else str(driver_id)),
                            "movement_type": str(mt_txt),
                            "time_text": str(tt_txt),
                            "unit_price": float(unit_price or 0.0),
                            "day_qty_json": json.dumps(day_map, ensure_ascii=False),
                        }
                    )
                continue

            time_block = str((meta or {}).get("time_block") or "GUN")
            try:
                line_no = int((meta or {}).get("line_no") or 0)
            except Exception:
                line_no = 0
            plan_tb = str((meta or {}).get("plan_time_block") or "").strip()
            planned_key_tb = plan_tb if plan_tb else str(time_block)
            is_planned = (int(rid), str(planned_key_tb)) in (self._planned_keys or set())
            # Split rows should not be persisted as empty planned rows.
            if int(line_no or 0) > 0:
                is_planned = False

            time_text = ""
            it_time = self.table.item(r, self._col_time_text)
            if it_time is not None:
                time_text = (it_time.text() or "").strip()

            it_v = self.table.item(r, self._col_vehicle)
            it_d = self.table.item(r, self._col_driver)
            vehicle_id = it_v.data(Qt.ItemDataRole.UserRole) if it_v is not None else None
            driver_id = it_d.data(Qt.ItemDataRole.UserRole) if it_d is not None else None

            p_item = self.table.item(r, self._col_price)
            p_txt = ((p_item.text() if p_item else "") or "").strip()
            try:
                # Prefer full unit price from UserRole; displayed text can be half for split rows.
                p_full = None
                try:
                    if p_item is not None:
                        p_full = p_item.data(Qt.ItemDataRole.UserRole)
                except Exception:
                    p_full = None
                if p_full is None or (isinstance(p_full, str) and not str(p_full).strip()):
                    price = self._parse_tr_float(p_txt)
                else:
                    price = float(p_full or 0.0)
            except Exception:
                price = 0.0

            is_cift_row = False
            try:
                mt_item = self.table.item(r, self._col_movement)
                mt_txt = self._norm_tr_text(mt_item.text() if mt_item is not None else "")
                is_cift_row = ("cift" in mt_txt)
            except Exception:
                is_cift_row = False

            # Persist trip_prices as the full base unit price.
            # Full unit price is carried in UserRole; UI may display half for split rows.
            base_price = float(price)
            # Repair legacy data for split ÇİFT rows.
            # Scenario A: DB already contains half price, UI shows quarter -> use DB*2.
            # Scenario B: UI shows half, and we are about to write half -> use UI*2.
            try:
                if bool(is_cift_row) and (int(rid), str(time_block)) in split_keys:
                    disp = float(self._parse_tr_float(p_txt)) if str(p_txt).strip() else 0.0
                    kdb = (int(rid), str(time_block))
                    db_price = float(existing_price_map.get(kdb) or 0.0)
                    eps = 0.0001
                    if disp > 0.0:
                        # Only upscale when DB is actually storing the displayed value.
                        # In correct state: DB=full, UI=half -> db_price ~= disp*2. That is NOT a legacy bug.
                        # Legacy bug: DB=half and UI=half -> db_price ~= disp, so fix via db*2.
                        if db_price > 0.0 and abs(float(db_price) - float(disp)) < eps:
                            base_price = float(db_price) * 2.0
                        # If we are about to persist displayed value (half), fix to full via *2
                        elif abs(float(base_price) - float(disp)) < eps:
                            base_price = float(base_price) * 2.0
            except Exception:
                base_price = float(base_price)

            if base_price != 0.0 or (int(rid), time_block) in existing_prices:
                kprice = (int(rid), str(time_block))
                prev = price_write_map.get(kprice)
                if prev is None:
                    price_write_map[kprice] = float(base_price)
                else:
                    price_write_map[kprice] = max(float(prev), float(base_price))

            for day in range(1, self.days_in_month + 1):
                col = self._day_start + (day - 1)
                it = self.table.item(r, col)
                val = (it.text() or "").strip() if it else ""
                qty = int(val) if val.isdigit() else 0
                trip_date = QDate(self.year, self.month, day).toString("yyyy-MM-dd")
                key = (int(rid), str(trip_date), str(time_block), int(line_no))
                if is_planned or qty != 0 or key in existing_entries:
                    entry_rows.append(
                        (
                            int(self.contract_id),
                            int(rid),
                            str(trip_date),
                            str(self.service_type),
                            str(time_block),
                            int(line_no),
                            int(qty),
                            str(time_text),
                            now,
                            now,
                        )
                    )

                key2 = (int(rid), str(trip_date), str(time_block), int(line_no))
                if is_planned or qty != 0 or key2 in existing_allocations:
                    override = self._alloc_override_map.get((int(rid), str(time_block), str(trip_date), int(line_no))) or {}
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
                            int(line_no),
                            d2,
                            v2,
                            float(qty),
                            str(time_text),
                            note2,
                            now,
                            now,
                        )
                    )

            # Track empty split rows for cleanup: if the entire row is empty and has no overrides,
            # remove persisted entries/allocations so we don't get phantom extra split lines later.
            try:
                if int(line_no or 0) > 0:
                    has_any_qty = False
                    for day in range(1, self.days_in_month + 1):
                        col = self._day_start + (day - 1)
                        itx = self.table.item(r, col)
                        v = (itx.text() or "").strip() if itx else ""
                        if v.isdigit() and int(v) > 0:
                            has_any_qty = True
                            break

                    has_any_override = False
                    if not has_any_qty:
                        for day in range(1, self.days_in_month + 1):
                            trip_date = QDate(self.year, self.month, day).toString("yyyy-MM-dd")
                            k0 = (int(rid), str(time_block), str(trip_date), int(line_no))
                            rec0 = (self._alloc_override_map or {}).get(k0) or {}
                            if bool(rec0.get("is_override")) or bool((rec0.get("note") or "").strip()):
                                has_any_override = True
                                break

                    if (not has_any_qty) and (not has_any_override) and (not (time_text or "").strip()):
                        empty_split_groups.append((int(rid), str(time_block), int(line_no)))
            except Exception:
                pass

        try:
            conn = self.db.connect()
            cur = conn.cursor()
            cur.execute("BEGIN")

            try:
                def _parse_hhmm_to_minutes(s: str):
                    t = str(s or "").strip()
                    if not t:
                        return None
                    parts = t.split(":")
                    if len(parts) != 2:
                        return None
                    if (not parts[0].isdigit()) or (not parts[1].isdigit()):
                        return None
                    hh = int(parts[0])
                    mm = int(parts[1])
                    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
                        return None
                    return hh * 60 + mm

                def _parse_range_minutes(tb: str, tt: str):
                    txt = str(tt or "").strip() or str(tb or "").strip()
                    if not txt:
                        return None, None
                    if "-" in txt:
                        left, right = (txt.split("-", 1) + [""])[:2]
                        m1 = _parse_hhmm_to_minutes(left.strip())
                        m2 = _parse_hhmm_to_minutes(right.strip())
                        if m1 is None or m2 is None:
                            return None, None
                        if m2 == m1:
                            return m1, (m1 + 15) % 1440
                        return m1, m2
                    m = _parse_hhmm_to_minutes(txt)
                    if m is None:
                        return None, None
                    return m, (m + 15) % 1440

                def _segments(s: int, e: int):
                    if s == e:
                        return [(s, (s + 1) % 1440)]
                    if s < e:
                        return [(s, e)]
                    return [(s, 1440), (0, e)]

                def _overlap(a1: int, a2: int, b1: int, b2: int):
                    for s1, e1 in _segments(int(a1), int(a2)):
                        for s2, e2 in _segments(int(b1), int(b2)):
                            if max(s1, s2) < min(e1, e2):
                                return True
                    return False

                conflict_found = False

                local_by_vehicle = {}
                local_by_driver = {}
                for row in alloc_rows or []:
                    try:
                        c_id, rid, tdate, st, tb, ln, did, vid, q, tt, nt, ca, ua = row
                    except Exception:
                        continue
                    try:
                        if float(q or 0) <= 0:
                            continue
                    except Exception:
                        continue
                    s_m, e_m = _parse_range_minutes(str(tb or ""), str(tt or ""))
                    if s_m is None or e_m is None:
                        continue

                    key_date = str(tdate)
                    if vid is not None and str(vid).strip():
                        local_by_vehicle.setdefault((key_date, str(vid)), []).append((int(s_m), int(e_m), int(rid), str(tb or ""), int(ln or 0)))
                    if did is not None and str(did).strip():
                        local_by_driver.setdefault((key_date, str(did)), []).append((int(s_m), int(e_m), int(rid), str(tb or ""), int(ln or 0)))

                for (dkey, vkey), rr in (local_by_vehicle or {}).items():
                    rr2 = sorted(rr, key=lambda x: (x[0], x[1]))
                    for i in range(len(rr2)):
                        for j in range(i + 1, len(rr2)):
                            if _overlap(rr2[i][0], rr2[i][1], rr2[j][0], rr2[j][1]):
                                conflict_found = True
                                break
                            if rr2[j][0] > rr2[i][1] and rr2[i][0] < rr2[i][1]:
                                break
                        if conflict_found:
                            break
                    if conflict_found:
                        break

                for (dkey, drkey), rr in (local_by_driver or {}).items():
                    rr2 = sorted(rr, key=lambda x: (x[0], x[1]))
                    for i in range(len(rr2)):
                        for j in range(i + 1, len(rr2)):
                            if _overlap(rr2[i][0], rr2[i][1], rr2[j][0], rr2[j][1]):
                                conflict_found = True
                                break
                            if rr2[j][0] > rr2[i][1] and rr2[i][0] < rr2[i][1]:
                                break
                        if conflict_found:
                            break
                    if conflict_found:
                        break

                for row in alloc_rows or []:
                    try:
                        c_id, rid, tdate, st, tb, ln, did, vid, q, tt, nt, ca, ua = row
                    except Exception:
                        continue
                    try:
                        if float(q or 0) <= 0:
                            continue
                    except Exception:
                        continue
                    if (vid is None or not str(vid).strip()) and (did is None or not str(did).strip()):
                        continue
                    conflict = self.db.find_allocation_conflict(
                        contract_id=int(self.contract_id),
                        trip_date=str(tdate),
                        service_type=str(self.service_type),
                        time_block=str(tb),
                        time_text=str(tt or ""),
                        vehicle_id=vid,
                        driver_id=did,
                        exclude_route_params_id=int(rid),
                        exclude_time_block=str(tb),
                        exclude_line_no=int(ln or 0),
                    )
                    if conflict:
                        conflict_found = True
                        break

                if conflict_found:
                    QMessageBox.warning(
                        self,
                        "Çakışma Uyarısı",
                        "Aynı gün içinde araç/şoför saat çakışması tespit edildi. Uyarıya rağmen kayıt yapılacaktır.",
                    )
            except Exception:
                pass

            try:
                for rid0, tb0, ln0 in (empty_hidden_groups or []):
                    if int(ln0 or 0) != 0:
                        continue
                    cur.execute(
                        """
                        DELETE FROM trip_entries
                        WHERE contract_id=? AND service_type=? AND time_block=? AND route_params_id=?
                          AND line_no=? AND trip_date BETWEEN ? AND ?
                        """,
                        (
                            int(self.contract_id),
                            str(self.service_type),
                            str(tb0),
                            int(rid0),
                            int(ln0),
                            start_date,
                            end_date,
                        ),
                    )
                    cur.execute(
                        """
                        DELETE FROM trip_allocations
                        WHERE contract_id=? AND service_type=? AND time_block=? AND route_params_id=?
                          AND line_no=? AND trip_date BETWEEN ? AND ?
                        """,
                        (
                            int(self.contract_id),
                            str(self.service_type),
                            str(tb0),
                            int(rid0),
                            int(ln0),
                            start_date,
                            end_date,
                        ),
                    )
            except Exception:
                pass

            try:
                if price_write_map:
                    for (ridp, tbp), prp in (price_write_map or {}).items():
                        price_rows.append(
                            (
                                int(self.contract_id),
                                int(ridp),
                                str(self.month_key),
                                str(self.service_type),
                                str(tbp),
                                float(prp),
                                now,
                            )
                        )
            except Exception:
                pass

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
                        contract_id, route_params_id, trip_date, service_type, time_block, line_no,
                        qty, time_text, created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(contract_id, route_params_id, trip_date, service_type, time_block, line_no)
                    DO UPDATE SET qty=excluded.qty, time_text=excluded.time_text, updated_at=excluded.updated_at
                    """,
                    entry_rows,
                )

            if alloc_rows:
                cur.executemany(
                    """
                    INSERT INTO trip_allocations (
                        contract_id, route_params_id, trip_date, service_type, time_block, line_no,
                        driver_id, vehicle_id, qty, time_text, note, created_at, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(contract_id, route_params_id, trip_date, service_type, time_block, line_no)
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

            # Cleanup empty split groups (line_no>0) to avoid extra/unused split rows coming back.
            try:
                for rid0, tb0, ln0 in (empty_split_groups or []):
                    if int(ln0 or 0) <= 0:
                        continue
                    cur.execute(
                        """
                        DELETE FROM trip_entries
                        WHERE contract_id=? AND service_type=? AND time_block=? AND route_params_id=?
                          AND line_no=? AND trip_date BETWEEN ? AND ?
                        """,
                        (
                            int(self.contract_id),
                            str(self.service_type),
                            str(tb0),
                            int(rid0),
                            int(ln0),
                            start_date,
                            end_date,
                        ),
                    )
                    cur.execute(
                        """
                        DELETE FROM trip_allocations
                        WHERE contract_id=? AND service_type=? AND time_block=? AND route_params_id=?
                          AND line_no=? AND trip_date BETWEEN ? AND ?
                        """,
                        (
                            int(self.contract_id),
                            str(self.service_type),
                            str(tb0),
                            int(rid0),
                            int(ln0),
                            start_date,
                            end_date,
                        ),
                    )
            except Exception:
                pass

            try:
                warned = set()
                for row in alloc_rows or []:
                    try:
                        c_id, rid, tdate, st, tb, ln, did, vid, q, tt, nt, ca, ua = row
                    except Exception:
                        continue
                    try:
                        if float(q or 0) <= 0:
                            continue
                    except Exception:
                        continue
                    if vid is None or not str(vid).strip():
                        continue
                    k = (str(tdate), str(vid))
                    if k in warned:
                        continue
                    warned.add(k)
                    mv = int(self.db.get_vehicle_movements_for_day(int(self.contract_id), str(tdate), vid) or 0)
                    if mv > 8:
                        QMessageBox.warning(self, "Uyarı", f"Bu araç için {tdate} tarihinde hareket sayısı {mv} oldu (limit: 8).")
            except Exception:
                pass

            conn.commit()
            conn.close()

            try:
                ok_manual = self.db.replace_bulk_puantaj_manual_rows(
                    int(self.contract_id),
                    str(self.month_key),
                    str(self.service_type),
                    list(manual_payload or []),
                )
                if not bool(ok_manual):
                    QMessageBox.warning(self, "Uyarı", "Manuel satırlar kaydedilemedi.")
            except Exception:
                try:
                    QMessageBox.warning(self, "Uyarı", "Manuel satırlar kaydedilemedi.")
                except Exception:
                    pass
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

        month_key = _norm_month_key(str(self.ctx.month))

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
                (int(self.ctx.contract_id), str(month_key), *self.service_type_values),
            )
            rows = cursor.fetchall() or []

            if not rows:
                try:
                    cursor.execute(
                        """
                        SELECT route_params_id, time_block
                        FROM trip_plan
                        WHERE contract_id = ?
                          AND month = ?
                        """,
                        (int(self.ctx.contract_id), str(month_key)),
                    )
                    rows = cursor.fetchall() or []
                except Exception:
                    rows = []

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
