# ========================================================
# === S.A.T.T.U.P - MERKEZİ GÖRSEL STİL DOSYASI (QSS) ===
# ========================================================

# Kurumsal Renkler
COLOR_PRIMARY = "#288EB2"      # Koyu Mavi (Logo Rengi)
COLOR_SECONDARY = "#162D6D"    # Koyu Gri/Mavi
COLOR_ACCENT = "#E67E22"       # Turuncu (Vurgu için)
COLOR_BG = "#D9D9D9"           # Açık Gri (Arka Plan)
COLOR_WHITE = "#FFFFFF"
COLOR_DANGER = "#C0392B"       # Kırmızı (Silme işlemleri)
COLOR_FOCUS_BG = "#EBF5FB" 


FORM_STYLE = f"""
    QWidget {{
        background-color: {COLOR_BG};
        font-family: 'Daytona',Calibri, Arial;
    }}
    
    QLabel {{
        color: {COLOR_SECONDARY};
        font-weight: bold;
        font-size: 12px;
        background: transparent;
        border: none;
    }}

    /* Input Alanları */
    QLineEdit, QComboBox, QDateEdit {{
        background-color: {COLOR_WHITE};
        border: 1px solid #BDC3C7;
        border-radius: 6px;
        padding: 5px;
        font-size: 12px;
        color: #333;
    }}

    QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{
        border: 2px solid {COLOR_PRIMARY};
        background-color: {COLOR_FOCUS_BG};
    }}
    
    /* Personel Kodu Özel Stil */
    QLineEdit#txt_personel_kodu {{
        font-family: 'Century Gothic', sans-serif;
        font-size: 16px;
        font-weight: bold;
        color: {COLOR_DANGER};
        border: none;
        background: transparent;
    }}
    QLineEdit#txt_personel_kodu:disabled {{
        color: {COLOR_DANGER};
        background: transparent;
        border: none;
    }}
    
    /* --- TABLO ÖZELLEŞTİRMELERİ --- */
    QTableWidget {{
        background-color: {COLOR_WHITE};
        
        /* Zebra Stili Rengi (Gri) */
        alternate-background-color: #F2F2F2; 
        
        /* 1. Izgara Çizgileri (Hafif Koyu Gri) */
        gridline-color: #909090;
        
        /* 3. Dış Çerçeve (Kalın) */
        border: 2px solid {COLOR_PRIMARY};
        border-radius: 6px;
        
        font-family: 'Daytona', 'Segoe UI', sans-serif;
        font-size: 10pt;
    }}
    
    /* 2. Header (Başlıklar) Ayrımı ve Radius */
    QHeaderView::section {{
        background-color: {COLOR_PRIMARY};
        color: white;
        padding: 4px;
        
        /* Başlıklar arası çizgi ve yuvarlatma */
        border: 1px solid #0E2942; 
        border-radius: 4px;
        margin: 1px; /* Kutucuk gibi görünmesi için boşluk */
        
        font-family: 'Century Gothic', sans-serif;
        font-weight: bold;
        font-size: 10pt;
    }}

    /* --- SEÇİM DAVRANIŞLARI (4. Madde) --- */
    
    /* Tablo ODAKLANDIĞINDA (Aktif) Seçili Satır: MAVİ */
    QTableWidget::item:selected {{
        background-color: #D6EAF8;
        color: #000;
    }}
    
    /* Tablo ODAK KAYBETTİĞİNDE (Başka yere tıklayınca) Seçili Satır: GRİ */
    QTableWidget::item:selected:!active {{
        background-color: #E0E0E0; /* Soluk Gri */
        color: #555;
    }}

    /* Butonlar */
    QPushButton {{
        background-color: {COLOR_PRIMARY};
        background-image: none; 
        color: white;
        border: none;
        border-radius: 6px;
        padding: 8px 15px;
        font-weight: bold;
        font-size: 12px;
        min-height:15px;
    }}
    QPushButton:hover {{ 
        background-color: #0D39B2;
        
        
    }}
    QPushButton:pressed {{ background-color: #0E2942; }}

    QPushButton#btn_yeni {{ background-color: {COLOR_ACCENT}; }}
    QPushButton#btn_yeni:hover {{ background-color: #D35400; }}
    
    QPushButton#btn_sil {{ background-color: {COLOR_DANGER}; }}
    QPushButton#btn_sil:hover {{ background-color: #922B21; }}
    
    QPushButton#btn_geridon {{ background-color: #7F8C8D; }}
    QPushButton#btn_geridon:hover {{ background-color: #626567; }}
"""