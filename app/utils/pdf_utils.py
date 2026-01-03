import os
from datetime import datetime
from fpdf import FPDF
from PIL import Image
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from app.styles import PATHS, COLORS, FONTS, COMPANY_NAME

class CustomPDF(FPDF):
    """
    FPDF sınıfını özelleştirerek:
    - Header: Logo ve Başlık (En altta)
    - Footer: Filigran + Alt Bilgi (En üstte, tablonun üzerine basar)
    """
    def __init__(self, orientation='P', unit='mm', format='A4', username="Admin", report_title="Rapor"):
        super().__init__(orientation, unit, format)
        self.username = username
        self.report_title = report_title
        self.active_font = "Arial" 

    def set_font_family(self, font_name):
        self.active_font = font_name

    def header(self):
        # --- 1. Sol Üst Logo ---
        if os.path.exists(PATHS["logo"]):
            self.image(PATHS["logo"], x=10, y=8, w=40)

        # --- 2. Rapor Başlığı ---
        self.set_xy(55, 15)
        self.set_font(self.active_font, "B", 14)
        self.cell(0, 10, f"{COMPANY_NAME} — {self.report_title}", align="C", ln=1)
        self.ln(10)

    def footer(self):
        # --- 1. Filigran (BURAYA TAŞINDI - EN ÜSTE ÇİZİLİR) ---
        # Footer sayfa içeriği bittikten sonra çağrıldığı için,
        # buraya eklenen resim tablonun ve satırların ÜZERİNE basılır.
        try:
            if os.path.exists(PATHS["logo"]):
                logo_faded = PATHS["logo_faded"]
                # Soluk logo yoksa oluştur
                if not os.path.exists(logo_faded):
                    with Image.open(PATHS["logo"]).convert("RGBA") as im:
                        alpha = im.split()[3]
                        # Opaklığı %12'ye çektim (Yazılar daha net okunsun diye)
                        alpha = alpha.point(lambda p: p * 0.12) 
                        im.putalpha(alpha)
                        im.save(logo_faded)
                
                # Sayfanın tam ortasına yerleştir
                x_center = self.w / 2
                y_center = self.h / 2
                img_w = 150
                img_h = 60 
                
                # Resim bas (Tablonun üzerine gelir)
                self.image(logo_faded, x=x_center - (img_w/2), y=y_center - (img_h/2), w=img_w)
        except Exception:
            pass

        # --- 2. Standart Footer Çizgi ve Yazıları ---
        self.set_y(-15)
        self.set_draw_color(0, 0, 0)
        self.set_line_width(0.4)
        self.line(10, self.get_y(), 287, self.get_y())
        
        self.set_font(self.active_font, "I", 7)
        self.set_text_color(0, 0, 0)
        
        # Sol: Şirket Adı
        self.set_xy(10, self.get_y() + 2)
        self.cell(0, 8, COMPANY_NAME, align="L")
        
        # Sağ: Bilgiler
        tarih = datetime.now().strftime("%d.%m.%Y %H:%M")
        footer_text = f"Raporlayan: {self.username} — {tarih} — Sayfa {self.page_no()}/{{nb}}"
        
        self.set_xy(0, self.get_y())
        self.cell(0, 8, footer_text, align="R")

def create_pdf(table_widget, report_title="Genel Rapor", username="Admin", parent=None):
    if table_widget.rowCount() == 0:
        QMessageBox.warning(parent, "Uyarı", "Listede veri yok!")
        return

    # Dosya Seçimi
    default_name = f"{report_title}_{datetime.now().strftime('%d%m%Y')}.pdf"
    file_name, _ = QFileDialog.getSaveFileName(
        parent,
        "PDF Kaydet",
        os.path.join(os.path.expanduser("~/Desktop"), default_name),
        "PDF Dosyaları (*.pdf)"
    )
    if not file_name:
        return

    try:
        # PDF Başlat
        pdf = CustomPDF(orientation="L", unit="mm", format="A4", username=username, report_title=report_title)
        pdf.alias_nb_pages()

        # Fontlar
        font_main = os.path.join(PATHS["fonts"], FONTS["main"])
        font_bold = os.path.join(PATHS["fonts"], FONTS["bold"])
        font_italic = os.path.join(PATHS["fonts"], FONTS["italic"])

        if os.path.exists(font_main):
            pdf.add_font("DejaVu", "", font_main, uni=True)
            pdf.add_font("DejaVu", "B", font_bold, uni=True)
            pdf.add_font("DejaVu", "I", font_italic, uni=True)
            pdf.set_font_family("DejaVu")
            active_font = "DejaVu"
        else:
            pdf.set_font_family("Arial")
            active_font = "Arial"

        pdf.add_page()

        # Tablo Başlıkları
        headers = [table_widget.horizontalHeaderItem(i).text() for i in range(table_widget.columnCount())]
        col_widths = [20, 30, 25, 60, 25, 30, 50, 15, 20] 

        def print_table_header():
            pdf.set_font(active_font, "B", 9)
            pdf.set_fill_color(60, 60, 60)
            pdf.set_text_color(255, 255, 255)
            for i, h in enumerate(headers):
                w = col_widths[i] if i < len(col_widths) else 30
                pdf.cell(w, 8, h, border=1, align="C", fill=True)
            pdf.ln()

        print_table_header()

        # Tablo Verileri
        pdf.set_font(active_font, "", 8)
        pdf.set_text_color(0, 0, 0)
        
        fill = False 
        row_count = table_widget.rowCount()
        col_count = table_widget.columnCount()

        for r in range(row_count):
            if pdf.get_y() > 175:
                pdf.add_page()
                print_table_header()
                pdf.set_font(active_font, "", 8)
                pdf.set_text_color(0, 0, 0)

            # Zebra Renklendirme (Klasik yöntem)
            # Filigran artık üstte olduğu için gri satırın üstüne basılacak
            pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
            
            row_height = 7
            
            for c in range(col_count):
                item = table_widget.item(r, c)
                text = str(item.text()) if item else ""
                w = col_widths[c] if c < len(col_widths) else 30
                
                align = "L" if c in [3, 6] else "C"
                
                # Her satırın arka planını (fill) boyuyoruz
                # Filigran bu boyanın ÜZERİNE geleceği için sorun kalmadı.
                pdf.cell(w, row_height, text, border=1, align=align, fill=True)
            
            pdf.ln()
            fill = not fill

        pdf.output(file_name)
        QMessageBox.information(parent, "Başarılı", f"PDF Kaydedildi:\n{file_name}")
        os.startfile(file_name)

    except Exception as e:
        QMessageBox.critical(parent, "Hata", f"PDF Hatası:\n{e}")