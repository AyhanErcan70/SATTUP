from PyQt6 import uic
from PyQt6.QtCore import QDate, Qt, QRegularExpression
from PyQt6.QtGui import QIntValidator, QRegularExpressionValidator
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QDialog, QWidget, QMessageBox, QTableWidgetItem, QHeaderView
from app.core.db_manager import DatabaseManager
from config import get_ui_path
import json
from datetime import datetime

class ContractsApp(QWidget):
    def __init__(self, user_data=None, parent=None):
        super().__init__(parent)
        uic.loadUi(get_ui_path("contracts_window.ui"), self)
        self.setObjectName("main_form")
        self.db = DatabaseManager()
        self.user_data = user_data or {}
        self.current_number = None
        self._price_matrix_cache = []
        self._tarife_loading = False
        if hasattr(self, "txt_sozlesme_kodu"):
            self.txt_sozlesme_kodu.setReadOnly(True)
            self.txt_sozlesme_kodu.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if hasattr(self, "txt_arac_adedi"):
            self.txt_arac_adedi.setValidator(QIntValidator(0, 999))
        if hasattr(self, "txt_toplam_tutar"):
            self.txt_toplam_tutar.setValidator(QRegularExpressionValidator(QRegularExpression(r"^[0-9]+([\\.,][0-9]{1,2})?$")))
        if hasattr(self, "txt_kdv_orani"):
            self.txt_kdv_orani.setValidator(QIntValidator(0, 100))
        self._init_dates()
        self._init_combos()
        self._init_price_table()
        self._init_tarife_tab()
        self._setup_connections()
        self._assign_next_number()
        self.load_table()

    def _get_price_table(self):
        if hasattr(self, "table_fiyatlar"):
            return getattr(self, "table_fiyatlar")
        if hasattr(self, "table_fiyat"):
            return getattr(self, "table_fiyat")
        if hasattr(self, "tableWidget"):
            return getattr(self, "tableWidget")
        return None

    def _get_btn_fiyat_ekle(self):
        if hasattr(self, "btn_fiyat_ekle"):
            return getattr(self, "btn_fiyat_ekle")
        if hasattr(self, "toolButton"):
            return getattr(self, "toolButton")
        return None

    def _get_btn_fiyat_sil(self):
        if hasattr(self, "btn_fiyat_sil"):
            return getattr(self, "btn_fiyat_sil")
        if hasattr(self, "toolButton_2"):
            return getattr(self, "toolButton_2")
        return None

    def _get_contracts_table(self):
        if hasattr(self, "tbl_sozlesmeler"):
            return getattr(self, "tbl_sozlesmeler")
        if hasattr(self, "table_View"):
            return getattr(self, "table_View")
        return None

    def _init_price_table(self):
        tbl = self._get_price_table()
        if tbl is None:
            return

        headers = ["GÜZERGAH", "GİDİŞ GELİŞ", "KM", "FİYAT"]
        tbl.setColumnCount(len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.verticalHeader().setVisible(False)
        tbl.setAlternatingRowColors(True)
        tbl.setSelectionBehavior(tbl.SelectionBehavior.SelectRows)
        tbl.setSelectionMode(tbl.SelectionMode.ExtendedSelection)

        h = tbl.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        # Kullanıcı fiyatı tablo üzerinden belirleyecek -> toplam otomatik hesaplanır
        if hasattr(self, "txt_toplam_tutar"):
            try:
                self.txt_toplam_tutar.setReadOnly(True)
            except Exception:
                pass

        # Varsayılan ilk satır
        if tbl.rowCount() == 0:
            self._price_add_row()

        self._recalc_price_total()

    def _init_dates(self):
        for name in ["date_baslangic", "date_bitis"]:
            w = getattr(self, name, None)
            if w is None:
                continue
            w.setCalendarPopup(True)
            w.setDisplayFormat("dd.MM.yyyy")
            w.setDate(QDate.currentDate())

    def _init_combos(self):
        # Yeni UI'da combo item'ları .ui içinde tanımlı olabilir; boş değilse ezmeyelim.
        if hasattr(self, "cmb_hizmet_tipi"):
            if self.cmb_hizmet_tipi.count() == 0:
                self.cmb_hizmet_tipi.addItem("Seçiniz...")
                self.cmb_hizmet_tipi.addItems(["ÖĞRENCİ TAŞIMA", "PERSONEL TAŞIMA", "ARAÇ KİRALAMA", "DİĞER"])
        if hasattr(self, "cmb_ucret_tipi"):
            if self.cmb_ucret_tipi.count() == 0:
                self.cmb_ucret_tipi.addItem("Seçiniz...")
                self.cmb_ucret_tipi.addItems(["AYLIK", "GÜNLÜK", "SEFER BAŞI"])
        if hasattr(self, "cmb_musteri"):
            self.cmb_musteri.clear()
            self.cmb_musteri.addItem("Seçiniz...")
            self._load_customers()

    def _load_customers(self):
        items = []
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute("SELECT id, COALESCE(title, '') FROM customers WHERE is_active = 1 ORDER BY title")
            items = cursor.fetchall()
            conn.close()
        except Exception:
            items = []
            
        for _id, title in items:
            
            self.cmb_musteri.addItem(title or "", _id)

    def _setup_connections(self):
        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.clicked.connect(self.save)
        if hasattr(self, "btn_temizle"):
            self.btn_temizle.clicked.connect(self.clear_form)
        if hasattr(self, "btn_sil"):
            self.btn_sil.clicked.connect(self._delete_selected)
        if hasattr(self, "btn_kalem_ekle"):
            self.btn_kalem_ekle.clicked.connect(self._open_hat_dialog)
        if hasattr(self, "txt_toplam_tutar"):
            self.txt_toplam_tutar.textChanged.connect(self._update_kdv_total)
        if hasattr(self, "txt_kdv_orani"):
            self.txt_kdv_orani.textChanged.connect(self._update_kdv_total)

        btn_add = self._get_btn_fiyat_ekle()
        if btn_add is not None:
            btn_add.clicked.connect(self._price_add_row)
        btn_del = self._get_btn_fiyat_sil()
        if btn_del is not None:
            btn_del.clicked.connect(self._price_delete_row)

        tbl = self._get_price_table()
        if tbl is not None:
            tbl.cellChanged.connect(self._recalc_price_total)

        list_tbl = self._get_contracts_table()
        if list_tbl is not None:
            list_tbl.doubleClicked.connect(self.select_contract)

        if hasattr(self, "cmb_tarife_period"):
            try:
                self.cmb_tarife_period.currentIndexChanged.connect(self._tarife_reload)
            except Exception:
                pass
        if hasattr(self, "cmb_tarife_service_type"):
            try:
                self.cmb_tarife_service_type.currentIndexChanged.connect(self._tarife_reload)
            except Exception:
                pass
        if hasattr(self, "btn_special_add"):
            try:
                self.btn_special_add.clicked.connect(self._tarife_add_special_row)
            except Exception:
                pass
        if hasattr(self, "btn_special_delete"):
            try:
                self.btn_special_delete.clicked.connect(self._tarife_delete_special_row)
            except Exception:
                pass
        if hasattr(self, "btn_special_save"):
            try:
                self.btn_special_save.clicked.connect(self._tarife_save_special_items)
            except Exception:
                pass

        if hasattr(self, "btn_tarife_save"):
            try:
                self.btn_tarife_save.clicked.connect(self._tarife_save_prices)
            except Exception:
                pass
        if hasattr(self, "date_tarife_effective_from"):
            try:
                self.date_tarife_effective_from.dateChanged.connect(self._tarife_reload)
            except Exception:
                pass

    def _tarife_effective_from_iso(self) -> str | None:
        if not hasattr(self, "date_tarife_effective_from"):
            return None
        try:
            qd = self.date_tarife_effective_from.date()
            return qd.toString("yyyy-MM-dd")
        except Exception:
            return None

    def _tarife_setup_price_table(self, pricing_model: str):
        tbl = getattr(self, "tbl_tarife_prices", None)
        if tbl is None:
            return

        pm = str(pricing_model or "").strip().upper()
        if pm not in ("VARDIYALI", "VARDIYASIZ"):
            pm = "VARDIYALI"

        if pm == "VARDIYALI":
            # categories shown in this order; CIFT is computed
            self._tarife_price_categories = ["TEK_SERVIS", "PAKET_SERVIS", "MESAI"]
            headers = [
                "GÜZERGAH",
                "HAREKET TÜRÜ",
                "KM",
                "TEK",
                "PAKET",
                "MESAI",
                "A.Y.TEK",
                "A.Y.PAKET",
                "A.Y.MESAI",
            ]
        else:
            self._tarife_price_categories = ["TEK_SERVIS", "CIFT_SERVIS", "MESAI"]
            headers = [
                "GÜZERGAH",
                "HAREKET TÜRÜ",
                "KM",
                "TEK",
                "ÇİFT",
                "MESAI",
                "A.Y.TEK",
                "A.Y.ÇİFT",
                "A.Y.MESAI",
            ]

        try:
            tbl.setColumnCount(len(headers))
            tbl.setHorizontalHeaderLabels(headers)
            h = tbl.horizontalHeader()
            h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

            # Column widths
            try:
                tbl.setColumnWidth(0, 260)
                tbl.setColumnWidth(1, 140)
                tbl.setColumnWidth(2, 70)
            except Exception:
                pass

            # Numeric columns fixed width (~10-11 chars like 11.000,00)
            for c in range(3, len(headers)):
                try:
                    h.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
                    tbl.setColumnWidth(c, 95)
                except Exception:
                    pass
        except Exception:
            pass

    def _tarife_load_price_rows(self):
        tbl = getattr(self, "tbl_tarife_prices", None)
        if tbl is None:
            return

        contract_id, _period, service_type = self._tarife_context()
        if not contract_id or not service_type:
            tbl.setRowCount(0)
            return

        eff = self._tarife_effective_from_iso()
        if not eff:
            tbl.setRowCount(0)
            return

        pm = "VARDIYALI"
        try:
            pm = self.db.get_pricing_model_for_date(int(contract_id), str(eff))
        except Exception:
            pm = "VARDIYALI"
        if hasattr(self, "txt_tarife_pricing_model"):
            try:
                self.txt_tarife_pricing_model.setText(str(pm))
            except Exception:
                pass
        self._tarife_setup_price_table(str(pm))

        # Route list
        route_rows = []
        try:
            route_rows = self.db.get_route_params_for_contract(int(contract_id), str(service_type))
        except Exception:
            route_rows = []

        # Existing tariff map: (route_params_id, pricing_category) -> (price, subcontractor_price)
        tmap: dict[tuple[int, str], tuple[float, float]] = {}
        try:
            rows = self.db.list_trip_tariff_prices_for_effective_from(int(contract_id), str(service_type), str(eff))
            for rid, pc, pr, spr in rows or []:
                try:
                    tmap[(int(rid), str(pc).strip().upper())] = (float(pr or 0.0), float(spr or 0.0))
                except Exception:
                    pass
        except Exception:
            pass

        # If nothing found for selected date, auto-switch to last saved effective_from (better UX on re-entry)
        if not tmap:
            try:
                dates = self.db.list_trip_tariff_effective_from_dates(int(contract_id), str(service_type))
                if dates:
                    last_eff = str(dates[0] or "").strip()
                    if last_eff and last_eff != str(eff):
                        try:
                            dt = datetime.strptime(last_eff, "%Y-%m-%d")
                            self._tarife_loading = True
                            self.date_tarife_effective_from.setDate(QDate(dt.year, dt.month, dt.day))
                        except Exception:
                            pass
                        finally:
                            self._tarife_loading = False
                        # Reload will be triggered by dateChanged; stop here
                        tbl.setRowCount(0)
                        return
            except Exception:
                pass

        tbl.blockSignals(True)
        tbl.setRowCount(0)
        for rr in route_rows or []:
            try:
                rid = int(rr[0])
            except Exception:
                continue
            rname = str(rr[1] if len(rr) > 1 else "")
            stops = str(rr[2] if len(rr) > 2 else "")
            km = rr[3] if len(rr) > 3 else 0
            mv = str(rr[4] if len(rr) > 4 else "")

            r = tbl.rowCount()
            tbl.insertRow(r)

            # col 0: route name
            it0 = QTableWidgetItem(str(rname or ""))
            it0.setData(Qt.ItemDataRole.UserRole + 1, int(rid))
            tbl.setItem(r, 0, it0)
            tbl.setItem(r, 1, QTableWidgetItem(str(mv or "")))
            itkm = QTableWidgetItem("" if km is None else str(km))
            itkm.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tbl.setItem(r, 2, itkm)

            # price columns
            col = 3
            for pc in getattr(self, "_tarife_price_categories", []) or []:
                pr, spr = tmap.get((int(rid), str(pc).upper()), (0.0, 0.0))
                itp = QTableWidgetItem("" if float(pr or 0.0) <= 0 else self._format_money_tr(float(pr or 0.0)))
                itp.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tbl.setItem(r, col, itp)
                col += 1

            # subcontractor price columns per category
            for pc in getattr(self, "_tarife_price_categories", []) or []:
                _pr, spr = tmap.get((int(rid), str(pc).upper()), (0.0, 0.0))
                its = QTableWidgetItem("" if float(spr or 0.0) <= 0 else self._format_money_tr(float(spr or 0.0)))
                its.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tbl.setItem(r, col, its)
                col += 1

        tbl.blockSignals(False)

    def _tarife_save_prices(self):
        tbl = getattr(self, "tbl_tarife_prices", None)
        if tbl is None:
            return

        contract_id, _period, service_type = self._tarife_context()
        if not contract_id:
            QMessageBox.warning(self, "Uyarı", "Önce bir sözleşme seçiniz.")
            return
        if not service_type:
            QMessageBox.warning(self, "Uyarı", "Hizmet Tipi seçiniz.")
            return
        eff = self._tarife_effective_from_iso()
        if not eff:
            QMessageBox.warning(self, "Uyarı", "Geçerlilik tarihi seçiniz.")
            return

        pm = "VARDIYALI"
        try:
            pm = self.db.get_pricing_model_for_date(int(contract_id), str(eff))
        except Exception:
            pm = "VARDIYALI"

        categories = list(getattr(self, "_tarife_price_categories", []) or [])
        # col mapping: 0 route,1 mv,2 km, 3.. prices, then 3+len(categories) .. subcontractor prices
        sub_base = 3 + len(categories)

        def _parse_money(s: str) -> float:
            txt = str(s or "").strip()
            if not txt:
                return 0.0
            txt = txt.replace(".", "").replace(",", ".")
            try:
                return float(txt)
            except Exception:
                return 0.0

        # Replace all tariff rows for this effective_from
        if not self.db.delete_trip_tariff_prices_for_effective_from(int(contract_id), str(service_type).strip(), str(eff)):
            QMessageBox.warning(self, "Uyarı", "Eski tarife satırları temizlenemedi.")
            return

        for r in range(tbl.rowCount()):
            it0 = tbl.item(r, 0)
            if not it0:
                continue
            rid = it0.data(Qt.ItemDataRole.UserRole + 1)
            try:
                rid = int(rid)
            except Exception:
                continue
            # save each category; VARDIYALI: no CIFT in DB, will be computed later
            for i, pc in enumerate(categories):
                price = _parse_money(tbl.item(r, 3 + i).text() if tbl.item(r, 3 + i) else "")
                sub_price = _parse_money(tbl.item(r, sub_base + i).text() if tbl.item(r, sub_base + i) else "")
                if float(price or 0.0) <= 0 and float(sub_price or 0.0) <= 0:
                    continue
                ok = self.db.upsert_trip_tariff_price(
                    contract_id=int(contract_id),
                    service_type=str(service_type).strip(),
                    route_params_id=int(rid),
                    pricing_category=str(pc).strip().upper(),
                    effective_from=str(eff),
                    price=float(price or 0.0),
                    subcontractor_price=float(sub_price or 0.0),
                )
                if not ok:
                    QMessageBox.warning(self, "Uyarı", "Tarife kaydında hata oluştu.")
                    return

        QMessageBox.information(self, "Başarılı", "Tarife kaydedildi.")
        self._tarife_load_price_rows()

    def _init_tarife_tab(self):
        # Period combo
        if hasattr(self, "cmb_tarife_period"):
            try:
                self.cmb_tarife_period.clear()
                self.cmb_tarife_period.addItem("Seçiniz...", None)
            except Exception:
                pass

        # Service type combo
        if hasattr(self, "cmb_tarife_service_type"):
            try:
                self.cmb_tarife_service_type.clear()
                self.cmb_tarife_service_type.addItem("Seçiniz...", None)
            except Exception:
                pass

        # Special items table
        tbl = getattr(self, "tbl_special_items", None)
        if tbl is not None:
            try:
                headers = ["AÇIKLAMA", "GÜN", "BİRİM FİYAT", "TUTAR", "NOT"]
                tbl.setColumnCount(len(headers))
                tbl.setHorizontalHeaderLabels(headers)
                tbl.verticalHeader().setVisible(False)
                tbl.setAlternatingRowColors(True)
                tbl.setSelectionBehavior(tbl.SelectionBehavior.SelectRows)
                tbl.setSelectionMode(tbl.SelectionMode.ExtendedSelection)
                h = tbl.horizontalHeader()
                h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
                h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
                for c in (1, 2, 3):
                    h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
                h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
            except Exception:
                pass

        # Tariff effective date
        if hasattr(self, "date_tarife_effective_from"):
            try:
                self.date_tarife_effective_from.setCalendarPopup(True)
                self.date_tarife_effective_from.setDisplayFormat("dd.MM.yyyy")
                self.date_tarife_effective_from.setDate(QDate.currentDate())
            except Exception:
                pass
        if hasattr(self, "txt_tarife_pricing_model"):
            try:
                self.txt_tarife_pricing_model.setText("")
            except Exception:
                pass

        # Tariff prices table
        tpt = getattr(self, "tbl_tarife_prices", None)
        if tpt is not None:
            try:
                tpt.verticalHeader().setVisible(False)
                tpt.setAlternatingRowColors(True)
                tpt.setSelectionBehavior(tpt.SelectionBehavior.SelectRows)
                tpt.setSelectionMode(tpt.SelectionMode.ExtendedSelection)
            except Exception:
                pass

            try:
                tpt.cellChanged.connect(self._tarife_on_price_cell_changed)
            except Exception:
                pass

        self._tarife_setup_price_table("VARDIYALI")

    def _tarife_on_price_cell_changed(self, row: int, col: int):
        tbl = getattr(self, "tbl_tarife_prices", None)
        if tbl is None:
            return
        # format only numeric cells (price/subcontract columns)
        try:
            if col < 3:
                return
            it = tbl.item(row, col)
            if it is None:
                return
            txt = (it.text() or "").strip()
            if not txt:
                return
            # parse + format
            val = self._parse_money(txt)
            tbl.blockSignals(True)
            it.setText("" if float(val or 0.0) <= 0 else self._format_money_tr(float(val or 0.0)))
        except Exception:
            return
        finally:
            try:
                tbl.blockSignals(False)
            except Exception:
                pass

    def _tarife_context(self):
        # contract_id
        contract_no = (self.txt_sozlesme_kodu.text() or "").strip() if hasattr(self, "txt_sozlesme_kodu") else ""
        if not contract_no:
            return None, None, None
        details = None
        try:
            details = self.db.get_contract_details_by_number(str(contract_no))
        except Exception:
            details = None
        contract_id = None
        try:
            contract_id = int((details or {}).get("id")) if isinstance(details, dict) and (details or {}).get("id") else None
        except Exception:
            contract_id = None

        # period
        period = None
        if hasattr(self, "cmb_tarife_period"):
            try:
                period = self.cmb_tarife_period.currentData()
                if period is None or str(period).strip() == "":
                    txt = (self.cmb_tarife_period.currentText() or "").strip()
                    period = txt if txt and not txt.lower().startswith("seç") else None
            except Exception:
                period = None

        # service_type
        service_type = None
        if hasattr(self, "cmb_tarife_service_type"):
            try:
                service_type = self.cmb_tarife_service_type.currentData()
                if service_type is None or str(service_type).strip() == "":
                    txt = (self.cmb_tarife_service_type.currentText() or "").strip()
                    service_type = txt if txt and not txt.lower().startswith("seç") else None
            except Exception:
                service_type = None

        try:
            period = (str(period).strip() if period is not None else None)
        except Exception:
            period = None
        try:
            service_type = (str(service_type).strip() if service_type is not None else None)
        except Exception:
            service_type = None

        return contract_id, period, service_type

    def _tarife_reload(self, *_args):
        if self._tarife_loading:
            return
        self._tarife_load_price_rows()
        self._load_tarife_special_items()

    def _load_tarife_periods(self, contract_id: int):
        if not hasattr(self, "cmb_tarife_period"):
            return
        try:
            self.cmb_tarife_period.blockSignals(True)
            self.cmb_tarife_period.clear()
            self.cmb_tarife_period.addItem("Seçiniz...", None)
            conn = self.db.connect()
            if not conn:
                return
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT DISTINCT month
                    FROM trip_plan
                    WHERE contract_id=?
                    ORDER BY month DESC
                    """,
                    (int(contract_id),),
                )
                months = [str(r[0]) for r in (cur.fetchall() or []) if r and r[0]]
            finally:
                conn.close()

            if not months:
                # fallback: derive from contract start/end date
                try:
                    contract_no = (self.txt_sozlesme_kodu.text() or "").strip() if hasattr(self, "txt_sozlesme_kodu") else ""
                    details = self.db.get_contract_details_by_number(str(contract_no)) if contract_no else None
                    sd = str((details or {}).get("start_date") or "").strip()
                    ed = str((details or {}).get("end_date") or "").strip()
                    if sd:
                        sdt = datetime.strptime(sd, "%Y-%m-%d")
                        edt = datetime.strptime(ed, "%Y-%m-%d") if ed else sdt
                        y, m = int(sdt.year), int(sdt.month)
                        y2, m2 = int(edt.year), int(edt.month)
                        months = []
                        while (y < y2) or (y == y2 and m <= m2):
                            months.append(f"{y:04d}-{m:02d}")
                            m += 1
                            if m > 12:
                                m = 1
                                y += 1
                except Exception:
                    months = []

            if not months:
                months = [QDate.currentDate().toString("yyyy-MM")]
            for m in months:
                self.cmb_tarife_period.addItem(str(m), str(m))

            # prefer active_month if exists
            ym = str((self.user_data or {}).get("active_month") or "").strip()
            if ym:
                idx = self.cmb_tarife_period.findData(ym)
                if idx >= 0:
                    self.cmb_tarife_period.setCurrentIndex(idx)
        except Exception:
            pass
        finally:
            try:
                self.cmb_tarife_period.blockSignals(False)
            except Exception:
                pass

    def _load_tarife_service_types(self, contract_id: int):
        if not hasattr(self, "cmb_tarife_service_type"):
            return
        try:
            self.cmb_tarife_service_type.blockSignals(True)
            self.cmb_tarife_service_type.clear()
            self.cmb_tarife_service_type.addItem("Seçiniz...", None)
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
                service_types = [str(r[0]) for r in (cur.fetchall() or []) if r and r[0]]
            finally:
                conn.close()
            for st in service_types:
                self.cmb_tarife_service_type.addItem(str(st), str(st))

            # default: contract_type if it exists
            try:
                details = self.db.get_contract_details_by_number((self.txt_sozlesme_kodu.text() or "").strip())
                cst = str((details or {}).get("contract_type") or "").strip()
                if cst and not service_types:
                    self.cmb_tarife_service_type.addItem(str(cst), str(cst))
                if cst:
                    idx = self.cmb_tarife_service_type.findData(cst)
                    if idx >= 0:
                        self.cmb_tarife_service_type.setCurrentIndex(idx)
            except Exception:
                pass
        except Exception:
            pass
        finally:
            try:
                self.cmb_tarife_service_type.blockSignals(False)
            except Exception:
                pass

    def _load_tarife_special_items(self):
        tbl = getattr(self, "tbl_special_items", None)
        if tbl is None:
            return
        contract_id, period, service_type = self._tarife_context()
        tbl.setRowCount(0)
        if not contract_id:
            return
        if not period or not service_type:
            return

        rows = []
        try:
            rows = self.db.list_contract_special_items(int(contract_id), str(period).strip(), str(service_type).strip())
        except Exception:
            rows = []

        for rec in rows or []:
            try:
                item_id = int(rec[0])
            except Exception:
                item_id = None
            title = rec[1] if len(rec) > 1 else ""
            qty_days = rec[6] if len(rec) > 6 else 0
            unit_price = rec[7] if len(rec) > 7 else 0
            total_amount = rec[8] if len(rec) > 8 else 0
            note = rec[9] if len(rec) > 9 else ""

            r = tbl.rowCount()
            tbl.insertRow(r)
            vals = [str(title or ""), str(qty_days or ""), str(unit_price or ""), str(total_amount or ""), str(note or "")]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c in (1, 2, 3):
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if c == 0 and item_id is not None:
                    it.setData(Qt.ItemDataRole.UserRole + 1, int(item_id))
                tbl.setItem(r, c, it)

    def _tarife_add_special_row(self):
        tbl = getattr(self, "tbl_special_items", None)
        if tbl is None:
            return
        contract_id, period, service_type = self._tarife_context()
        if not contract_id:
            QMessageBox.warning(self, "Uyarı", "Önce bir sözleşme seçiniz.")
            return
        if not period or not service_type:
            QMessageBox.warning(self, "Uyarı", "Dönem ve Hizmet Tipi seçiniz.")
            return

        period = str(period).strip()
        service_type = str(service_type).strip()

        r = tbl.rowCount()
        tbl.insertRow(r)
        for c in range(tbl.columnCount()):
            it = QTableWidgetItem("")
            if c in (1, 2, 3):
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tbl.setItem(r, c, it)

    def _tarife_delete_special_row(self):
        tbl = getattr(self, "tbl_special_items", None)
        if tbl is None:
            return
        selected = sorted({it.row() for it in (tbl.selectedItems() or [])}, reverse=True)
        if not selected and tbl.rowCount() > 0:
            selected = [tbl.rowCount() - 1]

        for r in selected:
            if 0 <= r < tbl.rowCount():
                tbl.removeRow(r)

    def _tarife_save_special_items(self):
        tbl = getattr(self, "tbl_special_items", None)
        if tbl is None:
            return
        contract_id, period, service_type = self._tarife_context()
        if not contract_id:
            QMessageBox.warning(self, "Uyarı", "Önce bir sözleşme seçiniz.")
            return
        if not period or not service_type:
            QMessageBox.warning(self, "Uyarı", "Dönem ve Hizmet Tipi seçiniz.")
            return

        out = []
        for r in range(tbl.rowCount()):
            it_title = tbl.item(r, 0)
            it_days = tbl.item(r, 1)
            it_unit = tbl.item(r, 2)
            it_total = tbl.item(r, 3)
            it_note = tbl.item(r, 4)

            title = (it_title.text() or "").strip() if it_title else ""
            days_txt = (it_days.text() or "").strip() if it_days else ""
            unit_txt = (it_unit.text() or "").strip() if it_unit else ""
            total_txt = (it_total.text() or "").strip() if it_total else ""
            note = (it_note.text() or "").strip() if it_note else ""

            item_id = None
            try:
                item_id = (it_title.data(Qt.ItemDataRole.UserRole + 1) if it_title else None)
                item_id = int(item_id) if item_id is not None else None
            except Exception:
                item_id = None

            def _parse_money(s: str) -> float:
                txt = str(s or "").strip()
                if not txt:
                    return 0.0
                txt = txt.replace(".", "").replace(",", ".")
                try:
                    return float(txt)
                except Exception:
                    return 0.0

            qty_days = _parse_money(days_txt)
            unit_price = _parse_money(unit_txt)
            total_amount = _parse_money(total_txt)

            if not any([title, note, qty_days, unit_price, total_amount]):
                continue

            # minimal validation: must be monetizable
            if total_amount <= 0 and (qty_days <= 0 or unit_price <= 0):
                QMessageBox.warning(self, "Uyarı", "Özel kalemlerde Tutar veya Gün+Birim Fiyat girilmelidir.")
                return

            out.append(
                {
                    "item_id": item_id,
                    "title": title,
                    "qty_days": qty_days,
                    "unit_price": unit_price,
                    "total_amount": total_amount,
                    "note": note,
                }
            )

        # Replace semantics: clear existing context then insert rows
        if not self.db.delete_contract_special_items_for_context(int(contract_id), str(period).strip(), str(service_type).strip()):
            QMessageBox.warning(self, "Uyarı", "Kayıt sırasında eski özel kalemler silinemedi.")
            return

        for rec in out:
            try:
                new_id = self.db.upsert_contract_special_item(
                    contract_id=int(contract_id),
                    period=str(period).strip(),
                    service_type=str(service_type).strip(),
                    title=str(rec.get("title") or ""),
                    qty_days=float(rec.get("qty_days") or 0.0),
                    unit_price=float(rec.get("unit_price") or 0.0),
                    total_amount=float(rec.get("total_amount") or 0.0),
                    note=str(rec.get("note") or ""),
                    item_id=None,
                )
                if new_id is None:
                    QMessageBox.warning(self, "Uyarı", "Özel kalemler kaydedilemedi (DB insert başarısız).")
                    return
            except Exception:
                QMessageBox.warning(self, "Uyarı", "Özel kalemler kaydedilirken hata oluştu.")
                return

        QMessageBox.information(self, "Başarılı", "Özel kalemler kaydedildi.")
        self._load_tarife_special_items()

    def _open_hat_dialog(self):
        # Sözleşme kodu olmadan kalem girişi yapmayalım
        contract_no = (self.txt_sozlesme_kodu.text() or "").strip() if hasattr(self, "txt_sozlesme_kodu") else ""
        if not contract_no:
            QMessageBox.warning(self, "Uyarı", "Önce sözleşme kaydını oluşturunuz.")
            return

        details = None
        try:
            details = self.db.get_contract_details_by_number(contract_no)
        except Exception:
            details = None
        contract_id = None
        service_type = ""
        start_date = ""
        end_date = ""
        try:
            if isinstance(details, dict):
                contract_id = details.get("id")
                service_type = str(details.get("contract_type") or "").strip()
                start_date = str(details.get("start_date") or "").strip()
                end_date = str(details.get("end_date") or "").strip()
        except Exception:
            contract_id = None

        dlg = QDialog(self)
        try:
            uic.loadUi(get_ui_path("hat_dialog.ui"), dlg)
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"hat_dialog.ui yüklenemedi:\n{str(e)}")
            return

        tbl = getattr(dlg, "table_kalemler", None)
        btn_add = getattr(dlg, "btn_satir_ekle", None)
        btn_del = getattr(dlg, "btn_satir_sil", None)
        btn_save = getattr(dlg, "btn_kaydet", None) or getattr(dlg, "pushButton", None)
        btn_close = getattr(dlg, "btn_kapat", None)

        if tbl is None:
            QMessageBox.critical(self, "Hata", "hat_dialog: table_kalemler bulunamadı")
            return

        headers = [
            "İŞ KALEMİ (HAT)",
            "HAREKET TÜRÜ",
            "MESAFE (KM)",
            "ARAÇ KPST.",
        ]
        tbl.setColumnCount(len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.verticalHeader().setVisible(False)
        tbl.setAlternatingRowColors(True)
        tbl.setSelectionBehavior(tbl.SelectionBehavior.SelectRows)
        tbl.setSelectionMode(tbl.SelectionMode.ExtendedSelection)
        h = tbl.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        # route_params tablosundan yükle
        pm = []
        try:
            if contract_id:
                rows = self.db.get_route_params_for_contract(int(contract_id), str(service_type))
                for rr in rows or []:
                    rid = rr[0]
                    rname = rr[1] if len(rr) > 1 else ""
                    stops = rr[2] if len(rr) > 2 else ""
                    km = rr[3] if len(rr) > 3 else 0
                    mv = rr[4] if len(rr) > 4 else ""
                    cap = rr[5] if len(rr) > 5 else 0
                    pm.append(
                        {
                            "id": rid,
                            "route_name": str(rname or ""),
                            "movement_type": str(mv or ""),
                            "distance_km": km,
                            "vehicle_capacity": cap,
                        }
                    )
        except Exception:
            pm = []

        tbl.setRowCount(0)
        for row in pm or []:
            r = tbl.rowCount()
            tbl.insertRow(r)
            vals = [
                str((row or {}).get("route_name") or ""),
                str((row or {}).get("movement_type") or ""),
                ("" if (row or {}).get("distance_km") is None else str((row or {}).get("distance_km"))),
                ("" if (row or {}).get("vehicle_capacity") is None else str((row or {}).get("vehicle_capacity"))),
            ]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c in (2, 3):
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tbl.setItem(r, c, it)

        def add_row():
            r = tbl.rowCount()
            tbl.insertRow(r)
            for c in range(tbl.columnCount()):
                it = QTableWidgetItem("")
                if c in (2, 3):
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tbl.setItem(r, c, it)

        def del_row():
            selected = sorted({it.row() for it in tbl.selectedItems()}, reverse=True)
            if not selected and tbl.rowCount() > 0:
                selected = [tbl.rowCount() - 1]
            for r in selected:
                if 0 <= r < tbl.rowCount():
                    tbl.removeRow(r)

        def save_rows():
            out = []
            for r in range(tbl.rowCount()):
                hat = (tbl.item(r, 0).text().strip() if tbl.item(r, 0) else "")
                hareket = (tbl.item(r, 1).text().strip() if tbl.item(r, 1) else "")
                km_txt = (tbl.item(r, 2).text().strip() if tbl.item(r, 2) else "")
                kps_txt = (tbl.item(r, 3).text().strip() if tbl.item(r, 3) else "")
                if not any([hat, hareket, km_txt, kps_txt]):
                    continue
                out.append(
                    {
                        "route_name": str(hat or "").strip(),
                        "movement_type": str(hareket or "").strip(),
                        "distance_km": self._parse_money(km_txt),
                        "vehicle_capacity": self._parse_money(kps_txt),
                    }
                )

            if not contract_id:
                QMessageBox.warning(self, "Uyarı", "Sözleşme bulunamadı. Lütfen sözleşmeyi kaydedip tekrar deneyiniz.")
                return

            try:
                ok = self.db.replace_route_params_for_contract(
                    contract_id=int(contract_id),
                    contract_number=str(contract_no),
                    start_date=str(start_date),
                    end_date=str(end_date),
                    service_type=str(service_type),
                    rows=out,
                )
                if ok:
                    QMessageBox.information(self, "Başarılı", "İş kalemleri kaydedildi.")
                else:
                    QMessageBox.warning(self, "Uyarı", "İş kalemleri kaydedilemedi.")
            except Exception:
                QMessageBox.warning(self, "Uyarı", "İş kalemleri kaydedilirken hata oluştu.")
            dlg.accept()

        if btn_add is not None:
            try:
                btn_add.clicked.connect(add_row)
            except Exception:
                pass
        if btn_del is not None:
            try:
                btn_del.clicked.connect(del_row)
            except Exception:
                pass
        if btn_save is not None:
            try:
                btn_save.clicked.connect(save_rows)
            except Exception:
                pass
        if btn_close is not None:
            try:
                btn_close.clicked.connect(dlg.reject)
            except Exception:
                pass

        dlg.exec()

    def _delete_selected(self):
        tbl = self._get_contracts_table()
        if tbl is None:
            return
        selected_rows = sorted({it.row() for it in tbl.selectedItems()})
        if not selected_rows:
            QMessageBox.information(self, "Bilgi", "Silmek için listeden sözleşme seçiniz.")
            return
        row = selected_rows[0]
        code_item = tbl.item(row, 0)
        contract_number = (code_item.text().strip() if code_item else "")
        if not contract_number:
            return

        msg = QMessageBox.question(
            self,
            "Onay",
            f"{contract_number} sözleşmesi silinsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if msg != QMessageBox.StandardButton.Yes:
            return

        ok = self.db.delete_contract_by_number(contract_number)
        if not ok:
            QMessageBox.critical(self, "Hata", "Sözleşme silinemedi.")
            return
        self.load_table()
        self.clear_form()

    def _format_date_tr(self, iso_date: str) -> str:
        s = (iso_date or "").strip()
        if not s:
            return ""
        try:
            d = QDate.fromString(s, "yyyy-MM-dd")
            if d.isValid():
                return d.toString("dd.MM.yyyy")
        except Exception:
            pass
        return s

    def _set_date_from_iso(self, widget_name: str, iso_date: str):
        w = getattr(self, widget_name, None)
        if w is None:
            return
        s = (iso_date or "").strip()
        if not s:
            return
        d = QDate.fromString(s, "yyyy-MM-dd")
        if d.isValid():
            w.setDate(d)

    def _load_price_table_from_json(self, price_matrix_json: str):
        tbl = self._get_price_table()
        if tbl is None:
            return
        try:
            rows = json.loads(price_matrix_json) if price_matrix_json else []
            if not isinstance(rows, list):
                rows = []
        except Exception:
            rows = []

        tbl.blockSignals(True)
        tbl.setRowCount(0)
        for r in rows:
            tbl.insertRow(tbl.rowCount())
            rr = tbl.rowCount() - 1
            guz = str((r or {}).get("guzergah") or "")
            gidis = str((r or {}).get("gidis_gelis") or "")
            km = (r or {}).get("km")
            fiyat = (r or {}).get("fiyat")
            values = [
                guz,
                gidis,
                ("" if km is None else str(km)),
                ("" if fiyat is None else self._format_money_tr(float(fiyat or 0.0))),
            ]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c in (2, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tbl.setItem(rr, c, item)
        tbl.blockSignals(False)
        if tbl.rowCount() == 0:
            self._price_add_row()
        self._recalc_price_total()

    def select_contract(self, index):
        tbl = self._get_contracts_table()
        if tbl is None:
            return
        try:
            row = index.row()
        except Exception:
            return

        code_item = tbl.item(row, 0)
        contract_number = (code_item.text().strip() if code_item else "")
        if not contract_number:
            return

        details = self.db.get_contract_details_by_number(contract_number)
        if not details:
            return

        self.current_number = contract_number
        if hasattr(self, "txt_sozlesme_kodu"):
            self.txt_sozlesme_kodu.setText(contract_number)

        # Müşteri
        cust_id = details.get("customer_id")
        if hasattr(self, "cmb_musteri"):
            for i in range(self.cmb_musteri.count()):
                if self.cmb_musteri.itemData(i) == cust_id:
                    self.cmb_musteri.setCurrentIndex(i)
                    break

        # Hizmet tipi / ücret tipi
        if hasattr(self, "cmb_hizmet_tipi") and details.get("contract_type") is not None:
            self.cmb_hizmet_tipi.setCurrentText(str(details.get("contract_type") or ""))
        if hasattr(self, "cmb_odeme_usulu") and details.get("odeme_usulu") is not None:
            self.cmb_odeme_usulu.setCurrentText(str(details.get("odeme_usulu") or ""))
        if hasattr(self, "cmb_ucret_tipi") and details.get("ucret_tipi") is not None:
            self.cmb_ucret_tipi.setCurrentText(str(details.get("ucret_tipi") or ""))

        if hasattr(self, "txt_isin_tanimi") and details.get("isin_tanimi") is not None:
            self.txt_isin_tanimi.setText(str(details.get("isin_tanimi") or ""))

        for name, key in [
            ("cmb_vardiya", "vardiya"),
            ("cmb_mesai", "mesai"),
            ("cmb_ek_ozel", "ek_ozel"),
        ]:
            w = getattr(self, name, None)
            if w is None:
                continue
            val = details.get(key)
            if val is None:
                continue
            idx = w.findText(str(val))
            if idx >= 0:
                w.setCurrentIndex(idx)

        # Tarihler
        self._set_date_from_iso("date_baslangic", str(details.get("start_date") or ""))
        self._set_date_from_iso("date_bitis", str(details.get("end_date") or ""))

        # Diğer alanlar
        if hasattr(self, "txt_arac_adedi"):
            self.txt_arac_adedi.setText(str(details.get("arac_adedi") or ""))
        if hasattr(self, "chk_esnek_sefer"):
            self.chk_esnek_sefer.setChecked(bool(int(details.get("esnek_sefer") or 0)))
        if hasattr(self, "radio_uzama_var") and hasattr(self, "radio_uzama_yok"):
            uz = int(details.get("uzatma") or 0)
            self.radio_uzama_var.setChecked(uz == 1)
            self.radio_uzama_yok.setChecked(uz != 1)
        if hasattr(self, "txt_kdv_orani"):
            k = details.get("kdv_orani")
            self.txt_kdv_orani.setText("" if k is None else str(int(float(k) or 0)))

        # İş kalemleri (fiyat matrisi json) cache'e alınır
        pm = details.get("price_matrix_json")
        if pm:
            try:
                parsed = json.loads(pm)
                self._price_matrix_cache = parsed if isinstance(parsed, list) else []
            except Exception:
                self._price_matrix_cache = []
        else:
            self._price_matrix_cache = []

        # Tarife tab combos + table refresh
        try:
            self._tarife_loading = True
            if details.get("id"):
                self._load_tarife_periods(int(details.get("id")))
                self._load_tarife_service_types(int(details.get("id")))
        except Exception:
            pass
        finally:
            self._tarife_loading = False
        self._tarife_load_price_rows()
        self._load_tarife_special_items()

        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.setText("GÜNCELLE")

    def _parse_money(self, s: str) -> float:
        s = (s or "").strip()
        if not s:
            return 0.0

        # Türkçe format desteği: 1.234,56 -> 1234.56
        s = s.replace(" ", "")
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        try:
            return float(s)
        except Exception:
            return 0.0

    def _format_money_tr(self, v: float) -> str:
        try:
            return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return ""

    def _price_add_row(self):
        tbl = self._get_price_table()
        if tbl is None:
            return

        r = tbl.rowCount()
        tbl.blockSignals(True)
        tbl.insertRow(r)
        for c in range(tbl.columnCount()):
            item = QTableWidgetItem("")
            if c in (2, 3):
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tbl.setItem(r, c, item)
        tbl.blockSignals(False)
        self._recalc_price_total()

    def _price_delete_row(self):
        tbl = self._get_price_table()
        if tbl is None:
            return

        selected = set()
        for it in tbl.selectedItems():
            selected.add(it.row())
        rows = sorted(selected, reverse=True)
        if not rows and tbl.rowCount() > 0:
            rows = [tbl.rowCount() - 1]

        tbl.blockSignals(True)
        for r in rows:
            if 0 <= r < tbl.rowCount():
                tbl.removeRow(r)
        tbl.blockSignals(False)

        self._recalc_price_total()

    def _recalc_price_total(self):
        tbl = self._get_price_table()
        if tbl is None or not hasattr(self, "txt_toplam_tutar"):
            return

        total = 0.0
        for r in range(tbl.rowCount()):
            price_item = tbl.item(r, 3)
            total += self._parse_money(price_item.text() if price_item else "")

        self.txt_toplam_tutar.blockSignals(True)
        self.txt_toplam_tutar.setText(self._format_money_tr(total))
        self.txt_toplam_tutar.blockSignals(False)
        self._update_kdv_total()

    def _collect_price_matrix(self):
        tbl = self._get_price_table()
        if tbl is None:
            return []

        rows = []
        for r in range(tbl.rowCount()):
            guz = (tbl.item(r, 0).text().strip() if tbl.item(r, 0) else "")
            gidis = (tbl.item(r, 1).text().strip() if tbl.item(r, 1) else "")
            km_txt = (tbl.item(r, 2).text().strip() if tbl.item(r, 2) else "")
            fiyat_txt = (tbl.item(r, 3).text().strip() if tbl.item(r, 3) else "")

            if not any([guz, gidis, km_txt, fiyat_txt]):
                continue

            row = {
                "guzergah": guz,
                "gidis_gelis": gidis,
                "km": self._parse_money(km_txt),
                "fiyat": self._parse_money(fiyat_txt),
            }
            rows.append(row)
        return rows

    def _assign_next_number(self):
        if hasattr(self, "txt_sozlesme_kodu"):
            self.txt_sozlesme_kodu.setText(self.db.get_next_contract_number())

    def _update_kdv_total(self):
        t = (self.txt_toplam_tutar.text() or "").replace(",", ".") if hasattr(self, "txt_toplam_tutar") else ""
        k = (self.txt_kdv_orani.text() or "") if hasattr(self, "txt_kdv_orani") else ""
        try:
            tutar = float(t) if t else 0.0
            kdv = int(k) if k else 0
            d = tutar * (1 + kdv / 100.0)
            if hasattr(self, "lbl_kdv_dahil_tutar"):
                self.lbl_kdv_dahil_tutar.setText(f"{d:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        except Exception:
            if hasattr(self, "lbl_kdv_dahil_tutar"):
                self.lbl_kdv_dahil_tutar.setText("")

    def _get_date_str(self, name):
        w = getattr(self, name, None)
        if w is None:
            return ""
        return w.date().toString("yyyy-MM-dd")

    def _collect_form_data(self):
        cust_id = self.cmb_musteri.currentData() if hasattr(self, "cmb_musteri") else None
        toplam_txt = (self.txt_toplam_tutar.text() if hasattr(self, "txt_toplam_tutar") else "") or ""
        data = {
            "customer_id": int(cust_id) if cust_id is not None else None,
            "contract_number": (self.txt_sozlesme_kodu.text() or "").strip() if hasattr(self, "txt_sozlesme_kodu") else "",
            "start_date": self._get_date_str("date_baslangic"),
            "end_date": self._get_date_str("date_bitis"),
            "contract_type": (self.cmb_hizmet_tipi.currentText() or "").strip() if hasattr(self, "cmb_hizmet_tipi") else "",
            "is_active": 1,
            "uzatma": 1 if (self.radio_uzama_var.isChecked() if hasattr(self, "radio_uzama_var") else False) else 0,
            "arac_adedi": int(self.txt_arac_adedi.text()) if hasattr(self, "txt_arac_adedi") and (self.txt_arac_adedi.text() or "").isdigit() else None,
            "esnek_sefer": 1 if (self.chk_esnek_sefer.isChecked() if hasattr(self, "chk_esnek_sefer") else False) else 0,
            "ucret_tipi": (self.cmb_ucret_tipi.currentText() or "").strip() if hasattr(self, "cmb_ucret_tipi") else "",
            "toplam_tutar": self._parse_money(toplam_txt),
            "kdv_orani": float(self.txt_kdv_orani.text()) if hasattr(self, "txt_kdv_orani") and (self.txt_kdv_orani.text() or "").isdigit() else 0.0,
        }

        if hasattr(self, "txt_isin_tanimi"):
            data["isin_tanimi"] = (self.txt_isin_tanimi.text() or "").strip()
        if hasattr(self, "cmb_odeme_usulu"):
            data["odeme_usulu"] = (self.cmb_odeme_usulu.currentText() or "").strip()

        for name, key in [
            ("cmb_vardiya", "vardiya"),
            ("cmb_mesai", "mesai"),
            ("cmb_ek_ozel", "ek_ozel"),
        ]:
            w = getattr(self, name, None)
            if w is None:
                continue
            txt = (w.currentText() or "").strip()
            try:
                data[key] = (None if txt in ("", "-") else int(txt))
            except Exception:
                data[key] = None

        if self._price_matrix_cache:
            data["price_matrix_json"] = json.dumps(self._price_matrix_cache, ensure_ascii=False)
        return data

    def save(self):
        data = self._collect_form_data()
        if not data.get("customer_id"):
            QMessageBox.warning(self, "Uyarı", "Müşteri seçimi gerekir.")
            return
        if not data.get("contract_number"):
            self._assign_next_number()
            data["contract_number"] = (self.txt_sozlesme_kodu.text() or "").strip()
        is_update = self.current_number is not None
        ok = self.db.save_contract(data, is_update=is_update)
        if ok:
            QMessageBox.information(self, "Başarılı", "Kayıt tamamlandı.")

            try:
                contract_no = str(data.get("contract_number") or "").strip()
                details = self.db.get_contract_details_by_number(contract_no) if contract_no else None
                contract_id = None
                if isinstance(details, dict):
                    contract_id = details.get("id")
                if contract_id:
                    self.db.sync_contract_operational_templates(
                        int(contract_id),
                        str(data.get("start_date") or ""),
                        str(data.get("end_date") or ""),
                    )
            except Exception:
                pass

            self.load_table()
            self.clear_form()
        else:
            QMessageBox.critical(self, "Hata", "Kayıt başarısız.")

    def clear_form(self):
        self.current_number = None
        self._price_matrix_cache = []
        if hasattr(self, "txt_sozlesme_kodu"):
            self._assign_next_number()
        if hasattr(self, "cmb_musteri"):
            self.cmb_musteri.setCurrentIndex(0)
        if hasattr(self, "cmb_hizmet_tipi"):
            self.cmb_hizmet_tipi.setCurrentIndex(0)
        if hasattr(self, "cmb_odeme_usulu"):
            self.cmb_odeme_usulu.setCurrentIndex(0)
        if hasattr(self, "txt_arac_adedi"):
            self.txt_arac_adedi.clear()
        if hasattr(self, "chk_esnek_sefer"):
            self.chk_esnek_sefer.setChecked(False)
        if hasattr(self, "cmb_ucret_tipi"):
            self.cmb_ucret_tipi.setCurrentIndex(0)
        if hasattr(self, "txt_isin_tanimi"):
            self.txt_isin_tanimi.clear()
        for name in ["cmb_vardiya", "cmb_mesai", "cmb_ek_ozel"]:
            w = getattr(self, name, None)
            if w is not None:
                w.setCurrentIndex(0)
        if hasattr(self, "txt_toplam_tutar"):
            self.txt_toplam_tutar.clear()
        if hasattr(self, "txt_kdv_orani"):
            self.txt_kdv_orani.clear()
        tbl = self._get_price_table()
        if tbl is not None:
            tbl.blockSignals(True)
            tbl.setRowCount(0)
            tbl.blockSignals(False)
            self._price_add_row()
        if hasattr(self, "btn_kaydet"):
            self.btn_kaydet.setText("KAYDET")
        self._update_kdv_total()

    def load_table(self):
        tbl = self._get_contracts_table()
        if tbl is None:
            return

        headers = [
            "SÖZLEŞME KODU",
            "MÜŞTERİ (CARİ)",
            "HİZMET TİPİ",
            "İŞE BAŞLAMA TARİHİ",
            "İŞ BİTİŞ TARİHİ",
            "DURUM",
        ]
        tbl.setColumnCount(len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.verticalHeader().setVisible(False)
        header = tbl.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        # Kolon genişlikleri
        header.resizeSection(0, 120)   # kod
        header.resizeSection(3, 130)  # başlangıç
        header.resizeSection(4, 130)  # bitiş
        header.resizeSection(5, 80)   # durum

        # Müşteri ve hizmet tipi alanı genişleyebilir
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        tbl.setAlternatingRowColors(True)
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    c.contract_number,
                    COALESCE(cu.title, ''),
                    COALESCE(c.contract_type, ''),
                    COALESCE(c.start_date, ''),
                    COALESCE(c.end_date, ''),
                    COALESCE(c.is_active, 1)
                FROM contracts c
                LEFT JOIN customers cu ON cu.id = c.customer_id
                ORDER BY c.id ASC
                """
            )
            rows = cursor.fetchall()
            conn.close()

            tbl.setRowCount(len(rows))
            for r, row in enumerate(rows):
                contract_no, customer_title, contract_type, start_date, end_date, is_active = row

                # DURUM rengi tarih bazlı
                status_txt = "AKTİF" if int(is_active or 0) == 1 else "PASİF"
                status_color = None
                try:
                    sd = QDate.fromString(str(start_date or ""), "yyyy-MM-dd")
                    ed = QDate.fromString(str(end_date or ""), "yyyy-MM-dd")
                    today = QDate.currentDate()
                    if ed.isValid() and today > ed:
                        status_txt = "PASİF"
                        status_color = QColor("red")
                    elif int(is_active or 0) != 1:
                        status_txt = "PASİF"
                        status_color = QColor("red")
                    elif sd.isValid() and ed.isValid() and today >= sd and today <= ed:
                        status_txt = "AKTİF"
                        days_left = today.daysTo(ed)
                        if days_left <= 10:
                            status_color = QColor("orange")
                        else:
                            status_color = QColor("green")
                except Exception:
                    status_color = None

                values = [
                    contract_no,
                    customer_title,
                    str(contract_type or ""),
                    self._format_date_tr(str(start_date or "")),
                    self._format_date_tr(str(end_date or "")),
                    status_txt,
                ]
                for c, value in enumerate(values):
                    item = QTableWidgetItem(str(value) if value is not None else "")
                    if c in [0, 5]:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if c == 5 and status_color is not None:
                        item.setForeground(status_color)
                    tbl.setItem(r, c, item)
        except Exception:
            tbl.setRowCount(0)
