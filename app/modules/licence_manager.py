import sys
import math
import random
import os
from PyQt6 import QtWidgets, uic
from decimal import Decimal, ROUND_HALF_UP
class SattupLicence(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        current_file_path = os.path.abspath(__file__) # .../SATTUP/app/modules/licence_manager.py
        modules_dir = os.path.dirname(current_file_path) # .../SATTUP/app/modules
        app_dir = os.path.dirname(modules_dir) # .../SATTUP/app
        project_root = os.path.dirname(app_dir) # .../SATTUP
        ui_path = os.path.join(project_root, "ui", "ui_files", "licence.ui")

        if not os.path.exists(ui_path):
            QtWidgets.QMessageBox.critical(self, "Dosya Hatası", f"UI dosyası bulunamadı:\n{ui_path}")
            return
        # Kendi hazırladığın .ui dosyasını yüklüyoruz
        # Dosya adını kendi dosya adınla değiştir (Örn: "lisans_arayuzu.ui")
        uic.loadUi(ui_path, self) 
        
        # Rastgele 12 adet 2 basamaklı sayı üret (Meydan Okuma)
        self.challenge_nums = [random.randint(10, 99) for _ in range(12)]
        self.rakamlari_yazdir()
        
        # Buton Bağlantıları (Nesne isimlerine göre)
        self.btn_active_et.clicked.connect(self.kontrol_et)
        self.btn_clear.clicked.connect(self.temizle)
        self.btn_exit.clicked.connect(self.close)
        self.btn_cancel.clicked.connect(self.reject)

    def kesin_yuvarla(self, n):
        # 0.5'i her zaman yukarı yuvarlar, sistem farklarını ortadan kaldırır
        return int(Decimal(str(n)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

    def basamak_al(self, ham_sayi, pozisyonlar):
        # Sayıyı yuvarla ve stringe çevir
        s = str(self.kesin_yuvarla(ham_sayi))
        res = ""
        for p in pozisyonlar:
            # p. basamağı al (Python indexi p-1)
            if len(s) >= p:
                res += s[p-1]
        return res

    def rakamlari_yazdir(self):
        # Üstteki QLabel'lara (lbl_rakamlar_1...12) sayıları basıyoruz
        for i in range(1, 13):
            obj_name = f"lbl_rakamlar_{i}"
            if hasattr(self, obj_name):
                getattr(self, obj_name).setText(str(self.challenge_nums[i-1]))

    def kontrol_et(self):
        x = self.challenge_nums
        # 12 kuralı manuel olarak, risk almadan hesaplıyoruz
        dogru_cevaplar = [
            self.basamak_al((x[0]*1275)/2 + 648, [2, 4]),
            self.basamak_al((x[1]*324)/2 + 188, [1, 2]),
            self.basamak_al((x[2]*1455)/2 + 819, [3, 1]),
            self.basamak_al((x[3]*1855)/2 + 572, [4, 2]),
            self.basamak_al((x[4]*957)/2 + 281, [1, 3]),
            self.basamak_al((x[5]*888)/2 + 5277, [2, 3]),
            self.basamak_al((x[6]*952)/2 + 6522, [4, 3]),
            self.basamak_al((x[7]*1277)/2 + 448, [3, 4]),
            self.basamak_al((x[8]*1543)/2 + 111, [1, 5]),
            self.basamak_al((x[9]*2355)/2 + 771, [3, 2]),
            self.basamak_al((x[10]*1644)/2 + 584, [4, 1]),
            self.basamak_al((x[11]*2327)/2 + 759, [4, 5])
        ]

        girilen_cevaplar = [
            self.txt_rakamlar_1.text().strip(),  self.txt_rakamlar_2.text().strip(),
            self.txt_rakamlar_3.text().strip(),  self.txt_rakamlar_4.text().strip(),
            self.txt_rakamlar_5.text().strip(),  self.txt_rakamlar_6.text().strip(),
            self.txt_rakamlar_7.text().strip(),  self.txt_rakamlar_8.text().strip(),
            self.txt_rakamlar_9.text().strip(),  self.txt_rakamlar_10.text().strip(),
            self.txt_rakamlar_11.text().strip(), self.txt_rakamlar_12.text().strip()
        ]


        for i in range(12):
                if girilen_cevaplar[i] != dogru_cevaplar[i]:
                    print(f"Hata Kutu {i+1}: Girilen {girilen_cevaplar[i]}, Beklenen {dogru_cevaplar[i]}")
                    QtWidgets.QMessageBox.critical(self, "Hata", "Aktivasyon kodları hatalı!")
                    return

        QtWidgets.QMessageBox.information(self, "Onay", "Lisans Onaylandı!")
        self.accept()
                # Kullanıcının girdiği QLineEdit'leri (txt_rakamlar_1...12) kontrol et
        hatali_mi = False
        for i in range(1, 13):
            obj_name = f"txt_rakamlar_{i}"
            if i == 1: obj_name = "txt_rakamlar_" # Senin görselde 1. kutu sadece "_" görünüyor
            
            if hasattr(self, obj_name):
                girilen = getattr(self, obj_name).text().strip()
                if girilen != dogru_cevaplar[i-1]:
                    hatali_mi = True
                    break
        
        if not hatali_mi:
            QtWidgets.QMessageBox.information(self, "Bilgi", "Lisans Onaylandı! Sistem Aktif.")
            self.accept()
        else:
            QtWidgets.QMessageBox.critical(self, "Hata", "Aktivasyon kodları hatalı!")

    def temizle(self):
        for i in range(1, 13):
            obj_name = f"txt_rakamlar_{i}"
            if i == 1: obj_name = "txt_rakamlar_"
            if hasattr(self, obj_name):
                getattr(self, obj_name).clear()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = SattupLicence()
    window.show()
    sys.exit(app.exec())