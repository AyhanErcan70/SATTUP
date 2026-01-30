from __future__ import annotations

import os
from datetime import datetime

from PyQt6 import uic
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMessageBox, QTableWidget, QTableWidgetItem, QWidget

from app.core.db_manager import DatabaseManager
from app.utils.style_utils import clear_all_styles
from config import get_ui_path


class HakedisApp(QWidget):
    def __init__(self, parent=None, user_data=None, db: DatabaseManager | None = None):
        super().__init__(parent)
        uic.loadUi(get_ui_path("hakedis_window.ui"), self)
        clear_all_styles(self)

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

        # price map: (route_params_id, time_block) -> price
        prices = self.db.get_trip_prices_for_month(int(contract_id), str(period), str(service_type))
        price_map = {(int(rid), str(tb)): float(p or 0) for rid, tb, p in (prices or [])}

        items = []
        for rid, trip_date, time_block, vehicle_id, driver_id, qty, time_text, note in allocations or []:
            try:
                rid_int = int(rid)
            except Exception:
                continue
            if route_params_id is not None and int(route_params_id) != rid_int:
                continue

            qty_f = float(qty or 0)
            unit_price = float(price_map.get((rid_int, str(time_block)), 0) or 0)
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

        ok = self.db.replace_hakedis_items(int(hakedis_id), items)
        if not ok:
            self._set_status("Kalemler kaydedilemedi")
            return

        self.db.update_hakedis_totals(int(hakedis_id))
        self._set_status(f"Hesaplandı: {len(items)} kalem")
        self.load_table()
