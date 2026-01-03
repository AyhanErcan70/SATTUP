# C:\ELBEK\app\input_utils.py dosyasının içeriği:

from PyQt6.QtWidgets import QLineEdit 

def turkish_upper(text):
    """Metni Türkçe'ye uygun olarak, I/i dönüşümlerini düzelterek büyük harfe çevirir."""
    
    # 1. Önce Sadece Hatalı Türkçe Karakterleri Düzelt
    # (Bu sayede genel .upper() işlemi onları bozmaz)
    text = text.replace('i', 'İ') # Küçük noktalı i -> Büyük noktalı İ
    text = text.replace('ı', 'I') # Küçük noktasız ı -> Büyük noktasız I
    
    # 2. Şimdi geri kalan her şeyi büyük harf yap (Ş, Ü, Ö, Ç, Ğ düzelir)
    return text.upper()

def _update_to_uppercase(widget, new_text):
    """textChanged sinyali tetiklendiğinde çalışır ve sonsuz döngüyü önler."""
    converted_text = turkish_upper(new_text)
    
    if widget.text() != converted_text:
        # Sonsuz döngüyü engelle: setText() sinyalini engelle
        widget.blockSignals(True) 
        widget.setText(converted_text)
        widget.blockSignals(False)

def connect_uppercase_fields(parent_widget, field_names):
    """Verilen parent widget (Form) içindeki LineEdit'leri büyük harfe çevirmek için bağlar."""
    for name in field_names:
        widget = getattr(parent_widget, name, None)
        if widget and isinstance(widget, QLineEdit):
            # Connect the textChanged signal to the real-time handler
            # Not: Lambda içinde widget'ı yakalamak, döngü sonundaki isim karışıklığını önler.
            widget.textChanged.connect(lambda new_text, w=widget: _update_to_uppercase(w, new_text))
            
# input_utils.py dosyasına ekle:

def format_gsm(text):
    """Metni parantezli GSM formatına ((5XX) XXX XX XX) dönüştürür."""
    # Sadece rakamları al
    digits = ''.join(filter(str.isdigit, text))
    
    if not digits:
        return ""
    
    # 10 haneli formatı uygula (Türk mobil standartı)
    formatted = []
    
    # Parantez (5XX)
    if len(digits) > 0:
        formatted.append("(")
        formatted.append(digits[:3])
        if len(digits) > 3:
            formatted.append(") ")
    
    # İlk üçlü (XXX)
    if len(digits) > 3:
        formatted.append(digits[3:6])
        if len(digits) > 6:
            formatted.append(" ")
            
    # İkinci ikili (XX)
    if len(digits) > 6:
        formatted.append(digits[6:8])
        if len(digits) > 8:
            formatted.append(" ")
            
    # Son ikili (XX)
    if len(digits) > 8:
        formatted.append(digits[8:10])

    return "".join(formatted)
# input_utils.py dosyasına ekle:

def format_iban(text):
    """Metni TR ile başlayan, 4'lü gruplara ayrılmış IBAN formatına dönüştürür."""
    
    # 1. TR'yi garanti et ve metni büyük harf yap
    text = text.upper()
    if not text.startswith("TR"):
        text = "TR" + text
        
    # 2. TR'den sonraki kısmı filtrele (Sadece rakamları al)
    prefix = text[:2] # TR sabit kalır
    # Sadece 22 rakam + 2 kontrol rakamı beklenir
    digits = ''.join(filter(str.isdigit, text[2:]))
    
    # 3. Maksimum uzunluğu (26 karakter) koru
    full_iban = prefix + digits
    if len(full_iban) > 26:
        full_iban = full_iban[:26]

    # 4. 4'lü gruplara ayırarak maskele
    masked = []
    
    # İlk 4 haneyi (TRxx) al
    masked.append(full_iban[:4])
    
    # Geri kalanını 4'lü gruplar halinde ayır
    remaining = full_iban[4:]
    for i in range(0, len(remaining), 4):
        masked.append(remaining[i:i+4])
        
    return " ".join(masked)
# input_utils.py dosyasına ekle:

def is_valid_tckn(tckn):
    """TC Kimlik Numarasının 11 haneli matematiksel geçerliliğini kontrol eder."""
    
    if not tckn or len(tckn) != 11 or not tckn.isdigit():
        return False
    
    if tckn.startswith('0'):
        return False
    
    digits = [int(d) for d in tckn]
    
    # 10. hanenin kontrolü
    # Tek haneler (T1, T3, T5, T7, T9) x 7 - Çift haneler (T2, T4, T6, T8) toplamı 10'a tam bölünmeli
    odd_sum = digits[0] + digits[2] + digits[4] + digits[6] + digits[8]
    even_sum = digits[1] + digits[3] + digits[5] + digits[7]
    check_10 = (odd_sum * 7 - even_sum) % 10
    
    if check_10 != digits[9]:
        return False

    # 11. hanenin kontrolü (İlk 10 hanenin toplamı 10'a tam bölünmeli)
    check_11 = (sum(digits[:10])) % 10
    
    if check_11 != digits[10]:
        return False

    return True