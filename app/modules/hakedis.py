from __future__ import annotations

import json
import os
import re
from datetime import datetime

from PyQt6 import uic
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMessageBox, QTableWidget, QTableWidgetItem, QWidget

from app.core.db_manager import DatabaseManager
from config import get_ui_path


class HakedisApp(QWidget):
    def __init__(self, parent=None, user_data=None, db: DatabaseManager | None = None):
        super().__init__(parent)
        uic.loadUi(get_ui_path("hakedis_window.ui"), self)
        self.setObjectName("main_form")

        self.user_data = user_data or {}
        self.db = db if db else DatabaseManager()

        self._setup_connections()
        self._init_defaults()

    def _set_status(self, message: str):
        msg = str(message or "").strip()
        try:
            w = getattr(self, "lbl_statusbar", None)
            if w is not None:
                w.setText(msg)
        except Exception:
            pass

    def _setup_connections(self):
        if hasattr(self, "btn_refresh"):
            self.btn_refresh.clicked.connect(self.load_table)
        if hasattr(self, "btn_calc"):
            self.btn_calc.clicked.connect(self.calculate_hakedis)
        if hasattr(self, "btn_approve"):
            self.btn_approve.clicked.connect(self.approve_selected)
        if hasattr(self, "btn_invoice"):
            self.btn_invoice.clicked.connect(self.invoice_selected)
        if hasattr(self, "btn_add_deduction"):
            self.btn_add_deduction.clicked.connect(self.add_deduction)
        if hasattr(self, "btn_remove_deduction"):
            self.btn_remove_deduction.clicked.connect(self.remove_selected_deductions)
        if hasattr(self, "btn_add_doc"):
            self.btn_add_doc.clicked.connect(self.add_doc)
        if hasattr(self, "btn_remove_doc"):
            self.btn_remove_doc.clicked.connect(self.remove_selected_docs)
        if hasattr(self, "btn_open_doc"):
            self.btn_open_doc.clicked.connect(self.open_selected_doc)
        if hasattr(self, "btn_export_excel"):
            self.btn_export_excel.clicked.connect(self.export_excel)
        if hasattr(self, "btn_export_pdf"):
            self.btn_export_pdf.clicked.connect(self.export_pdf)
        if hasattr(self, "btn_print"):
            self.btn_print.clicked.connect(self.export_pdf)

        try:
            tbl = getattr(self, "tbl_hakedis", None)
            if tbl is not None and tbl.selectionModel() is not None:
                tbl.selectionModel().selectionChanged.connect(self._on_hakedis_selection_changed)
        except Exception:
            pass

        if hasattr(self, "cmb_contract"):
            self.cmb_contract.currentIndexChanged.connect(self._on_contract_changed)
        if hasattr(self, "cmb_service_type"):
            self.cmb_service_type.currentIndexChanged.connect(self._on_service_changed)
        if hasattr(self, "cmb_period"):
            self.cmb_period.currentIndexChanged.connect(self._on_period_changed)

    def _init_defaults(self):
        self._init_filters()
        self.load_table()

    def _init_filters(self):
        self._fill_contracts()
        self._on_contract_changed()

    def _fill_contracts(self):
        cmb = getattr(self, "cmb_contract", None)
        if cmb is None:
            return

        cmb.blockSignals(True)
        try:
            cmb.clear()
            cmb.addItem("Seçiniz...", None)
            conn = self.db.connect()
            if not conn:
                return
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT id, COALESCE(contract_number,'')
                    FROM contracts
                    WHERE COALESCE(is_active,1)=1
                    ORDER BY contract_number
                    """
                )
                for cid, cno in cur.fetchall() or []:
                    cmb.addItem(str(cno), int(cid))
            finally:
                conn.close()
        finally:
            cmb.blockSignals(False)

    def _fill_service_types(self, contract_id: int | None):
        cmb = getattr(self, "cmb_service_type", None)
        if cmb is None:
            return

        cmb.blockSignals(True)
        try:
            cmb.clear()
            cmb.addItem("Seçiniz...", None)
            if not contract_id:
                return

            conn = self.db.connect()
            if not conn:
                return
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT DISTINCT COALESCE(service_type,'')
                    FROM route_params
                    WHERE contract_id=?
                      AND COALESCE(service_type,'') <> ''
                    ORDER BY service_type
                    """,
                    (int(contract_id),),
                )
                for (st,) in cur.fetchall() or []:
                    cmb.addItem(str(st), str(st))
            finally:
                conn.close()
        finally:
            cmb.blockSignals(False)

    def _fill_periods(self, contract_id: int | None, service_type: str | None):
        cmb = getattr(self, "cmb_period", None)
        if cmb is None:
            return

        cmb.blockSignals(True)
        try:
            cmb.clear()
            cmb.addItem("Seçiniz...", None)
            if not contract_id or not service_type:
                return

            conn = self.db.connect()
            if not conn:
                return
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT DISTINCT SUBSTR(trip_date, 1, 7) AS ym
                    FROM trip_allocations
                    WHERE contract_id=?
                      AND service_type=?
                      AND COALESCE(trip_date,'') <> ''
                    ORDER BY ym DESC
                    """,
                    (int(contract_id), str(service_type)),
                )
                for (ym,) in cur.fetchall() or []:
                    if ym:
                        cmb.addItem(str(ym), str(ym))
            finally:
                conn.close()
        finally:
            cmb.blockSignals(False)

        try:
            # Eğer user_data içinde active_month varsa onu seçmeye çalış.
            ym = str((self.user_data or {}).get("active_month") or "").strip()
            if ym and hasattr(self, "cmb_period"):
                idx = self.cmb_period.findData(ym)
                if idx >= 0:
                    self.cmb_period.setCurrentIndex(idx)
        except Exception:
            pass

    def _fill_routes(self, contract_id: int | None, service_type: str | None):
        cmb = getattr(self, "cmb_route", None)
        if cmb is None:
            return

        cmb.blockSignals(True)
        try:
            cmb.clear()
            cmb.addItem("Tümü", None)
            if not contract_id or not service_type:
                return

            rows = self.db.get_route_params_for_contract(int(contract_id), str(service_type))
            for rid, route_name, stops, dist_km, *_rest in rows or []:
                txt = str(route_name or "").strip()
                if not txt:
                    txt = f"ID {rid}"
                cmb.addItem(txt, int(rid))
        finally:
            cmb.blockSignals(False)

    def _on_contract_changed(self, *_args):
        contract_id = None
        try:
            contract_id = self._safe_combo_data(getattr(self, "cmb_contract", None))
            if contract_id is not None:
                contract_id = int(contract_id)
        except Exception:
            contract_id = None

        self._fill_service_types(contract_id)
        self._fill_periods(contract_id, None)
        self._fill_routes(contract_id, None)

    def _on_service_changed(self, *_args):
        contract_id = None
        try:
            contract_id = self._safe_combo_data(getattr(self, "cmb_contract", None))
            if contract_id is not None:
                contract_id = int(contract_id)
        except Exception:
            contract_id = None

        service_type = None
        try:
            service_type = self._safe_combo_data(getattr(self, "cmb_service_type", None))
        except Exception:
            service_type = None

        self._fill_periods(contract_id, str(service_type) if service_type else None)
        self._fill_routes(contract_id, str(service_type) if service_type else None)

    def _on_period_changed(self, *_args):
        # şimdilik bir şey yapmıyoruz; ileride otomatik listeleme eklenebilir.
        pass

    def _safe_combo_data(self, cmb):
        if cmb is None:
            return None
        try:
            data = cmb.currentData()
            if data is not None and str(data).strip() != "":
                return data
        except Exception:
            pass
        try:
            txt = str(cmb.currentText() or "").strip()
            return txt if txt else None
        except Exception:
            return None

    def _reselect_by_id(self, hakedis_id: int | None):
        if not hakedis_id:
            return
        tbl = getattr(self, "tbl_hakedis", None)
        if tbl is None:
            return
        try:
            for r in range(tbl.rowCount()):
                it = tbl.item(r, 0)
                if it is None:
                    continue
                if str(it.text() or "").strip() == str(int(hakedis_id)):
                    tbl.setCurrentCell(r, 1)
                    return
        except Exception:
            return

    def approve_selected(self):
        hid = self._selected_hakedis_id()
        if not hid:
            self._set_status("Onay için hakediş seçmelisin")
            return
        ok = self.db.set_hakedis_status(int(hid), "ONAYLANDI")
        if not ok:
            self._set_status("Onaylama başarısız")
            return
        self._set_status("Onaylandı")
        self.load_table()
        self._reselect_by_id(hid)

    def invoice_selected(self):
        hid = self._selected_hakedis_id()
        if not hid:
            self._set_status("Faturalandı için hakediş seçmelisin")
            return
        ok = self.db.set_hakedis_status(int(hid), "FATURALANDI")
        if not ok:
            self._set_status("Faturalandı güncellemesi başarısız")
            return
        self._set_status("Faturalandı")
        self.load_table()
        self._reselect_by_id(hid)

    def load_table(self):
        tbl = getattr(self, "tbl_hakedis", None)
        if tbl is None:
            return

        contract_id = None
        period = None
        service_type = None
        route_params_id = None
        status = None
        only_missing_docs = False

        try:
            contract_id = self._safe_combo_data(getattr(self, "cmb_contract", None))
            if contract_id is not None and str(contract_id).isdigit():
                contract_id = int(contract_id)
            else:
                contract_id = None
        except Exception:
            contract_id = None

        try:
            period = self._safe_combo_data(getattr(self, "cmb_period", None))
        except Exception:
            period = None

        try:
            service_type = self._safe_combo_data(getattr(self, "cmb_service_type", None))
        except Exception:
            service_type = None

        try:
            route_params_id = self._safe_combo_data(getattr(self, "cmb_route", None))
            if route_params_id is not None and str(route_params_id).isdigit():
                route_params_id = int(route_params_id)
            else:
                route_params_id = None
        except Exception:
            route_params_id = None

        try:
            status = self._safe_combo_data(getattr(self, "cmb_status", None))
        except Exception:
            status = None

        try:
            chk = getattr(self, "chk_only_missing_docs", None)
            if chk is not None:
                only_missing_docs = bool(chk.isChecked())
        except Exception:
            only_missing_docs = False

        rows = self.db.list_hakedis(
            contract_id=contract_id,
            period=period,
            service_type=service_type,
            route_params_id=route_params_id,
            status=status,
            only_missing_docs=only_missing_docs,
        )

        tbl.setRowCount(0)
        for r_idx, row in enumerate(rows):
            tbl.insertRow(r_idx)
            for c_idx, val in enumerate(row):
                if c_idx >= tbl.columnCount():
                    break
                it = QTableWidgetItem(str(val if val is not None else ""))
                if c_idx in (0,):
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                tbl.setItem(r_idx, c_idx, it)

        try:
            if tbl.columnCount() > 0:
                tbl.setColumnHidden(0, True)
        except Exception:
            pass

        try:
            txt_summary = getattr(self, "txt_summary", None)
            if txt_summary is not None:
                txt_summary.setText(f"{len(rows)} kayıt listelendi")
        except Exception:
            pass

        self._set_status(f"{len(rows)} kayıt listelendi")

        # Liste yenilenince detayları temizle
        self._clear_details()

    def _selected_hakedis_id(self) -> int | None:
        tbl = getattr(self, "tbl_hakedis", None)
        if tbl is None:
            return None
        try:
            r = tbl.currentRow()
            if r is None or r < 0:
                return None
            it = tbl.item(r, 0)
            if it is None:
                return None
            v = str(it.text() or "").strip()
            return int(v) if v.isdigit() else None
        except Exception:
            return None

    def _clear_table(self, t):
        if t is None:
            return
        try:
            t.setRowCount(0)
        except Exception:
            pass

    def _clear_details(self):
        self._clear_table(getattr(self, "tbl_items", None))
        self._clear_table(getattr(self, "tbl_deductions", None))
        self._clear_table(getattr(self, "tbl_docs", None))

    def _on_hakedis_selection_changed(self, *_args):
        hid = self._selected_hakedis_id()
        if not hid:
            self._clear_details()
            return
        self._load_details(hid)

    def _load_details(self, hakedis_id: int):
        self._load_items(hakedis_id)
        self._load_deductions(hakedis_id)
        self._load_docs(hakedis_id)

    def _load_items(self, hakedis_id: int):
        tbl = getattr(self, "tbl_items", None)
        if tbl is None:
            return
        rows = self.db.get_hakedis_items_rows(int(hakedis_id))
        tbl.setRowCount(0)
        for r_idx, row in enumerate(rows or []):
            tbl.insertRow(r_idx)
            for c_idx, val in enumerate(row):
                if c_idx >= tbl.columnCount():
                    break
                it = QTableWidgetItem(str(val if val is not None else ""))
                tbl.setItem(r_idx, c_idx, it)

    def _load_deductions(self, hakedis_id: int):
        tbl = getattr(self, "tbl_deductions", None)
        if tbl is None:
            return
        rows = self.db.get_hakedis_deductions_ui_rows(int(hakedis_id))
        tbl.setRowCount(0)
        for r_idx, row in enumerate(rows or []):
            tbl.insertRow(r_idx)
            # row: (id, type, amount, description)
            did = None
            try:
                did = int(row[0])
            except Exception:
                did = None
            vals = [row[1] if len(row) > 1 else "", row[2] if len(row) > 2 else 0, row[3] if len(row) > 3 else ""]
            for c_idx, val in enumerate(vals):
                if c_idx >= tbl.columnCount():
                    break
                it = QTableWidgetItem(str(val if val is not None else ""))
                if c_idx == 0 and did is not None:
                    it.setData(Qt.ItemDataRole.UserRole + 1, int(did))
                tbl.setItem(r_idx, c_idx, it)

    def _load_docs(self, hakedis_id: int):
        tbl = getattr(self, "tbl_docs", None)
        if tbl is None:
            return
        rows = self.db.get_hakedis_docs_ui_rows(int(hakedis_id))
        tbl.setRowCount(0)
        for r_idx, row in enumerate(rows or []):
            tbl.insertRow(r_idx)
            # row: (id, doc_type, file_name, file_path, uploaded_at, description)
            doc_id = None
            try:
                doc_id = int(row[0])
            except Exception:
                doc_id = None
            doc_type = row[1] if len(row) > 1 else ""
            file_name = row[2] if len(row) > 2 else ""
            file_path = row[3] if len(row) > 3 else ""
            uploaded_at = row[4] if len(row) > 4 else ""
            desc = row[5] if len(row) > 5 else ""
            vals = [doc_type, file_name, file_path, uploaded_at, desc]

            for c_idx, val in enumerate(vals):
                if c_idx >= tbl.columnCount():
                    break
                it = QTableWidgetItem(str(val if val is not None else ""))
                if c_idx == 0:
                    if doc_id is not None:
                        it.setData(Qt.ItemDataRole.UserRole + 1, int(doc_id))
                    it.setData(Qt.ItemDataRole.UserRole + 2, str(file_path or ""))
                tbl.setItem(r_idx, c_idx, it)

    def _month_range(self, ym: str):
        # ym: YYYY-MM
        try:
            d0 = datetime.strptime(str(ym).strip() + "-01", "%Y-%m-%d")
        except Exception:
            return None, None
        if d0.month == 12:
            d1 = datetime(d0.year + 1, 1, 1)
        else:
            d1 = datetime(d0.year, d0.month + 1, 1)
        start = d0.strftime("%Y-%m-%d")
        end = (d1 - __import__("datetime").timedelta(days=1)).strftime("%Y-%m-%d")
        return start, end

    def _parse_money(self, txt: str) -> float:
        s = str(txt or "").strip()
        if not s:
            return 0.0
        s = s.replace(".", "").replace(",", ".")
        try:
            return float(s)
        except Exception:
            return 0.0

    def add_deduction(self):
        hid = self._selected_hakedis_id()
        if not hid:
            self._set_status("Kesinti eklemek için hakediş seçmelisin")
            return

        dtype, ok = QInputDialog.getText(self, "Kesinti", "Kesinti türü:")
        if not ok:
            return
        dtype = str(dtype or "").strip()
        if not dtype:
            self._set_status("Kesinti türü boş olamaz")
            return

        amt_txt, ok = QInputDialog.getText(self, "Kesinti", "Tutar:")
        if not ok:
            return
        amount = self._parse_money(amt_txt)
        if amount <= 0:
            self._set_status("Tutar 0'dan büyük olmalı")
            return

        desc, ok = QInputDialog.getText(self, "Kesinti", "Açıklama:")
        if not ok:
            return

        did = self.db.add_hakedis_deduction(int(hid), dtype, float(amount), str(desc or ""))
        if not did:
            self._set_status("Kesinti eklenemedi")
            return

        self.db.update_hakedis_totals(int(hid))
        self._set_status("Kesinti eklendi")
        self.load_table()
        self._reselect_by_id(hid)
        self._load_deductions(int(hid))

    def remove_selected_deductions(self):
        hid = self._selected_hakedis_id()
        if not hid:
            self._set_status("Kesinti silmek için hakediş seçmelisin")
            return
        tbl = getattr(self, "tbl_deductions", None)
        if tbl is None:
            return

        rows = sorted({it.row() for it in (tbl.selectedItems() or [])}, reverse=True)
        if not rows:
            self._set_status("Silmek için kesinti satırı seçmelisin")
            return

        msg = QMessageBox.question(
            self,
            "Onay",
            "Seçili kesinti(ler) silinsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if msg != QMessageBox.StandardButton.Yes:
            return

        deleted_any = False
        for r in rows:
            it0 = tbl.item(r, 0)
            did = None
            try:
                did = it0.data(Qt.ItemDataRole.UserRole + 1) if it0 else None
            except Exception:
                did = None
            if did is None:
                continue
            if self.db.delete_hakedis_deduction(int(did)):
                deleted_any = True

        if deleted_any:
            self.db.update_hakedis_totals(int(hid))
            self._set_status("Kesinti silindi")
            self.load_table()
            self._reselect_by_id(hid)
            self._load_deductions(int(hid))
        else:
            self._set_status("Kesinti silinemedi")

    def _selected_doc_meta(self):
        tbl = getattr(self, "tbl_docs", None)
        if tbl is None:
            return None, None
        try:
            r = tbl.currentRow()
            if r is None or r < 0:
                return None, None
            it0 = tbl.item(r, 0)
            if it0 is None:
                return None, None
            doc_id = it0.data(Qt.ItemDataRole.UserRole + 1)
            path = it0.data(Qt.ItemDataRole.UserRole + 2)
            return (int(doc_id) if doc_id is not None else None), (str(path) if path is not None else "")
        except Exception:
            return None, None

    def add_doc(self):
        hid = self._selected_hakedis_id()
        if not hid:
            self._set_status("Belge eklemek için hakediş seçmelisin")
            return

        doc_type, ok = QInputDialog.getText(self, "Belge", "Belge türü:")
        if not ok:
            return
        doc_type = str(doc_type or "").strip()
        if not doc_type:
            self._set_status("Belge türü boş olamaz")
            return

        desc, ok = QInputDialog.getText(self, "Belge", "Açıklama:")
        if not ok:
            return

        file_path, _ = QFileDialog.getOpenFileName(self, "Belge seç", "", "Tüm Dosyalar (*.*)")
        if not file_path:
            return

        file_name = os.path.basename(file_path)
        uploaded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        doc_id = self.db.add_hakedis_doc(
            int(hid),
            str(doc_type),
            str(file_name),
            str(file_path),
            str(uploaded_at),
            str(desc or ""),
        )
        if not doc_id:
            self._set_status("Belge eklenemedi")
            return
        self._set_status("Belge eklendi")
        self._load_docs(int(hid))

    def remove_selected_docs(self):
        hid = self._selected_hakedis_id()
        if not hid:
            self._set_status("Belge silmek için hakediş seçmelisin")
            return
        tbl = getattr(self, "tbl_docs", None)
        if tbl is None:
            return

        rows = sorted({it.row() for it in (tbl.selectedItems() or [])}, reverse=True)
        if not rows:
            self._set_status("Silmek için belge satırı seçmelisin")
            return

        msg = QMessageBox.question(
            self,
            "Onay",
            "Seçili belge(ler) silinsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if msg != QMessageBox.StandardButton.Yes:
            return

        deleted_any = False
        for r in rows:
            it0 = tbl.item(r, 0)
            doc_id = None
            try:
                doc_id = it0.data(Qt.ItemDataRole.UserRole + 1) if it0 else None
            except Exception:
                doc_id = None
            if doc_id is None:
                continue
            if self.db.delete_hakedis_doc(int(doc_id)):
                deleted_any = True

        if deleted_any:
            self._set_status("Belge silindi")
            self._load_docs(int(hid))
        else:
            self._set_status("Belge silinemedi")

    def open_selected_doc(self):
        _doc_id, path = self._selected_doc_meta()
        path = str(path or "").strip()
        if not path:
            self._set_status("Açmak için belge seçmelisin")
            return
        if not os.path.exists(path):
            self._set_status("Dosya bulunamadı")
            return
        try:
            os.startfile(path)  # type: ignore[attr-defined]
            return
        except Exception:
            pass
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception:
            self._set_status("Dosya açılamadı")

    def _build_export_table_from(self, src_tbl: QTableWidget) -> QTableWidget:
        export_table = QTableWidget()
        export_table.setColumnCount(src_tbl.columnCount())

        headers = []
        for c in range(src_tbl.columnCount()):
            h = src_tbl.horizontalHeaderItem(c)
            headers.append(h.text() if h else "")
        export_table.setHorizontalHeaderLabels(headers)

        visible_rows = [r for r in range(src_tbl.rowCount()) if not src_tbl.isRowHidden(r)]
        export_table.setRowCount(len(visible_rows))

        for out_r, src_r in enumerate(visible_rows):
            for c in range(src_tbl.columnCount()):
                item = src_tbl.item(src_r, c)
                export_table.setItem(out_r, c, QTableWidgetItem(item.text() if item else ""))

        return export_table

    def export_excel(self):
        try:
            from app.utils.excel_utils import create_excel
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Excel modülü yüklenemedi:\n{str(e)}")
            return

        tbl = getattr(self, "tbl_hakedis", None)
        if tbl is None:
            QMessageBox.warning(self, "Uyarı", "Tablo bulunamadı!")
            return

        export_table = self._build_export_table_from(tbl)
        create_excel(export_table, report_title="Hakediş Listesi", username="Admin", parent=self)

    def export_pdf(self):
        try:
            from app.utils.pdf_utils import create_pdf
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"PDF modülü yüklenemedi:\n{str(e)}")
            return

        tbl = getattr(self, "tbl_hakedis", None)
        if tbl is None:
            QMessageBox.warning(self, "Uyarı", "Tablo bulunamadı!")
            return

        export_table = self._build_export_table_from(tbl)
        create_pdf(export_table, report_title="Hakediş Listesi", username="Admin", parent=self)

    def calculate_hakedis(self):
        # MVP hesaplama: trip_allocations + trip_prices kullanarak kalem üret
        contract_id = None
        period = None
        service_type = None
        route_params_id = None

        try:
            contract_id = self._safe_combo_data(getattr(self, "cmb_contract", None))
            if contract_id is not None and str(contract_id).isdigit():
                contract_id = int(contract_id)
            else:
                contract_id = None
        except Exception:
            contract_id = None

        try:
            period = self._safe_combo_data(getattr(self, "cmb_period", None))
        except Exception:
            period = None

        try:
            service_type = self._safe_combo_data(getattr(self, "cmb_service_type", None))
        except Exception:
            service_type = None

        try:
            route_params_id = self._safe_combo_data(getattr(self, "cmb_route", None))
            if route_params_id is not None and str(route_params_id).isdigit():
                route_params_id = int(route_params_id)
            else:
                route_params_id = None
        except Exception:
            route_params_id = None

        if not contract_id or not period or not service_type:
            self._set_status("Hesaplama için Sözleşme + Dönem + Hizmet Türü seçmelisin")
            return

        start_date, end_date = self._month_range(str(period))
        if not start_date or not end_date:
            self._set_status("Dönem formatı hatalı (YYYY-MM bekleniyor)")
            return

        hakedis_id = self.db.upsert_hakedis_header(
            contract_id=int(contract_id),
            period=str(period),
            service_type=str(service_type),
            route_params_id=int(route_params_id) if route_params_id is not None else None,
            status="TASLAK",
        )
        if not hakedis_id:
            self._set_status("Hakediş başlığı oluşturulamadı")
            return

        allocations = self.db.get_trip_allocations_for_range(
            contract_id=int(contract_id),
            service_type=str(service_type),
            start_date=str(start_date),
            end_date=str(end_date),
        )

        def _norm_route_name(s: str) -> str:
            txt = (s or "").strip().lower()
            if not txt:
                return ""
            txt = re.sub(r"\s+", "", txt)
            txt = re.sub(r"[^0-9a-zçğıöşü]", "", txt)
            return txt

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
            return str(raw or "").strip().lower()

        # Fallback price map: route_params_id -> base price from contracts.price_matrix_json
        route_price_by_id: dict[int, float] = {}
        try:
            route_rows = self.db.get_route_params_for_contract(int(contract_id), str(service_type))
        except Exception:
            route_rows = []

        price_json = ""
        try:
            price_json = self.db.get_contract_price_matrix_json(int(contract_id))
        except Exception:
            price_json = ""

        contract_price_by_name_mt: dict[tuple[str, str], float] = {}
        contract_price_by_norm_mt: dict[tuple[str, str], float] = {}
        contract_price_by_name: dict[str, float] = {}
        contract_price_by_norm: dict[str, float] = {}
        ambiguous_names: set[str] = set()

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
                    st = str((rec or {}).get("_service_type") or (rec or {}).get("service_type") or "").strip()
                    if st and st.lower() != str(service_type).strip().lower():
                        continue
                    mt = _extract_movement_type(rec or {})
                    try:
                        pr = float((rec or {}).get("fiyat") or 0.0)
                    except Exception:
                        pr = 0.0

                    if guz in contract_price_by_name:
                        ambiguous_names.add(guz)
                    else:
                        contract_price_by_name[guz] = pr

                    ng = _norm_route_name(guz)
                    if ng:
                        if ng in contract_price_by_norm:
                            ambiguous_names.add(guz)
                        else:
                            contract_price_by_norm[ng] = pr

                    contract_price_by_name_mt[(guz, mt)] = pr
                    if ng:
                        contract_price_by_norm_mt[(ng, mt)] = pr

        if route_rows and (contract_price_by_name_mt or contract_price_by_norm_mt or contract_price_by_name or contract_price_by_norm):
            for rr in route_rows or []:
                try:
                    rid = int(rr[0] or 0)
                    rname = str(rr[1] if len(rr) > 1 else "").strip().lower()
                    mt_r = str(rr[4] if len(rr) > 4 else "").strip().lower()
                except Exception:
                    continue
                if rid <= 0 or not rname:
                    continue

                pr = None
                if mt_r and (rname, mt_r) in contract_price_by_name_mt:
                    pr = float(contract_price_by_name_mt.get((rname, mt_r)) or 0.0)
                elif rname in contract_price_by_name and rname not in ambiguous_names:
                    pr = float(contract_price_by_name.get(rname) or 0.0)
                else:
                    nrn = _norm_route_name(rname)
                    if mt_r and nrn and (nrn, mt_r) in contract_price_by_norm_mt:
                        pr = float(contract_price_by_norm_mt.get((nrn, mt_r)) or 0.0)
                    elif nrn and nrn in contract_price_by_norm and rname not in ambiguous_names:
                        pr = float(contract_price_by_norm.get(nrn) or 0.0)

                if pr is not None:
                    route_price_by_id[int(rid)] = float(pr or 0.0)

        # price map: (route_params_id, time_block) -> price
        prices = self.db.get_trip_prices_for_month(int(contract_id), str(period), str(service_type))
        price_map = {(int(rid), str(tb)): float(p or 0) for rid, tb, p in (prices or [])}

        items = []
        missing_price_keys: set[tuple[int, str]] = set()
        for rid, trip_date, time_block, line_no, vehicle_id, driver_id, qty, time_text, note in allocations or []:
            try:
                rid_int = int(rid)
            except Exception:
                continue
            if route_params_id is not None and int(route_params_id) != rid_int:
                continue

            qty_f = float(qty or 0)
            unit_price = float(price_map.get((rid_int, str(time_block)), 0) or 0)
            if unit_price <= 0:
                try:
                    unit_price = float(route_price_by_id.get(int(rid_int), 0.0) or 0.0)
                except Exception:
                    unit_price = 0.0
            if qty_f > 0 and unit_price <= 0:
                try:
                    missing_price_keys.add((int(rid_int), str(time_block or "")))
                except Exception:
                    pass
            amount = float(qty_f * unit_price)

            items.append(
                {
                    "item_date": str(trip_date or ""),
                    "route_params_id": rid_int,
                    "vehicle_id": vehicle_id,
                    "driver_id": driver_id,
                    "work_type": str(time_block or ""),
                    "quantity": qty_f,
                    "unit_price": unit_price,
                    "amount": amount,
                    "description": str(time_text or ""),
                    "source_trip_id": None,
                }
            )

        # --- GİDER: TAŞERON ARACI kalemlerini taşeron sözleşmeleri altında hesapla ---
        # Model seçimi: gider hakedişi taşeron sözleşmesi altında saklanacak.
        subcontract_items_by_contract: dict[int, list[dict]] = {}
        subcontract_missing_contract: set[tuple[int, str]] = set()  # (vehicle_id, trip_date)
        subcontract_missing_supplier: set[int] = set()  # vehicle_id
        subcontract_missing_route_map: set[tuple[int, int]] = set()  # (sub_contract_id, main_route_params_id)

        # Cache route rows for main contract for mapping purposes
        main_route_rows = route_rows or []
        main_route_info_by_id: dict[int, tuple[str, str]] = {}
        for rr in main_route_rows:
            try:
                rid0 = int(rr[0] or 0)
                rn0 = str(rr[1] if len(rr) > 1 else "").strip().lower()
                mt0 = str(rr[4] if len(rr) > 4 else "").strip().lower()
            except Exception:
                continue
            if rid0 > 0:
                main_route_info_by_id[rid0] = (rn0, mt0)

        # Per subcontract contract caches: route mapping + price maps
        sub_route_map_by_contract: dict[int, dict[int, int]] = {}
        sub_price_map_by_contract: dict[int, dict[tuple[int, str], float]] = {}
        sub_route_price_by_id_by_contract: dict[int, dict[int, float]] = {}

        def _get_sub_route_map(sub_contract_id: int) -> dict[int, int]:
            if int(sub_contract_id) in sub_route_map_by_contract:
                return sub_route_map_by_contract[int(sub_contract_id)]

            try:
                sub_rows = self.db.get_route_params_for_contract(int(sub_contract_id), str(service_type))
            except Exception:
                sub_rows = []

            # Build lookup on subcontract routes: (norm_name, movement_type) -> route_id
            sub_by_key: dict[tuple[str, str], int] = {}
            sub_by_name: dict[str, int] = {}
            for r in sub_rows or []:
                try:
                    rid_s = int(r[0] or 0)
                    name_s = str(r[1] if len(r) > 1 else "").strip().lower()
                    mt_s = str(r[4] if len(r) > 4 else "").strip().lower()
                except Exception:
                    continue
                if rid_s <= 0 or not name_s:
                    continue
                sub_by_key[(_norm_route_name(name_s), mt_s)] = rid_s
                # fallback map: only name (norm)
                sub_by_name[_norm_route_name(name_s)] = rid_s

            out: dict[int, int] = {}
            for mid, (mname, mmt) in main_route_info_by_id.items():
                key = (_norm_route_name(mname), str(mmt or ""))
                if key in sub_by_key:
                    out[int(mid)] = int(sub_by_key[key])
                else:
                    nn = _norm_route_name(mname)
                    if nn and nn in sub_by_name:
                        out[int(mid)] = int(sub_by_name[nn])

            sub_route_map_by_contract[int(sub_contract_id)] = out
            return out

        def _ensure_sub_prices(sub_contract_id: int) -> None:
            cid = int(sub_contract_id)
            if cid in sub_price_map_by_contract and cid in sub_route_price_by_id_by_contract:
                return

            # trip_prices for subcontract contract
            try:
                prices2 = self.db.get_trip_prices_for_month(cid, str(period), str(service_type))
            except Exception:
                prices2 = []
            sub_price_map_by_contract[cid] = {
                (int(rid), str(tb)): float(p or 0) for rid, tb, p in (prices2 or [])
            }

            # price_matrix_json fallback for subcontract contract
            try:
                price_json2 = self.db.get_contract_price_matrix_json(cid)
            except Exception:
                price_json2 = ""

            # Route base price map for subcontract contract: route_params_id -> price
            route_price_by_id2: dict[int, float] = {}
            try:
                sub_route_rows = self.db.get_route_params_for_contract(cid, str(service_type))
            except Exception:
                sub_route_rows = []

            contract_price_by_name_mt2: dict[tuple[str, str], float] = {}
            contract_price_by_norm_mt2: dict[tuple[str, str], float] = {}
            contract_price_by_name2: dict[str, float] = {}
            contract_price_by_norm2: dict[str, float] = {}
            ambiguous_names2: set[str] = set()

            if price_json2:
                try:
                    parsed2 = json.loads(price_json2)
                except Exception:
                    parsed2 = []
                if isinstance(parsed2, list):
                    for rec in parsed2:
                        guz2 = str((rec or {}).get("guzergah") or "").strip().lower()
                        if not guz2:
                            continue
                        st2 = str((rec or {}).get("_service_type") or (rec or {}).get("service_type") or "").strip()
                        if st2 and st2.lower() != str(service_type).strip().lower():
                            continue
                        mt2 = _extract_movement_type(rec or {})
                        try:
                            pr2 = float((rec or {}).get("fiyat") or 0.0)
                        except Exception:
                            pr2 = 0.0

                        if guz2 in contract_price_by_name2:
                            ambiguous_names2.add(guz2)
                        else:
                            contract_price_by_name2[guz2] = pr2

                        ng2 = _norm_route_name(guz2)
                        if ng2:
                            if ng2 in contract_price_by_norm2:
                                ambiguous_names2.add(guz2)
                            else:
                                contract_price_by_norm2[ng2] = pr2

                        contract_price_by_name_mt2[(guz2, mt2)] = pr2
                        if ng2:
                            contract_price_by_norm_mt2[(ng2, mt2)] = pr2

            if sub_route_rows and (
                contract_price_by_name_mt2
                or contract_price_by_norm_mt2
                or contract_price_by_name2
                or contract_price_by_norm2
            ):
                for rr2 in sub_route_rows or []:
                    try:
                        rid2 = int(rr2[0] or 0)
                        rname2 = str(rr2[1] if len(rr2) > 1 else "").strip().lower()
                        mt_r2 = str(rr2[4] if len(rr2) > 4 else "").strip().lower()
                    except Exception:
                        continue
                    if rid2 <= 0 or not rname2:
                        continue

                    pr = None
                    if mt_r2 and (rname2, mt_r2) in contract_price_by_name_mt2:
                        pr = float(contract_price_by_name_mt2.get((rname2, mt_r2)) or 0.0)
                    elif rname2 in contract_price_by_name2 and rname2 not in ambiguous_names2:
                        pr = float(contract_price_by_name2.get(rname2) or 0.0)
                    else:
                        nrn2 = _norm_route_name(rname2)
                        if mt_r2 and nrn2 and (nrn2, mt_r2) in contract_price_by_norm_mt2:
                            pr = float(contract_price_by_norm_mt2.get((nrn2, mt_r2)) or 0.0)
                        elif nrn2 and nrn2 in contract_price_by_norm2 and rname2 not in ambiguous_names2:
                            pr = float(contract_price_by_norm2.get(nrn2) or 0.0)

                    if pr is not None:
                        route_price_by_id2[int(rid2)] = float(pr or 0.0)

            sub_route_price_by_id_by_contract[cid] = route_price_by_id2

        for rid, trip_date, time_block, line_no, vehicle_id, driver_id, qty, time_text, note in allocations or []:
            if vehicle_id is None:
                continue
            try:
                arac_turu, supplier_customer_id = self.db.get_vehicle_subcontract_meta(int(vehicle_id))
            except Exception:
                arac_turu, supplier_customer_id = ("", None)

            at = str(arac_turu or "").strip().upper()
            if at != "TAŞERON ARACI" and at != "TASERON ARACI":
                continue

            if supplier_customer_id is None:
                try:
                    subcontract_missing_supplier.add(int(vehicle_id))
                except Exception:
                    pass
                continue

            sub_contract_id = None
            try:
                sub_contract_id = self.db.resolve_subcontract_contract_id(
                    int(contract_id), int(supplier_customer_id), str(trip_date or "")
                )
            except Exception:
                sub_contract_id = None

            if not sub_contract_id:
                try:
                    subcontract_missing_contract.add((int(vehicle_id), str(trip_date or "")))
                except Exception:
                    pass
                continue

            try:
                rid_int = int(rid)
            except Exception:
                continue

            # Apply route filter (selected on main contract) to expense too.
            if route_params_id is not None and int(route_params_id) != rid_int:
                continue

            sub_route_map = _get_sub_route_map(int(sub_contract_id))
            sub_rid = int(sub_route_map.get(int(rid_int), 0) or 0)

            if sub_rid <= 0:
                try:
                    subcontract_missing_route_map.add((int(sub_contract_id), int(rid_int)))
                except Exception:
                    pass

            _ensure_sub_prices(int(sub_contract_id))
            sub_price_map = sub_price_map_by_contract.get(int(sub_contract_id), {})
            sub_route_price_by_id = sub_route_price_by_id_by_contract.get(int(sub_contract_id), {})

            qty_f = float(qty or 0)
            unit_price = 0.0
            if sub_rid > 0:
                unit_price = float(sub_price_map.get((int(sub_rid), str(time_block)), 0) or 0)
                if unit_price <= 0:
                    unit_price = float(sub_route_price_by_id.get(int(sub_rid), 0.0) or 0.0)

            if qty_f > 0 and unit_price <= 0:
                try:
                    if sub_rid > 0:
                        missing_price_keys.add((int(sub_rid), str(time_block or "")))
                except Exception:
                    pass

            amount = float(qty_f * unit_price)

            subcontract_items_by_contract.setdefault(int(sub_contract_id), []).append(
                {
                    "item_date": str(trip_date or ""),
                    "route_params_id": int(sub_rid) if sub_rid > 0 else None,
                    "vehicle_id": vehicle_id,
                    "driver_id": driver_id,
                    "work_type": str(time_block or ""),
                    "quantity": qty_f,
                    "unit_price": unit_price,
                    "amount": amount,
                    "description": str(time_text or ""),
                    "source_trip_id": None,
                }
            )

        if missing_price_keys:
            try:
                sample = sorted(missing_price_keys)[:10]
                sample_txt = "\n".join([f"- rota_id={rid} time_block={tb}" for rid, tb in sample])
                more = "" if len(missing_price_keys) <= 10 else f"\n... (+{len(missing_price_keys) - 10} adet daha)"
                msg = (
                    "Bazı seferlerde fiyat bulunamadı (unit_price=0).\n"
                    "Bu kalemler 0 tutarla hesaplanacak. Devam edilsin mi?\n\n"
                    f"Örnekler:\n{sample_txt}{more}"
                )
                ans = QMessageBox.question(
                    self,
                    "Eksik Fiyat",
                    msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if ans != QMessageBox.StandardButton.Yes:
                    self._set_status("Hesaplama iptal edildi (eksik fiyat)")
                    return
            except Exception:
                # UI sorusu çıkamazsa yine de sessiz iptal etmeyelim; hesaplamaya devam.
                pass

        ok = self.db.replace_hakedis_items(int(hakedis_id), items)
        if not ok:
            self._set_status("Kalemler kaydedilemedi")
            return

        self.db.update_hakedis_totals(int(hakedis_id))
        # Subcontract expense hakedis writeback
        created_expense_headers = 0
        for sub_cid, sub_items in (subcontract_items_by_contract or {}).items():
            try:
                sub_hakedis_id = self.db.upsert_hakedis_header(
                    contract_id=int(sub_cid),
                    period=str(period),
                    service_type=str(service_type),
                    route_params_id=None,
                    status="TASLAK",
                )
            except Exception:
                sub_hakedis_id = None

            if not sub_hakedis_id:
                continue

            try:
                ok2 = self.db.replace_hakedis_items(int(sub_hakedis_id), sub_items)
            except Exception:
                ok2 = False
            if not ok2:
                continue
            try:
                self.db.update_hakedis_totals(int(sub_hakedis_id))
            except Exception:
                pass
            created_expense_headers += 1

        warn_parts = []
        if subcontract_missing_supplier:
            warn_parts.append(
                f"Alt Yüklenici seçilmemiş TAŞERON ARACI var: {len(subcontract_missing_supplier)} adet (Araçlar modülünde Alt Yük. seçiniz)."
            )
        if subcontract_missing_contract:
            warn_parts.append(
                f"Bazı taşeron satırlarında uygun taşeron sözleşmesi bulunamadı: {len(subcontract_missing_contract)} adet."
            )
        if subcontract_missing_route_map:
            warn_parts.append(
                f"Bazı taşeron sözleşmelerinde rota eşlemesi bulunamadı (route_params): {len(subcontract_missing_route_map)} adet. (Rotalar modülünde taşeron sözleşmesi rotalarını ekleyin)"
            )

        if warn_parts:
            try:
                QMessageBox.warning(self, "Gider Hakedişi Uyarı", "\n\n".join(warn_parts))
            except Exception:
                pass

        self._set_status(
            f"Hesaplandı: {len(items)} gelir kalemi, {created_expense_headers} taşeron hakedişi oluşturuldu (Giderleri görmek için taşeron sözleşmesini seçin)"
        )
        self.load_table()

        # Hesaplama sonrası ilgili satırı seçip detayları otomatik yükle
        try:
            self._reselect_by_id(int(hakedis_id))
            self._load_details(int(hakedis_id))
        except Exception:
            pass
