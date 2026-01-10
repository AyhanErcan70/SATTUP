import os

from config import BASE_DIR

COLORS = {
    "dark_blue": "#153D64",
    "light_bg": "#E5EAF0",
    "header_fill": "4D4D4D",
    "header_text": "FFFFFF",
    "border": "A6A6A6",
    "row_odd": "FFFFFF",
    "row_even": "F5F5F5",
}

FONTS = {
    "main": "DejaVuSans.ttf",
    "bold": "DejaVuSans-Bold.ttf",
    "italic": "DejaVuSans-Oblique.ttf",
    "size_normal": 9,
    "size_title": 14,
    "size_footer": 7,
}

PATHS = {
    "fonts": os.path.join(BASE_DIR, "assets", "fonts"),
    "icons": os.path.join(BASE_DIR, "assets", "images"),
    "logo": os.path.join(BASE_DIR, "assets", "images", "logo.png"),
    "logo_faded": os.path.join(BASE_DIR, "assets", "images", "logo_faded.png"),
}

COMPANY_NAME = "Sakarya Asil Tur Taşımacılık Hizmetleri"
