# 🚌 S.A.T.T.U.P – Sxxxxxx Axxxxx Tur Taşımacılık Uygulaması Projesi

## 🎯 Proje Tanımı
Bu Proje; Taşımacılık Yönetim Sistemi, Personel ve Öğrenci Servis Taşımacılığı ile Araç Kiralama sektöründe faaliyet gösteren işletmeler için özel olarak tasarlanmış, Python programlama dili ile geliştirilen, Windows tabanlı bir masaüstü otomasyon çözümüdür. Uygulama; operasyonel süreçlerin dijitalleşmesini sağlayarak personel, araç, müşteri (gerçek/tüzel) ve tedarikçi ağının tek bir merkezden, kullanıcı dostu bir arayüzle yönetilmesine imkan tanır.

## 🎯 Proje Amacı
Projenin temel amacı, firmanın iş süreçlerini uçtan uca kayıt altına alarak operasyonel verimliliği maksimize etmektir. Bu doğrultuda uygulama şu hedefleri gerçekleştirmektedir:

**Finansal Takip:** Tüm gelir ve gider kalemlerini belirli bir düzen içerisinde saklayarak mali disiplini sağlamak.
**Performans Ölçümleme:** Firmanın günlük, aylık veya seçilen özel tarih aralıklarındaki performansını ölçeklenebilir verilerle ortaya koymak.
**Stratejik Raporlama:** Biriken ham verileri anlamlı istatistiklere ve detaylı raporlara dönüştürerek, yönetimin veriye dayalı kararlar almasına yardımcı olmak.     
**İş İlişkileri Yönetimi:** Hizmet sunulan müşteriler ve hizmet alınan alt yükleniciler ile olan tüm ticari/operasyonel süreçleri hatasız ve izlenebilir bir yapıda takip etmek.

---
## 🎯 PROJE İŞ AKIŞI ALGORİTMASI:

## 1.Bölüm: Kaynak Yönetimi (Veri Girşi
Bu aşamada faaliyetin yürütülmesi için gerekli olan ana tanımlamalar yapılır.         
**Personeller & Sürücüler**: Şirket çalışanları ve araç sürücüleri sisteme kaydedilir.       
**Müşteriler:** Hizmet sunulan veya alınan tüm gerçek/tüzel kişiler (Cariler) sisteme işlenir.        
**Araçlar & Araç Bakım:** Hizmette kullanılacak araçlar ve bu araçların rutin bakım/onarım bilgileri kayıt altına alınır.

## 2.Bölüm:Operasyonel Süreç (Planlama ve İcra)
Kaydedilen kaynaklar bu bölümde bir iş planına dönüştürülür.

**Sözleşmeler:** Müşteriler ile yapılan işin süresi, bedeli ve sorumlulukları belirlenir.    
**Rota Planlama:** Sözleşme kapsamındaki işin başlangıç ve bitiş noktaları planlanır.    
**Seferler:** Planlanan rotanın günlük olarak hangi araç, sürücü ve güzergahla yapılacağı sisteme girilir.  
**Puantaj:** Seferlerin fiili olarak gerçekleşme durumu ve günlük sefer sayıları kaydedilir.  

## 3. Bölüm: Finansal ve Analitik Sonuçlar (Çıktı)
Operasyondan gelen veriler bu bölümde mali değere ve rapora dönüşür.

**Hakedişler:** Puantaj modülünden gelen verilere göre kişi alacakları otomatik hesaplanır.  
**Mali Yönetim:** Tüm gelir ve giderler birleşerek genel gelir-gider dengesi analiz edilir.  
**Raporlar:** Tüm sistem verileri istatistiksel ve yazılı çıktılar haline getirilir.  

## 4. Bölüm: Sistem Denetimi (Teknik Yapı)
Sistemin kısıtları ve yetkileri bu bölümden yönetilir.

**Kullanıcılar:** Yetki ve rol atamaları yapılır.  
**Sabit Bilgiler:** Diğer modüllere veri sınırı ve standartlar koyulur.  
**Ayarlar:** Sistemsel sorunların çözümü ve yapılandırmalar yönetilir. 

## 🧩 Modüller
- **Kullanıcılar**
- **Personeller**
- **Müşteriler**
- **Araçlar**
- **Şoförler**
- **Araç Bakım**
- **Sözleşmeler**
- **Rota Planlama**
- **Seferler**
- **Puantajlar**
- **Hakedişler**
- **Mali Yönetim**
- **Sabit Bilgiler**
- **Raporlar**
- **Ayarlar**

---

# Algoritmanın Mantıksal Döngüsü
 *Sözleşme varsa -> Rota Planlaması yapılır.  
 *Rota Planlaması varsa -> Sefer tanımlanır.  
 *Sefer yapıldıysa -> Puantaj işlenir.  
 *Puantaj varsa -> Hakediş hesaplanır.  
 *Hakediş ve Giderler varsa -> Mali Yönetim raporu oluşur.

---

## 🖥️ Teknoloji ve Yapı
- **Dil:** Python 3.13+
- **GUI Framework:** PyQt6 - Qt Designer  
- **Veritabanı:** SQLite (`xxxxxxxx.db`)
- **Yapılandırma:** `config.py`
- **Versiyon Kontrol:** Git & GitHub

---

## 🚀 Geliştirme Durumu
Proje şu anda **geliştirme aşamasında** olup,  
öncelikli olarak ana menü, kullanıcı giriş ve personel modülleri tamamlanmıştır.

---

## 👤 Geliştirici
**Ayhan Ercan**  
Sakarya / Türkiye  
📧 [GitHub Profili](https://github.com/AyhanErcan70)

---

> “Sağlam temelle başlamak, uzun yolun ilk kazancıdır.”
