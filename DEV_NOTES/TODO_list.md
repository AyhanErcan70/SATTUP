#46 in_progress (high)
Toplu Puantaj UI'ını DEV_NOTES/puantaj_ornek_net2.xlsx ile birebir aynı algıda olacak şekilde tasarla (satır/sütun düzeni, başlıklar, özet satırları, 2/1/0 mantığı ve gerektiğinde aynı gün için 2 satır 1 girilebilmesi)
#49 completed (high)
Toplu Puantaj: satırları plan/time_blocks'tan üret (trip_plan(_new) + trip_time_blocks) ve Excel'deki çok satırlı giriş/çıkış saatlerini otomatik oluştur
#50 completed (high)
Puantaj kilitleme öncesi zorunluluk kontrolü: planlı satırlarda ilgili ayın tüm günleri 2/1/0 girilmiş mi? (boş hücre bırakma engeli)
#57 completed (medium)
Toplu Puantaj: planlı satırları gridde görsel olarak vurgula (renk/etiket)
#55 pending (high)
Toplu Puantaj: default fiyatı sözleşme fiyat matrisinden otomatik getir (trip_prices yoksa) (şimdilik manuel bıraktık)
#56 completed (high)
Toplu Puantaj: kaydetme performansı (bulk upsert / sadece değişen hücreleri yaz) ve kaydet sırasında pencere kapanınca crash olmaması
#53 completed (high)
Toplu Puantaj: fiyat sütununu kalıcı yap (DB'ye kaydet/yükle) ve toplam bedeli popup açılışında yeniden hesapla
#54 pending (medium)
Fiyat otomasyonu: ileride rota/sözleşme fiyat modelinden (contract pricing) otomatik fiyat çek ve satır fiyatlarını kilitle/override destekle
#35 in_progress (high)
Puantaj modülü (GERÇEKLEŞEN): günlük grid yoklama + allocation girişi; Onayla (kilitle) / admin-only Onay Kaldır; trip_entries + trip_allocations kaydet/yükle
#40 in_progress (high)
Toplu Puantaj popup'ını AttendanceApp'e entegre et ve trip_entries/trip_allocations'a yazacak şekilde adapte et
#45 pending (low)
Geçici debug print’lerini temizle (Attendance) ve log spam’ini azalt
#51 pending (high)
Puantaj modülü tamamlanınca: projeyi yedekle, repo'yu sıfırdan initialize et ve GitHub'a temiz push (branch, .gitignore, ilk tag/release)
#52 pending (medium)
Ev/iş çalışma düzeni: GitHub workflow (pull/push), DB ve config taşıma, zip yedek standardı ve kısa dokümantasyon