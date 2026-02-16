import os
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.drawing.image import Image as XLImage
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from app.styles import COLORS, PATHS, COMPANY_NAME
import re

def create_excel(table_widget, report_title="Genel Rapor", username="Admin", parent=None, meta=None):
    """
    QTableWidget verilerini Excel'e dönüştürür.
    TEK SAYFAYA SIĞDIRMA GARANTİLİ VERSİYON.
    """
    
    # 1. Kayıt Yeri Seçimi
    default_name = f"{report_title}_{datetime.now().strftime('%d%m%Y')}.xlsx"
    file_name, _ = QFileDialog.getSaveFileName(
        parent,
        "Excel Olarak Kaydet",
        os.path.join(os.path.expanduser("~/Desktop"), default_name),
        "Excel Dosyası (*.xlsx)"
    )
    
    if not file_name:
        return

    try:
        src_col_count = table_widget.columnCount()
        is_bulk_puantaj = "Toplu Puantaj" in str(report_title or "")

        template_path = None
        if is_bulk_puantaj:
            try:
                repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                cand = os.path.join(repo_root, "ui", "Toplu_puantaj_sablon.xlsx")
                if os.path.exists(cand):
                    template_path = cand
            except Exception:
                template_path = None

        if template_path:
            wb = openpyxl.load_workbook(template_path)
            ws = wb.active

            def _anchor_cell(row: int, col: int):
                try:
                    for mr in ws.merged_cells.ranges:
                        if mr.min_row <= row <= mr.max_row and mr.min_col <= col <= mr.max_col:
                            return ws.cell(row=mr.min_row, column=mr.min_col) # type: ignore
                except Exception:
                    pass
                return ws.cell(row=row, column=col) # type: ignore

            def _norm_hdr(x: str) -> str:
                return re.sub(r"\s+", " ", str(x or "").strip()).casefold()

            src_headers = [table_widget.horizontalHeaderItem(i).text() for i in range(src_col_count)]
            src_headers_norm = [_norm_hdr(h) for h in src_headers]

            export_src_cols = list(range(src_col_count))
            if is_bulk_puantaj:
                try:
                    drop_idx = None
                    for i, h in enumerate(src_headers_norm):
                        if h == "duraklar":
                            drop_idx = i
                            break
                    if drop_idx is not None:
                        export_src_cols = [i for i in export_src_cols if i != int(drop_idx)]
                except Exception:
                    pass

            if is_bulk_puantaj:
                try:
                    def _tr_month_name(m: int) -> str:
                        mm = int(m)
                        names = {
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
                        return names.get(mm, str(mm))

                    meta_d = meta if isinstance(meta, dict) else {}
                    cust = str(meta_d.get("customer_name") or "").strip()
                    if cust:
                        _anchor_cell(3, 4).value = cust

                    ym = str(meta_d.get("month") or "").strip()
                    m = re.match(r"^\s*(20\d{2})[-./](\d{1,2})\s*$", ym)
                    if m:
                        _anchor_cell(2, 40).value = str(m.group(1))
                        _anchor_cell(3, 40).value = _tr_month_name(int(m.group(2)))
                except Exception:
                    pass

            max_col = int(ws.max_column or 0)
            header_rows = (5, 6) if is_bulk_puantaj else None
            if not header_rows:
                max_row = int(ws.max_row or 0)
                header_row = None
                for r in range(1, max_row + 1):
                    row_vals = []
                    for c in range(1, max_col + 1):
                        v = ws.cell(row=r, column=c).value
                        row_vals.append(_norm_hdr(v) if v is not None else "")
                    hit = 0
                    for key in ["güzergah", "guzergah", "şoför", "sofor", "hareket"]:
                        if any((key in s) for s in row_vals):
                            hit += 1
                    if hit >= 2:
                        header_row = r
                        break
                if header_row is None:
                    raise RuntimeError("Şablonda başlık satırı bulunamadı")
                header_rows = (int(header_row),)

            tmpl_headers = {}
            for c in range(1, max_col + 1):
                parts = []
                for rr in header_rows or ():
                    try:
                        v = _anchor_cell(int(rr), int(c)).value
                        nv = _norm_hdr(v)
                        if nv:
                            parts.append(nv)
                    except Exception:
                        pass
                joined = _norm_hdr(" ".join([p for p in parts if p]))
                if joined and joined not in tmpl_headers:
                    tmpl_headers[joined] = c

            tmpl_export_cols = []
            for c in range(1, int(ws.max_column or 0) + 1):
                has_hdr = False
                for rr in (5, 6) if is_bulk_puantaj else ():
                    try:
                        v = _anchor_cell(int(rr), int(c)).value
                        if _norm_hdr(v):
                            has_hdr = True
                            break
                    except Exception:
                        pass
                if has_hdr:
                    tmpl_export_cols.append(int(c))

            src_to_tmpl_col = {}

            if is_bulk_puantaj:
                try:
                    tmpl_fixed = list(tmpl_export_cols[:6])
                    tmpl_days = list(tmpl_export_cols[6:37])
                    tmpl_sum = list(tmpl_export_cols[37:40])

                    src_fixed = list(export_src_cols[:6])
                    src_sum = list(export_src_cols[-3:]) if len(export_src_cols) >= 9 else []
                    src_days = list(export_src_cols[6:-3]) if len(export_src_cols) >= 9 else []

                    if (
                        len(tmpl_fixed) == 6
                        and len(tmpl_days) == 31
                        and len(tmpl_sum) == 3
                        and len(src_fixed) == 6
                        and len(src_sum) == 3
                    ):
                        for i in range(6):
                            src_to_tmpl_col[int(src_fixed[i])] = int(tmpl_fixed[i])

                        for i in range(min(len(src_days), 31)):
                            src_to_tmpl_col[int(src_days[i])] = int(tmpl_days[i])

                        for i in range(3):
                            src_to_tmpl_col[int(src_sum[i])] = int(tmpl_sum[i])
                except Exception:
                    src_to_tmpl_col = {}

            start_data_row = 7 if is_bulk_puantaj else (int((header_rows or (0,))[0]) + 1)

            row_count = table_widget.rowCount()
            for r in range(int(row_count)):
                out_r = int(start_data_row) + int(r)
                for src_c, tmpl_c in (src_to_tmpl_col or {}).items():
                    item = table_widget.item(int(r), int(src_c))
                    val = item.text() if item else ""
                    if is_bulk_puantaj and int(tmpl_c) == int(tmpl_headers.get(_norm_hdr("GÜZERGAH")) or -1):
                        val = str(val or "")
                    _anchor_cell(int(out_r), int(tmpl_c)).value = val

            wb.save(file_name)
            QMessageBox.information(parent, "Başarılı", f"Excel dosyası oluşturuldu:\n{file_name}")
            os.startfile(file_name)
            return

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Rapor" # type: ignore

        # --- 2. Sayfa Düzeni ve SIĞDIRMA AYARLARI ---
        ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE # type: ignore
        ws.page_setup.paperSize = ws.PAPERSIZE_A4 # type: ignore
        
        # --- KRİTİK DÜZELTME BAŞLANGICI ---
        # Excel'e "Sayfa yapısı ayarlarını kullan" emrini veriyoruz
        ws.sheet_properties.pageSetUpPr.fitToPage = True  # type: ignore
        
        # Genişliği KESİN OLARAK 1 sayfaya sığdır
        ws.page_setup.fitToWidth = 1 # type: ignore
        ws.page_setup.fitToHeight = False # type: ignore # Yükseklik serbest (otomatik artsın)
        # --- KRİTİK DÜZELTME BİTİŞİ ---

        ws.print_options.horizontalCentered = True # type: ignore
        ws.page_margins = PageMargins(left=0.4, right=0.4, top=0.5, bottom=0.5, header=0.3, footer=0.3) # type: ignore

        # --- 3. Logo ---
        if os.path.exists(PATHS["logo"]):
            try:
                img = XLImage(PATHS["logo"])
                img.width = 120
                img.height = 50
                ws.add_image(img, "A1") # type: ignore
            except Exception:
                pass

        headers = [table_widget.horizontalHeaderItem(i).text() for i in range(src_col_count)]
        is_bulk_puantaj = "Toplu Puantaj" in str(report_title or "")

        export_src_cols = list(range(src_col_count))
        if is_bulk_puantaj:
            try:
                def _norm_hdr(x: str) -> str:
                    return str(x or "").replace("\n", " ").strip().casefold()

                drop_idx = None
                for i, h in enumerate(headers):
                    if _norm_hdr(h) == "duraklar":
                        drop_idx = i
                        break
                if drop_idx is not None:
                    export_src_cols = [i for i in export_src_cols if i != int(drop_idx)]
            except Exception:
                pass

        col_count = len(export_src_cols)
        last_col_letter = get_column_letter(col_count)

        # --- 4. Başlıklar ---
        title_cell = ws["A2"] # type: ignore
        title_cell.value = f"{COMPANY_NAME} - {report_title}"
        title_cell.font = Font(bold=True, size=14)
        title_cell.alignment = Alignment(horizontal="center", vertical="center")
        
        ws.merge_cells(f"A2:{last_col_letter}2") # type: ignore

        # --- 5. Tablo Başlıkları ---
        headers = [headers[i] for i in export_src_cols]

        if is_bulk_puantaj:
            def _simplify_day_header(h: str) -> str:
                txt = str(h or "").strip()
                if not txt:
                    return txt
                # Common formats: "1\nPz", "1 Pz", "01\nPt".
                m = re.match(r"^\s*(\d{1,2})\b", txt)
                if not m:
                    return txt
                try:
                    day = int(m.group(1))
                except Exception:
                    return txt
                if 1 <= day <= 31:
                    return str(day)
                return txt

            headers = [_simplify_day_header(h) for h in headers]
        
        header_fill = PatternFill(start_color=COLORS["header_fill"], end_color=COLORS["header_fill"], fill_type="solid")
        header_font = Font(bold=True, color=COLORS["header_text"])
        thin_border = Border(left=Side(style="thin", color=COLORS["border"]), 
                             right=Side(style="thin", color=COLORS["border"]), 
                             top=Side(style="thin", color=COLORS["border"]), 
                             bottom=Side(style="thin", color=COLORS["border"]))

        start_row = 5
        for col_idx, col_name in enumerate(headers, start=1):
            cell = ws.cell(row=start_row, column=col_idx, value=col_name) # type: ignore
            cell.font = header_font
            cell.fill = header_fill
            cell.border = thin_border
            if "Toplu Puantaj" in str(report_title or ""):
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            else:
                cell.alignment = Alignment(horizontal="center", vertical="center")

        try:
            if "Toplu Puantaj" in str(report_title or ""):
                ws.row_dimensions[start_row].height = 32 # type: ignore
        except Exception:
            pass

        # --- 6. Veriler ---
        row_count = table_widget.rowCount()
        for r in range(row_count):
            for out_c, src_c in enumerate(export_src_cols):
                item = table_widget.item(r, int(src_c))
                val = item.text() if item else ""
                
                cell = ws.cell(row=start_row + 1 + r, column=out_c + 1, value=val) # type: ignore
                cell.border = thin_border
                h_align = "left" if out_c in [3, 6] else "center"
                if is_bulk_puantaj and (out_c + 1) in [1, 2, 3, 4]:
                    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
                else:
                    cell.alignment = Alignment(horizontal=h_align, vertical="center")

        # --- 7. Sütun Genişlikleri (Hafif Revize Edildi) ---
        # 1:Kod, 2:Tür, 3:TCKN, 4:AdSoyad, 5:Görev, 6:GSM, 7:Email, 8:Kan, 9:Durum
        custom_widths = {
            1: 13,  # Kod
            2: 20,  # Tür 
            3: 15,  # TCKN
            4: 30,  # Ad Soyad
            5: 20,  # Görev
            6: 18,  # GSM
            7: 35,  # Email
            8: 10,  # Kan
            9: 10   # Durum
        }

        is_bulk_puantaj = "Toplu Puantaj" in str(report_title or "")
        bulk_widths = {
            1: 3.5546875,
            2: 10.44140625,
            3: 9.33203125,
            4: 10.21875,
            5: 7.21875,
            6: 9.44140625,
            7: 2.88671875,
        }

        for col_idx, col_name in enumerate(headers, start=1):
            col_letter = get_column_letter(col_idx)
            if is_bulk_puantaj:
                try:
                    if col_idx in bulk_widths:
                        ws.column_dimensions[col_letter].width = float(bulk_widths[col_idx]) # type: ignore
                        continue
                except Exception:
                    pass

                try:
                    if col_idx >= 7 and col_idx <= (col_count - 3):
                        ws.column_dimensions[col_letter].width = 2.88671875 # type: ignore
                        continue
                except Exception:
                    pass

                try:
                    last4_start = max(1, int(col_count) - 3)
                    if col_idx == last4_start:
                        ws.column_dimensions[col_letter].width = 7.33203125 # type: ignore
                    elif col_idx == last4_start + 1:
                        ws.column_dimensions[col_letter].width = 9.5546875 # type: ignore
                    elif col_idx == last4_start + 2:
                        ws.column_dimensions[col_letter].width = 10.33203125 # type: ignore
                    elif col_idx == last4_start + 3:
                        ws.column_dimensions[col_letter].width = 8.88671875 # type: ignore
                    else:
                        ws.column_dimensions[col_letter].width = 15 # type: ignore
                except Exception:
                    ws.column_dimensions[col_letter].width = 15 # type: ignore
            else:
                if col_idx in custom_widths:
                    ws.column_dimensions[col_letter].width = custom_widths[col_idx] # type: ignore
                else:
                    ws.column_dimensions[col_letter].width = 15 # type: ignore

        try:
            if is_bulk_puantaj:
                start_data_row = start_row + 1
                end_data_row = start_row + int(row_count)
                for merge_col in [1, 2, 3, 4, 5]:
                    r0 = start_data_row
                    while r0 <= end_data_row:
                        v0 = ws.cell(row=r0, column=merge_col).value # type: ignore
                        v0s = re.sub(r"\s+", " ", str(v0 or "").strip()).casefold()
                        r1 = r0
                        while r1 + 1 <= end_data_row:
                            v1 = ws.cell(row=r1 + 1, column=merge_col).value # type: ignore
                            v1s = re.sub(r"\s+", " ", str(v1 or "").strip()).casefold()
                            if v1s != v0s:
                                break
                            r1 += 1
                        if v0s and r1 > r0:
                            ws.merge_cells(start_row=r0, start_column=merge_col, end_row=r1, end_column=merge_col) # type: ignore
                            if merge_col in [1, 2, 3, 4]:
                                try:
                                    top_cell = ws.cell(row=r0, column=merge_col) # type: ignore
                                    top_cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
                                except Exception:
                                    pass
                        r0 = r1 + 1
        except Exception:
            pass

        # --- 8. Yazdırma Alanı ---
        ws.print_area = f"A1:{last_col_letter}{ws.max_row}" # type: ignore
        ws.print_title_rows = '5:5' # type: ignore

        wb.save(file_name)
        QMessageBox.information(parent, "Başarılı", f"Excel dosyası oluşturuldu:\n{file_name}")
        os.startfile(file_name)

    except Exception as e:
        QMessageBox.critical(parent, "Hata", f"Excel hatası:\n{e}")