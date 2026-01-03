# =====================================================
# === EXPORT STYLES (PDF & EXCEL ORTAK AYARLAR) =======
# =====================================================
import os

# Eğer C:\ELBEK yoksa, projenin olduğu yeri baz alsın diye ufak bir önlem
BASE_DIR = r"C:\ELBEK"
if not os.path.exists(BASE_DIR):
    BASE_DIR = os.getcwd() 

COLORS = {
    "dark_blue": "#153D64",
    "light_bg": "#E5EAF0",
    "header_fill": "4D4D4D", # # işaretini kaldırdım, openpyxl hatasız çalışsın diye
    "header_text": "FFFFFF",
    "border": "A6A6A6",
    "row_odd": "FFFFFF",
    "row_even": "F5F5F5"
}

FONTS = {
    "main": "DejaVuSans.ttf",
    "bold": "DejaVuSans-Bold.ttf",
    "italic": "DejaVuSans-Oblique.ttf",
    "size_normal": 9,
    "size_title": 14,
    "size_footer": 7
}

PATHS = {
    "fonts": os.path.join(BASE_DIR, "fonts"),
    "icons": os.path.join(BASE_DIR, "icons"),
    "logo": os.path.join(BASE_DIR, "icons", "logo.png"),
    "logo_faded": os.path.join(BASE_DIR, "icons", "logo_faded.png")
}

COMPANY_NAME = "Sakarya Asil Tur Taşımacılık Hizmetleri"