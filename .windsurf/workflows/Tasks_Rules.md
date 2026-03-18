---
description: Proje bağlamı, hedefler, modüller ve mevcut aşama notları
---

# 🚌 S.A.T.T.U.P – Sakarya Asil Tur Taşımacılık Uygulaması Projesi

**S.A.T.T.U.P** (Sakarya Asil Tur Taşımacılık Uygulaması Projesi),  
öğrenci ve personel taşıma hizmetleri için geliştirilmiş bir masaüstü uygulamadır.  
Proje, Python yazılım dili ile, arayüzü de PyQt6 kütüphanesi kullanılarak geliştirilmektedir.

---

## 🎯 Proje Amacı
Bu uygulama; Personel taşıma ve Öğrenci taşıma hizmeti ile araç kiralama hizmetlerinin, sözleşme, puantaj, hakediş ve mali yönetim süreçlerinin  
tek bir arayüz üzerinden kolayca yönetilmesini hedefler.

---

## 🎯 GitHub deposu
https://github.com/AyhanErcan70/SATTUP
default branch: main
Visibility repository: Public

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
- **Sabitler**
- **Raporlar**
- **Ayarlar**


---

## 🖥️ Teknoloji ve Yapı
- **Dil:** Python 3.12.8
- **GUI Framework:** PyQt6  
- **Veritabanı:** SQLite (`asil_system.db`)
- **Versiyon Kontrol:** Git & GitHub

---

## 🚀 Geliştirme Durumu
Projenin şu anda biten (ancak genel ve karşılaştırmalı testleri tam yapılmamış) modülleri: 

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
- **Hakedişler** (eksik kalan yerleri var)
- **Sabitler**
---

## 🚀 Şuan Hangi Aşamada (en son yapılanlar)

Hesaplamaya esas kullanılan; "Sözleşmeler, Rota Planlama, Seferler ve Hakedişler" modüllerinin karşılaştırmalı test aşaması. 
- En son yapılan test: Bir müşterinin Ocak ayı Puantaj kayıtları işlenerek, modüllerde eksik/fazla objeler var mı, kullanıcı için kullanım kolaylıklarına yönelik geliştirilebilirliği ve Hakediş modülüne load edilen verilerin doğru hesaplanıp hesaplanmadığı ve doğru inputlara load edilip edilmediğinin testi.

## NOTLAR:

- Programı kullanacak olan firma personeli (bundan sonra "kullanıcı" olarak anılacaktır)uzun yıllardır firmanın proje amacındaki işlemlerini Excel Tablolarıyla manuel olarak yapmış olması ve mevcut alışkanlıklarından vazgeçememesi nedniyle proje programımızın kullanımı ve arayüzü excel tablolarına benzerlik hedefli olarak  geliştirilmektedir. 
- Karşılaştırmalı test anlamı: Şuan kullanıcı excel tablosu ile işlerini devam etmektedir. aynı zamanda gerçek verilerin programa dahil edilerek aynı işlemler programda da yürütülmekte ve sonuçları karşılaştırılarak, olası hataları tespit etme aşaması. 
- Programın geliştiricisinin aynı zamanda firma sahipleriyle dostane ilişkilerinin olması ve programı firmanın işyerinde yazmaya çalışıyor olmasının karşılaştırmalı test aşamasındaki avantajı olarak düşünülebilir.

## 👤 Geliştirici
**Ayhan Ercan**  
Sakarya / Türkiye  
📧 [GitHub Profili](https://github.com/AyhanErcan70)

---

> “Sağlam temelle başlamak, uzun yolun ilk kazancıdır.”
