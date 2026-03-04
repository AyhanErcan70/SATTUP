
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from app.core.db_manager import DatabaseManager
from config import get_ui_path


@dataclass(frozen=True)
class _Period:
    year: int
    month: int

    def key(self) -> str:
        return f"{int(self.year):04d}-{int(self.month):02d}"


class HakedisApp(QWidget):
    def __init__(self, parent=None, user_data=None, db: DatabaseManager | None = None):
        super().__init__(parent)
        uic.loadUi(get_ui_path("hakedis_window.ui"), self)
        self.setObjectName("main_form")

        self.user_data = user_data or {}
        self.db = db if db else DatabaseManager()

        self._setup_connections()
        self._init_filters()
        self._clear_tables()

    def _clear_tables(self):
        for name in ("tbl_tab1_yuklenici_araclari", "tbl_tab2_sirket_araclari", "tbl_owner_report"):
            tbl = getattr(self, name, None)
            if tbl is None:
                continue
            try:
                tbl.setRowCount(0)
            except Exception:
                pass

    def _setup_connections(self):
        if hasattr(self, "btn_refresh"):
            self.btn_refresh.clicked.connect(self.load_tables)
        if hasattr(self, "btn_export_excel"):
            self.btn_export_excel.clicked.connect(self.export_excel)
        if hasattr(self, "btn_export_pdf"):
            self.btn_export_pdf.clicked.connect(self.export_pdf)
        if hasattr(self, "cmb_owner"):
            try:
                self.cmb_owner.currentIndexChanged.connect(self._load_owner_report)
            except Exception:
                pass

    def _init_filters(self):
        self._fill_year_month()
        self._fill_customers()

    def _fill_year_month(self):
        ycmb = getattr(self, "cmb_year", None)
        mcmb = getattr(self, "cmb_month", None)
        if ycmb is None or mcmb is None:
            return

        ycmb.blockSignals(True)
        mcmb.blockSignals(True)
        try:
            ycmb.clear()
            mcmb.clear()

            today = date.today()
            for y in range(int(today.year) - 3, int(today.year) + 2):
                ycmb.addItem(str(y), int(y))

            months = [
                ("OCAK", 1),
                ("ŞUBAT", 2),
                ("MART", 3),
                ("NİSAN", 4),
                ("MAYIS", 5),
                ("HAZİRAN", 6),
                ("TEMMUZ", 7),
                ("AĞUSTOS", 8),
                ("EYLÜL", 9),
                ("EKİM", 10),
                ("KASIM", 11),
                ("ARALIK", 12),
            ]
            for name, m in months:
                mcmb.addItem(name, int(m))

            yi = ycmb.findData(int(today.year))
            if yi >= 0:
                ycmb.setCurrentIndex(yi)
            mi = mcmb.findData(int(today.month))
            if mi >= 0:
                mcmb.setCurrentIndex(mi)
        finally:
            ycmb.blockSignals(False)
            mcmb.blockSignals(False)

    def _fill_customers(self):
        cmb = getattr(self, "cmb_customer", None)
        if cmb is None:
            return

        cmb.blockSignals(True)
        try:
            cmb.clear()
            cmb.addItem("Seçiniz...", None)
            for cid, title in self.db.get_active_customers_list() or []:
                cmb.addItem(str(title or ""), int(cid))
        finally:
            cmb.blockSignals(False)

    def _selected_period(self) -> _Period | None:
        ycmb = getattr(self, "cmb_year", None)
        mcmb = getattr(self, "cmb_month", None)
        if ycmb is None or mcmb is None:
            return None
        try:
            y = int(ycmb.currentData() or 0)
            m = int(mcmb.currentData() or 0)
        except Exception:
            return None
        if y <= 0 or m <= 0:
            return None
        return _Period(year=y, month=m)

    def _selected_customer_id(self) -> int | None:
        cmb = getattr(self, "cmb_customer", None)
        if cmb is None:
            return None
        try:
            v = cmb.currentData()
            return int(v) if v is not None and str(v).strip() else None
        except Exception:
            return None

    def _fmt_money(self, v: object) -> str:
        try:
            x = float(v or 0)
        except Exception:
            x = 0.0
        s = f"{x:,.2f}"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")

    def _fmt_qty(self, v: object) -> str:
        try:
            x = float(v or 0)
        except Exception:
            x = 0.0
        s = f"{x:,.2f}"
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        try:
            if "," in s:
                s2 = s.rstrip("0").rstrip(",")
                return s2 if s2 else "0"
        except Exception:
            pass
        return s

    def _set_item(self, tbl: QTableWidget, r: int, c: int, text: str, align=Qt.AlignmentFlag.AlignCenter):
        it = QTableWidgetItem(str(text))
        it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        try:
            it.setTextAlignment(align)
        except Exception:
            pass
        tbl.setItem(int(r), int(c), it)

    def _set_item_total(self, tbl: QTableWidget, r: int, c: int, text: str, align=Qt.AlignmentFlag.AlignCenter):
        it = QTableWidgetItem(str(text))
        it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        try:
            it.setTextAlignment(align)
        except Exception:
            pass
        try:
            f = QFont()
            f.setBold(True)
            f.setItalic(True)
            it.setFont(f)
        except Exception:
            pass
        tbl.setItem(int(r), int(c), it)

    def load_tables(self):
        period = self._selected_period()
        if period is None:
            QMessageBox.warning(self, "Uyarı", "Lütfen dönem seçiniz.")
            return

        customer_id = self._selected_customer_id()
        month_key = period.key()

        rows_tab1 = self.db.get_hakedis_tab1_yuklenici_araclari_rows_all(
            period=str(month_key),
            customer_id=int(customer_id) if customer_id is not None else None,
        )
        rows_tab2 = self.db.get_hakedis_tab2_sirket_araclari_rows_all(
            period=str(month_key),
            customer_id=int(customer_id) if customer_id is not None else None,
        )

        self._fill_tab1(rows_tab1 or [])
        self._fill_tab2(rows_tab2 or [])
        self._refresh_owner_list()
        self._load_owner_report()

    def _refresh_owner_list(self):
        cmb = getattr(self, "cmb_owner", None)
        if cmb is None:
            return
        period = self._selected_period()
        if period is None:
            return
        customer_id = self._selected_customer_id()
        month_key = period.key()

        prev = ""
        try:
            prev = str(cmb.currentData() or "")
        except Exception:
            prev = ""

        cmb.blockSignals(True)
        try:
            cmb.clear()
            cmb.addItem("Seçiniz...", "")
            for o in self.db.get_hakedis_tab1_owner_list_for_period(
                period=str(month_key),
                customer_id=int(customer_id) if customer_id is not None else None,
            ):
                cmb.addItem(str(o), str(o))
        finally:
            cmb.blockSignals(False)

        try:
            if prev:
                ix = cmb.findData(str(prev))
                if ix >= 0:
                    cmb.setCurrentIndex(ix)
        except Exception:
            pass

    def _load_owner_report(self):
        tbl = getattr(self, "tbl_owner_report", None)
        cmb = getattr(self, "cmb_owner", None)
        if tbl is None or cmb is None:
            return
        period = self._selected_period()
        if period is None:
            return
        customer_id = self._selected_customer_id()
        month_key = period.key()

        try:
            owner = str(cmb.currentData() or "").strip()
        except Exception:
            owner = ""

        if not owner:
            try:
                tbl.clearContents()
            except Exception:
                pass
            try:
                tbl.setRowCount(0)
            except Exception:
                pass
            return

        rows = self.db.get_hakedis_tab1_owner_report_rows_all(
            period=str(month_key),
            owner=str(owner),
            customer_id=int(customer_id) if customer_id is not None else None,
        )
        self._fill_owner_report(rows or [])

    def _fill_owner_report(self, rows: list[tuple]):
        tbl = getattr(self, "tbl_owner_report", None)
        if tbl is None:
            return
        try:
            tbl.clearContents()
        except Exception:
            pass
        tbl.setRowCount(int(len(rows)) + 1)

        sum_gun = 0.0
        sum_tutar = 0.0
        sum_kdv = 0.0
        sum_ara = 0.0
        sum_genel = 0.0

        for r, rec in enumerate(rows):
            try:
                firma, guzergah, sahis, plaka, hareket, gun, bfiyat, tutar, kdv, ara_top, genel = rec
            except Exception:
                continue

            try:
                sum_gun += float(gun or 0)
            except Exception:
                pass
            try:
                sum_tutar += float(tutar or 0)
            except Exception:
                pass
            try:
                sum_kdv += float(kdv or 0)
            except Exception:
                pass
            try:
                sum_ara += float(ara_top or 0)
            except Exception:
                pass
            try:
                sum_genel += float(genel or 0)
            except Exception:
                pass

            self._set_item(tbl, r, 0, str(firma), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._set_item(tbl, r, 1, str(guzergah), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._set_item(tbl, r, 2, str(sahis), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._set_item(tbl, r, 3, str(plaka))
            self._set_item(tbl, r, 4, str(hareket))
            self._set_item(tbl, r, 5, self._fmt_qty(gun))
            self._set_item(tbl, r, 6, self._fmt_money(bfiyat))
            self._set_item(tbl, r, 7, self._fmt_money(tutar))
            self._set_item(tbl, r, 8, self._fmt_money(kdv))
            self._set_item(tbl, r, 9, self._fmt_money(ara_top))
            self._set_item(tbl, r, 10, self._fmt_money(genel))

        tr = int(len(rows))
        try:
            self._set_item_total(tbl, tr, 0, "")
            self._set_item_total(tbl, tr, 1, "")
            self._set_item_total(tbl, tr, 2, "")
            self._set_item_total(tbl, tr, 3, "")
            self._set_item_total(tbl, tr, 4, "TOPLAM", Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._set_item_total(tbl, tr, 5, self._fmt_qty(sum_gun))
            self._set_item_total(tbl, tr, 6, "")
            self._set_item_total(tbl, tr, 7, self._fmt_money(sum_tutar))
            self._set_item_total(tbl, tr, 8, self._fmt_money(sum_kdv))
            self._set_item_total(tbl, tr, 9, self._fmt_money(sum_ara))
            self._set_item_total(tbl, tr, 10, self._fmt_money(sum_genel))
        except Exception:
            pass

        try:
            tbl.resizeColumnsToContents()
        except Exception:
            pass

    def _fill_tab1(self, rows: list[tuple]):
        tbl = getattr(self, "tbl_tab1_yuklenici_araclari", None)
        if tbl is None:
            return
        try:
            tbl.clearContents()
        except Exception:
            pass
        tbl.setRowCount(int(len(rows)) + 1)

        sum_gun = 0.0
        sum_toplam = 0.0
        sum_kdv = 0.0
        sum_ara_top = 0.0
        sum_tev = 0.0
        sum_gtop = 0.0

        # Expected columns in UI (11): MÜŞTERİ/CARİ(FİRMA), GÜZERGAH, ŞAHIS, HAREKET TÜRÜ,
        # GÜN TOP., B.FİYAT, TOPLAM, KDV%20, ARA TOPLAM, TEVKİFAT %10, GENEL TOPLAM
        for r, rec in enumerate(rows):
            try:
                firma, guzergah, sahis, hareket, gun, bfiyat, toplam, kdv, ara_top, tev, gtop = rec
            except Exception:
                continue

            try:
                sum_gun += float(gun or 0)
            except Exception:
                pass
            try:
                sum_toplam += float(toplam or 0)
            except Exception:
                pass
            try:
                sum_kdv += float(kdv or 0)
            except Exception:
                pass
            try:
                sum_ara_top += float(ara_top or 0)
            except Exception:
                pass
            try:
                sum_tev += float(tev or 0)
            except Exception:
                pass
            try:
                sum_gtop += float(gtop or 0)
            except Exception:
                pass

            self._set_item(tbl, r, 0, str(firma), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._set_item(tbl, r, 1, str(guzergah), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._set_item(tbl, r, 2, str(sahis), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._set_item(tbl, r, 3, str(hareket))
            self._set_item(tbl, r, 4, self._fmt_qty(gun))
            self._set_item(tbl, r, 5, self._fmt_money(bfiyat))
            self._set_item(tbl, r, 6, self._fmt_money(toplam))
            self._set_item(tbl, r, 7, self._fmt_money(kdv))
            self._set_item(tbl, r, 8, self._fmt_money(ara_top))
            self._set_item(tbl, r, 9, self._fmt_money(tev))
            self._set_item(tbl, r, 10, self._fmt_money(gtop))

        tr = int(len(rows))
        try:
            self._set_item_total(tbl, tr, 0, "")
            self._set_item_total(tbl, tr, 1, "")
            self._set_item_total(tbl, tr, 2, "")
            self._set_item_total(tbl, tr, 3, "TOPLAM", Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._set_item_total(tbl, tr, 4, self._fmt_qty(sum_gun))
            self._set_item_total(tbl, tr, 5, "")
            self._set_item_total(tbl, tr, 6, self._fmt_money(sum_toplam))
            self._set_item_total(tbl, tr, 7, self._fmt_money(sum_kdv))
            self._set_item_total(tbl, tr, 8, self._fmt_money(sum_ara_top))
            self._set_item_total(tbl, tr, 9, self._fmt_money(sum_tev))
            self._set_item_total(tbl, tr, 10, self._fmt_money(sum_gtop))
        except Exception:
            pass

        try:
            tbl.resizeColumnsToContents()
        except Exception:
            pass

    def _fill_tab2(self, rows: list[tuple]):
        tbl = getattr(self, "tbl_tab2_sirket_araclari", None)
        if tbl is None:
            return
        try:
            tbl.clearContents()
        except Exception:
            pass
        tbl.setRowCount(int(len(rows)) + 1)

        sum_gun = 0.0
        sum_toplam = 0.0
        sum_kdv = 0.0
        sum_ara_top = 0.0
        sum_tev = 0.0
        sum_gtop = 0.0

        # UI columns (11): GÜZERGAH, ŞAHIS, PLAKA, HAREKET TÜRÜ, GÜN TOP., B.FİYAT,
        # TOPLAM, KDV%20, ARA TOPLAM, TEVKİFAT %10, GENEL TOPLAM
        for r, rec in enumerate(rows):
            try:
                firma, guzergah, sahis, plaka, hareket, gun, bfiyat, toplam, kdv, ara_top, tev, gtop = rec
            except Exception:
                continue

            try:
                sum_gun += float(gun or 0)
            except Exception:
                pass
            try:
                sum_toplam += float(toplam or 0)
            except Exception:
                pass
            try:
                sum_kdv += float(kdv or 0)
            except Exception:
                pass
            try:
                sum_ara_top += float(ara_top or 0)
            except Exception:
                pass
            try:
                sum_tev += float(tev or 0)
            except Exception:
                pass
            try:
                sum_gtop += float(gtop or 0)
            except Exception:
                pass

            self._set_item(tbl, r, 0, str(firma), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._set_item(tbl, r, 1, str(guzergah), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._set_item(tbl, r, 2, str(sahis), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._set_item(tbl, r, 3, str(plaka))
            self._set_item(tbl, r, 4, str(hareket))
            self._set_item(tbl, r, 5, self._fmt_qty(gun))
            self._set_item(tbl, r, 6, self._fmt_money(bfiyat))
            self._set_item(tbl, r, 7, self._fmt_money(toplam))
            self._set_item(tbl, r, 8, self._fmt_money(kdv))
            self._set_item(tbl, r, 9, self._fmt_money(ara_top))
            self._set_item(tbl, r, 10, self._fmt_money(tev))
            self._set_item(tbl, r, 11, self._fmt_money(gtop))

        tr = int(len(rows))
        try:
            self._set_item_total(tbl, tr, 0, "")
            self._set_item_total(tbl, tr, 1, "")
            self._set_item_total(tbl, tr, 2, "")
            self._set_item_total(tbl, tr, 3, "")
            self._set_item_total(tbl, tr, 4, "TOPLAM", Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._set_item_total(tbl, tr, 5, self._fmt_qty(sum_gun))
            self._set_item_total(tbl, tr, 6, "")
            self._set_item_total(tbl, tr, 7, self._fmt_money(sum_toplam))
            self._set_item_total(tbl, tr, 8, self._fmt_money(sum_kdv))
            self._set_item_total(tbl, tr, 9, self._fmt_money(sum_ara_top))
            self._set_item_total(tbl, tr, 10, self._fmt_money(sum_tev))
            self._set_item_total(tbl, tr, 11, self._fmt_money(sum_gtop))
        except Exception:
            pass

        try:
            tbl.resizeColumnsToContents()
        except Exception:
            pass

    def export_excel(self):
        tbl1 = getattr(self, "tbl_tab1_yuklenici_araclari", None)
        tbl2 = getattr(self, "tbl_tab2_sirket_araclari", None)
        if tbl1 is None or tbl2 is None:
            return

        out_path, _ = QFileDialog.getSaveFileName(self, "Excel Kaydet", "hakedis.xlsx", "Excel (*.xlsx)")
        if not out_path:
            return

        try:
            import openpyxl
        except Exception:
            QMessageBox.critical(self, "Hata", "Excel aktarımı için 'openpyxl' gerekli.")
            return

        wb = openpyxl.Workbook()
        ws1 = wb.active
        ws1.title = "YÜKLENİCİ ARAÇLARI"
        ws2 = wb.create_sheet("ŞİRKET ARAÇ")

        def _dump_qtable(ws, tbl: QTableWidget):
            headers = []
            for c in range(tbl.columnCount()):
                hi = tbl.horizontalHeaderItem(c)
                headers.append((hi.text() if hi is not None else ""))
            ws.append(headers)
            for r in range(tbl.rowCount()):
                row = []
                for c in range(tbl.columnCount()):
                    it = tbl.item(r, c)
                    row.append(it.text() if it is not None else "")
                ws.append(row)

        _dump_qtable(ws1, tbl1)
        _dump_qtable(ws2, tbl2)

        try:
            wb.save(str(Path(out_path)))
        except Exception:
            QMessageBox.critical(self, "Hata", "Excel kaydedilemedi.")
            return

        QMessageBox.information(self, "Bilgi", "Excel kaydedildi.")

    def export_pdf(self):
        QMessageBox.information(self, "Bilgi", "PDF aktarımı bu sürümde henüz hazırlanmadı.")

