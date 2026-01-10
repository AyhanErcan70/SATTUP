# Trips (Seferler) UI Builder Notes

Bu not, yeni Seferler (Excel-grid) UI dosyasını hazırlarken Qt Designer/Creator kaynaklı engellere takılmamak için hazırlanmıştır.

## Sorun 1: QSplitter ekleyemiyorum
Bu problem bloklayıcı değil.

### Çözüm
QSplitter yerine layout kullan:
- Root `QWidget` → `QVBoxLayout` (`verticalLayout_root` gibi)
- Üste: `frame_filters` (QFrame)
- Ortaya: `frame_body` (QFrame)
  - `frame_body` içine `QHBoxLayout` (`hbox_body`)
  - `hbox_body` içine:
    - Sol: `tbl_grid` (QTableWidget)
    - Sağ: `frame_side` (QFrame) (not + allocation paneli)
- Alta: `frame_actions` (QFrame)

QSplitter’ın tek avantajı sürükleyerek genişlik ayarıydı; layout ile de çok iyi çalışır.

## Sorun 2: `editTriggers` değiştiremiyorum
Bu da bloklayıcı değil.

### Çözüm
`QTableWidget` ve benzeri property’leri UI’dan değil Python kodundan set edeceğiz.

Örnek (tbl_grid):
- `tbl_grid.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)`
- `tbl_grid.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)`
- `tbl_grid.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)`
- `tbl_grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)`

`tbl_alloc` (allocation tablosu) için edit açık olacak.

## Minimum zorunlu widget listesi (objectName’ler birebir olmalı)
### Filtreler
- `cmb_period` (QComboBox)
- `cmb_musteri` (QComboBox)
- `cmb_sozlesme` (QComboBox)
- `date_month` (QDateEdit) (opsiyonel)
- `lbl_pricing_type_value` (QLabel)

### Grid
- `tbl_grid` (QTableWidget)

### Not
- `txt_note` (QPlainTextEdit)
- `btn_note_save` (QPushButton)
- `btn_note_clear` (QPushButton)

### Allocation
- `tbl_alloc` (QTableWidget)
- `btn_alloc_add` (QPushButton)
- `btn_alloc_del` (QPushButton)
- `btn_alloc_save` (QPushButton)

### Varsayılan Kaynak
- `cmb_default_vehicle` (QComboBox)
- `cmb_default_driver` (QComboBox)
- `btn_apply_default_to_selection` (QPushButton)

### Aksiyonlar
- `btn_reload` (QPushButton)
- `btn_save` (QPushButton)
- `btn_lock_period` (QPushButton)
- `btn_close` (QPushButton)

## Grid hücre davranışı (UI’da değil kodda)
- DAILY (SHIFT): `"" -> 2 -> 1 -> ""`
- PER_TRIP (TRIP): `"" -> 1 -> ""`

Bu döngü `tbl_grid.cellClicked` üzerinden uygulanacak.
