# Dev Notes (Routes)

## Amaç
Routes modülünü (customer -> contract -> rota -> final tablo) stabil çalışır hale getirmek.

## Son durum (07.01.2026)
- Routes modülünde `table_rota` sözleşme seçilince bazen hiç dolmuyor.
- `table_son` tablosunda son kolon "MESAFE (KM)" bazen görünmüyor/boş kalıyor.

## UI doğrulama
`ui/ui_files/routes_window.ui` içeriğine göre kolonlar:
- `table_rota`: 5 kolon
  - 0: HİZMET TİPİ
  - 1: GÜZERGAH ADI
  - 2: BAŞLANGIÇ NOKTASI
  - 3: DURAKLAR
  - 4: MESAFE (KM)
- `table_son`: 7 kolon
  - 0: SÖZLEŞME KODU
  - 1: BAŞLAMA TARİHİ
  - 2: BİTİŞ TARİHİ
  - 3: HİZMET TİPİ
  - 4: GÜZERGAH ADI
  - 5: NOKTALAR
  - 6: MESAFE (KM)

## Yapılan kod değişiklikleri (özet)
Dosya: `app/modules/routes.py`
- `table_rota` ve `table_son` için kolon sayısı runtime'da garanti altına alındı:
  - `_init_tables()` içinde:
    - `table_rota.columnCount() < 5` ise `setColumnCount(5)`
    - `table_son.columnCount() < 7` ise `setColumnCount(7)`
  - Load öncesi ekstra güvence:
    - `_load_contract_details_and_fill_rota()` başında `table_rota` için aynı kontrol
    - `_load_saved_routes_for_contract()` başında `table_son` için aynı kontrol

- `price_matrix_json` boşsa rota verisi `route_params` tablosundan fallback ile alınıyor.
- Fallback ile gelen satırlarda `table_rota` artık NOKTALAR kolonlarını da dolduruyor:
  - start_point -> col 2
  - stops -> col 3
  - distance_km -> col 4

## Hâlâ problem varsa (muhtemel kök nedenler)
1) Sözleşmede `price_matrix_json` boş ve `route_params` tablosunda o sözleşmeye ait kayıt yok.
2) `route_params.contract_id` yanlış/uyuşmuyor. Bu durumda fallback sorgusu genişletilebilir:
   - `contract_number` üzerinden eşleme gibi.

## Test planı (manuel)
1) Routes ekranı aç.
2) Müşteri seç.
3) Sözleşme seç.
4) Beklenen:
   - `table_rota` dolu gelmeli (en az 1 satır).
   - `table_son` dolu gelmeli ve col 6 KM görünmeli.

Senaryo A: `price_matrix_json` dolu sözleşme.
Senaryo B: `price_matrix_json` boş, `route_params` dolu sözleşme.

## Bir sonraki adım
- Eğer Senaryo B'de hâlâ `table_rota` boşsa:
  - DB'de `route_params` kaydı var mı kontrol et.
  - Gerekirse fallback sorgusunu `contract_number` ile genişlet.
