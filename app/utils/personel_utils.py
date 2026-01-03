import os
import sys
import re


def _load_list_from_txt(file_name, sub_folder="personel"):
    
    # Path hesaplama (Artık 3 seviye yukarı çıkmalıyız: ELBEK/app/personel_utils.py -> ELBEK)

    current_file_dir = os.path.dirname(os.path.abspath(__file__)) # ELBEK/app
    APP_DIR = os.path.dirname(current_file_dir)                   # ELBEK/
    BASE_DIR = os.path.dirname(APP_DIR)                           # C:\ELBEK (Artık 3 kez dirname kullanıyoruz)
    # Path'i oluştur
    COMBO_PATH = os.path.join(APP_DIR, "database", "combos", sub_folder)
    file_path = os.path.join(COMBO_PATH, file_name)
    
    if not os.path.exists(file_path):
        print(f"UYARI: Dosya bulunamadı: {file_path}")
        return []
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            # Sadece boş olmayan satırları al (Dosyanın ilk satırındaki "Seçiniz..." ifadesini silmiş olmalıyız)
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"HATA: {file_path} okunamadı. {e}")
        return []