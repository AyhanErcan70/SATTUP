# DB Schema: `c:\Users\ayhan\SATTUP\database\asil_system.db`

## TABLE: `arac_bakim`

### Columns

- `id` INTEGER PK
- `vehicle_code` TEXT NOT NULL
- `bakim_tarihi` TEXT
- `bakim_km` INTEGER
- `bakim_turu` TEXT
- `firma_adi` TEXT
- `yapilan_islemler` TEXT
- `maliyet` REAL DEFAULT 0
- `fis_no` TEXT
- `sonraki_bakim_tarihi` TEXT
- `muhasebe_durum` INTEGER DEFAULT 0
- `created_at` TEXT
- `updated_at` TEXT

### Foreign Keys

- `vehicle_code` -> `vehicles`.`vehicle_code` (on_update=NO ACTION, on_delete=NO ACTION)

## TABLE: `bulk_puantaj_manual_rows`

### Columns

- `id` INTEGER PK
- `contract_id` INTEGER NOT NULL
- `month` TEXT NOT NULL
- `service_type` TEXT NOT NULL
- `sort_order` INTEGER NOT NULL DEFAULT 0
- `guzergah` TEXT
- `vehicle_id` TEXT
- `driver_id` TEXT
- `movement_type` TEXT
- `time_text` TEXT
- `unit_price` REAL DEFAULT 0
- `day_qty_json` TEXT
- `created_at` TEXT
- `updated_at` TEXT

### Indexes

- `idx_bulk_puantaj_manual_rows_ctx` (`contract_id`, `month`, `service_type`) origin=c

## TABLE: `constants`

### Columns

- `id` INTEGER PK
- `group_name` TEXT NOT NULL
- `value` TEXT NOT NULL
- `parent_id` INTEGER

### Foreign Keys

- `parent_id` -> `constants`.`id` (on_update=NO ACTION, on_delete=NO ACTION)

## TABLE: `contract_links`

### Columns

- `id` INTEGER PK
- `main_contract_id` INTEGER NOT NULL
- `subcontract_contract_id` INTEGER NOT NULL
- `is_active` INTEGER DEFAULT 1
- `created_at` TEXT
- `updated_at` TEXT

### Foreign Keys

- `subcontract_contract_id` -> `contracts`.`id` (on_update=NO ACTION, on_delete=NO ACTION)
- `main_contract_id` -> `contracts`.`id` (on_update=NO ACTION, on_delete=NO ACTION)

### Indexes

- `idx_contract_links_sub` (`subcontract_contract_id`) origin=c
- `idx_contract_links_main` (`main_contract_id`) origin=c
- `sqlite_autoindex_contract_links_1` (`main_contract_id`, `subcontract_contract_id`) UNIQUE origin=u

## TABLE: `contract_pricing_model_history`

### Columns

- `id` INTEGER PK
- `contract_id` INTEGER NOT NULL
- `effective_from` TEXT NOT NULL
- `pricing_model` TEXT NOT NULL
- `note` TEXT
- `created_at` TEXT

### Indexes

- `idx_cpmh_key` (`contract_id`, `effective_from`) origin=c
- `sqlite_autoindex_contract_pricing_model_history_1` (`contract_id`, `effective_from`) UNIQUE origin=u

## TABLE: `contract_special_items`

### Columns

- `id` INTEGER PK
- `contract_id` INTEGER NOT NULL
- `period` TEXT NOT NULL
- `service_type` TEXT NOT NULL
- `title` TEXT
- `date_from` TEXT
- `date_to` TEXT
- `time_text` TEXT
- `distance_km` REAL NOT NULL DEFAULT 0
- `qty_days` REAL NOT NULL DEFAULT 0
- `unit_price` REAL NOT NULL DEFAULT 0
- `total_amount` REAL NOT NULL DEFAULT 0
- `note` TEXT
- `created_at` TEXT
- `updated_at` TEXT

### Indexes

- `idx_csi_key` (`contract_id`, `period`, `service_type`) origin=c

## TABLE: `contracts`

### Columns

- `id` INTEGER PK
- `customer_id` INTEGER
- `contract_number` TEXT
- `isin_tanimi` TEXT
- `contract_type` TEXT
- `odeme_usulu` TEXT DEFAULT 0
- `ucret_tipi` TEXT
- `start_date` TEXT
- `end_date` TEXT
- `is_active` INTEGER DEFAULT 1
- `uzatma` INTEGER DEFAULT 0
- `toplam_tutar` REAL
- `kdv_orani` REAL
- `price_matrix_json` TEXT
- `arac_adedi` INTEGER
- `esnek_sefer` INTEGER DEFAULT 0
- `vardiya` INTEGER
- `mesai` INTEGER
- `ek_ozel` INTEGER

### Foreign Keys

- `customer_id` -> `customers`.`id` (on_update=NO ACTION, on_delete=NO ACTION)

### Indexes

- `sqlite_autoindex_contracts_1` (`contract_number`) UNIQUE origin=u

## TABLE: `customers`

### Columns

- `id` INTEGER PK
- `customer_code` TEXT
- `title` TEXT NOT NULL
- `tax_office` TEXT
- `tax_number` TEXT
- `address` TEXT
- `phone` TEXT
- `email` TEXT
- `is_active` INTEGER DEFAULT 1
- `musteri_turu` TEXT
- `kisilik` TEXT
- `sektor` TEXT
- `yetkili` TEXT
- `gorevi` TEXT
- `il` TEXT
- `ilce` TEXT
- `adres1` TEXT
- `adres2` TEXT
- `bakiye` REAL DEFAULT 0
- `iban` TEXT
- `vergi_dairesi` TEXT
- `pricing_model` TEXT DEFAULT 'VARDIYALI'

### Indexes

- `sqlite_autoindex_customers_1` (`customer_code`) UNIQUE origin=u

## TABLE: `driver_documents`

### Columns

- `id` INTEGER PK
- `personel_kodu` TEXT NOT NULL
- `ehliyet_sinifi` TEXT
- `ehliyet_tarihi` TEXT
- `src_durumu` INTEGER DEFAULT 0
- `src_turu` TEXT
- `src_tarihi` TEXT
- `psikoteknik_durumu` INTEGER DEFAULT 0
- `psikoteknik_tarihi` TEXT
- `sertifika_durumu` INTEGER DEFAULT 0
- `sertifika_metni` TEXT
- `resim_yolu` TEXT
- `updated_at` TEXT

### Foreign Keys

- `personel_kodu` -> `employees`.`personel_kodu` (on_update=NO ACTION, on_delete=NO ACTION)

### Indexes

- `sqlite_autoindex_driver_documents_1` (`personel_kodu`) UNIQUE origin=u

## TABLE: `employees`

### Columns

- `personel_kodu` TEXT PK
- `personel_turu` TEXT
- `tckn` TEXT
- `ad_soyad` TEXT
- `anne_adi` TEXT
- `baba_adi` TEXT
- `dogum_yeri` TEXT
- `dogum_tarihi` TEXT
- `gsm` TEXT
- `email` TEXT
- `gorevi` TEXT
- `kan_grubu` TEXT
- `il` TEXT
- `ilce` TEXT
- `adres1` TEXT
- `adres2` TEXT
- `banka_adi` TEXT
- `iban` TEXT
- `notlar1` TEXT
- `notlar2` TEXT
- `is_active` INTEGER DEFAULT 1
- `photo_path` TEXT

### Indexes

- `sqlite_autoindex_employees_1` (`personel_kodu`) UNIQUE origin=pk

## TABLE: `hakedis`

### Columns

- `id` INTEGER PK
- `contract_id` INTEGER NOT NULL
- `period` TEXT NOT NULL
- `service_type` TEXT
- `route_params_id` INTEGER
- `status` TEXT DEFAULT 'TASLAK'
- `total_amount` REAL DEFAULT 0
- `deduction_amount` REAL DEFAULT 0
- `net_amount` REAL DEFAULT 0
- `notes` TEXT
- `created_at` TEXT
- `updated_at` TEXT
- `approved_at` TEXT
- `invoiced_at` TEXT

### Indexes

- `idx_hakedis_key` (`contract_id`, `period`, `service_type`, `route_params_id`) origin=c
- `sqlite_autoindex_hakedis_1` (`contract_id`, `period`, `service_type`, `route_params_id`) UNIQUE origin=u

## TABLE: `hakedis_deductions`

### Columns

- `id` INTEGER PK
- `hakedis_id` INTEGER NOT NULL
- `deduction_type` TEXT
- `amount` REAL DEFAULT 0
- `description` TEXT
- `created_at` TEXT
- `updated_at` TEXT

### Indexes

- `idx_hakedis_deductions_parent` (`hakedis_id`) origin=c

## TABLE: `hakedis_docs`

### Columns

- `id` INTEGER PK
- `hakedis_id` INTEGER NOT NULL
- `doc_type` TEXT
- `file_name` TEXT
- `file_path` TEXT
- `uploaded_at` TEXT
- `note` TEXT
- `description` TEXT
- `created_at` TEXT
- `updated_at` TEXT

### Indexes

- `idx_hakedis_docs_hakedis` (`hakedis_id`) origin=c
- `idx_hakedis_docs_parent` (`hakedis_id`) origin=c

## TABLE: `hakedis_items`

### Columns

- `id` INTEGER PK
- `hakedis_id` INTEGER NOT NULL
- `item_date` TEXT
- `route_params_id` INTEGER
- `vehicle_id` INTEGER
- `driver_id` INTEGER
- `work_type` TEXT
- `quantity` REAL DEFAULT 0
- `unit_price` REAL DEFAULT 0
- `amount` REAL DEFAULT 0
- `description` TEXT
- `source_trip_id` INTEGER
- `created_at` TEXT
- `updated_at` TEXT

### Indexes

- `idx_hakedis_items_parent` (`hakedis_id`) origin=c

## TABLE: `period_close`

### Columns

- `month` TEXT PK
- `closed` INTEGER NOT NULL DEFAULT 0
- `closed_at` TEXT
- `closed_by_user_id` INTEGER
- `note` TEXT

### Indexes

- `sqlite_autoindex_period_close_1` (`month`) UNIQUE origin=pk

## TABLE: `route_params`

### Columns

- `id` INTEGER PK
- `contract_id` INTEGER NOT NULL
- `contract_number` TEXT
- `start_date` TEXT
- `end_date` TEXT
- `service_type` TEXT
- `route_name` TEXT
- `start_point` TEXT
- `stops` TEXT
- `distance_km` REAL
- `created_at` TEXT
- `movement_type` TEXT
- `vehicle_capacity` REAL

### Foreign Keys

- `contract_id` -> `contracts`.`id` (on_update=NO ACTION, on_delete=NO ACTION)

## TABLE: `trip_allocations`

### Columns

- `id` INTEGER PK
- `contract_id` INTEGER NOT NULL
- `route_params_id` INTEGER NOT NULL
- `trip_date` TEXT NOT NULL
- `service_type` TEXT NOT NULL
- `time_block` TEXT NOT NULL
- `line_no` INTEGER NOT NULL DEFAULT 0
- `driver_id` INTEGER
- `vehicle_id` INTEGER
- `qty` REAL NOT NULL DEFAULT 0
- `time_text` TEXT
- `note` TEXT
- `created_at` TEXT
- `updated_at` TEXT

### Indexes

- `idx_trip_allocations_key2` (`contract_id`, `route_params_id`, `trip_date`, `service_type`, `time_block`, `line_no`) origin=c
- `idx_trip_allocations_key` (`contract_id`, `trip_date`, `service_type`, `time_block`) origin=c
- `idx_trip_allocations_contract_date` (`contract_id`, `trip_date`) origin=c
- `sqlite_autoindex_trip_allocations_1` (`contract_id`, `route_params_id`, `trip_date`, `service_type`, `time_block`, `line_no`) UNIQUE origin=u

## TABLE: `trip_entries`

### Columns

- `id` INTEGER PK
- `contract_id` INTEGER NOT NULL
- `route_params_id` INTEGER NOT NULL
- `trip_date` TEXT NOT NULL
- `service_type` TEXT NOT NULL
- `time_block` TEXT NOT NULL
- `line_no` INTEGER NOT NULL DEFAULT 0
- `qty` INTEGER NOT NULL DEFAULT 0
- `time_text` TEXT
- `note` TEXT
- `created_at` TEXT
- `updated_at` TEXT

### Indexes

- `idx_trip_entries_contract_date` (`contract_id`, `trip_date`) origin=c
- `sqlite_autoindex_trip_entries_1` (`contract_id`, `route_params_id`, `trip_date`, `service_type`, `time_block`, `line_no`) UNIQUE origin=u

## TABLE: `trip_period_lock`

### Columns

- `id` INTEGER PK
- `contract_id` INTEGER NOT NULL
- `month` TEXT NOT NULL
- `service_type` TEXT NOT NULL
- `locked` INTEGER NOT NULL DEFAULT 0
- `locked_at` TEXT
- `locked_by_user_id` INTEGER
- `unlocked_by_user_id` INTEGER
- `unlocked_at` TEXT
- `unlock_reason` TEXT

### Indexes

- `sqlite_autoindex_trip_period_lock_1` (`contract_id`, `month`, `service_type`) UNIQUE origin=u

## TABLE: `trip_plan`

### Columns

- `id` INTEGER PK
- `contract_id` INTEGER NOT NULL
- `route_params_id` INTEGER NOT NULL
- `month` TEXT NOT NULL
- `service_type` TEXT NOT NULL
- `time_block` TEXT NOT NULL
- `vehicle_id` TEXT
- `driver_id` TEXT
- `note` TEXT
- `created_at` TEXT
- `updated_at` TEXT

### Indexes

- `sqlite_autoindex_trip_plan_1` (`contract_id`, `route_params_id`, `month`, `service_type`, `time_block`) UNIQUE origin=u

## TABLE: `trip_prices`

### Columns

- `id` INTEGER PK
- `contract_id` INTEGER NOT NULL
- `route_params_id` INTEGER NOT NULL
- `month` TEXT NOT NULL
- `service_type` TEXT NOT NULL
- `time_block` TEXT NOT NULL
- `price` REAL NOT NULL DEFAULT 0
- `updated_at` TEXT
- `pricing_category` TEXT DEFAULT ''
- `effective_from` TEXT DEFAULT ''
- `subcontractor_price` REAL NOT NULL DEFAULT 0

### Indexes

- `idx_trip_prices_effective` (`contract_id`, `service_type`, `route_params_id`, `pricing_category`, `effective_from`) origin=c
- `idx_trip_prices_key` (`contract_id`, `month`, `service_type`) origin=c
- `sqlite_autoindex_trip_prices_1` (`contract_id`, `route_params_id`, `month`, `service_type`, `time_block`) UNIQUE origin=u

## TABLE: `trip_time_blocks`

### Columns

- `id` INTEGER PK
- `contract_id` INTEGER NOT NULL
- `month` TEXT NOT NULL
- `service_type` TEXT NOT NULL
- `custom1` TEXT
- `custom2` TEXT
- `created_at` TEXT
- `updated_at` TEXT

### Indexes

- `sqlite_autoindex_trip_time_blocks_1` (`contract_id`, `month`, `service_type`) UNIQUE origin=u

## TABLE: `trips`

### Columns

- `id` INTEGER PK
- `contract_id` INTEGER
- `vehicle_id` INTEGER
- `user_id` INTEGER
- `trip_date` TEXT
- `route_info` TEXT
- `status` TEXT DEFAULT 'Planned'

### Foreign Keys

- `user_id` -> `users`.`id` (on_update=NO ACTION, on_delete=NO ACTION)
- `vehicle_id` -> `vehicles`.`id` (on_update=NO ACTION, on_delete=NO ACTION)
- `contract_id` -> `contracts`.`id` (on_update=NO ACTION, on_delete=NO ACTION)

## TABLE: `users`

### Columns

- `id` INTEGER PK
- `username` TEXT NOT NULL
- `password` TEXT NOT NULL
- `full_name` TEXT
- `role` TEXT
- `is_active` INTEGER DEFAULT 1

### Indexes

- `sqlite_autoindex_users_1` (`username`) UNIQUE origin=u

## TABLE: `vehicles`

### Columns

- `id` INTEGER PK
- `plate_number` TEXT NOT NULL
- `brand` TEXT
- `model` TEXT
- `capacity` INTEGER
- `fuel_type` TEXT
- `daily_cost` REAL DEFAULT 0
- `is_active` INTEGER DEFAULT 1
- `vehicle_code` TEXT
- `arac_turu` TEXT
- `hizmet_turu` TEXT
- `kategori` TEXT
- `yil` INTEGER
- `muayene_tarihi` TEXT
- `sigorta_tarihi` TEXT
- `koltuk_tarihi` TEXT
- `kasko_tarihi` TEXT
- `calisma_ruhsati_tarihi` TEXT
- `guzergah_izin_tarihi` TEXT
- `arac_takip` INTEGER DEFAULT 0
- `arac_cam` INTEGER DEFAULT 0
- `arac_sahibi` TEXT
- `photo_path` TEXT
- `supplier_customer_id` INTEGER

### Indexes

- `idx_vehicles_vehicle_code` (`vehicle_code`) UNIQUE origin=c
- `sqlite_autoindex_vehicles_1` (`plate_number`) UNIQUE origin=u
