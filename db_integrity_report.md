# DB Integrity Report

- **DB**: `c:\Users\ayhan\SATTUP\database\asil_system.db`

## [MED] Orphan plan rows (missing route)

- Orphan count: **418** (trip_plan.route_params_id not in route_params.id)

## [INFO] Row counts (high level)

- trip_plan: 1900
- trip_allocations: 1556
- trip_entries: 1281
- hakedis: 0
- hakedis_items: 0

## [INFO] service_type variants in trip_allocations

- Distinct values: **1**
- trip_allocations.service_type='PERSONEL TAŞIMA' -> 1556

## [INFO] service_type variants in trip_entries

- Distinct values: **1**
- trip_entries.service_type='PERSONEL TAŞIMA' -> 1281

## [INFO] service_type variants in trip_plan

- Distinct values: **1**
- trip_plan.service_type='PERSONEL TAŞIMA' -> 1900

## [INFO] service_type variants in trip_prices

- Distinct values: **1**
- trip_prices.service_type='PERSONEL TAŞIMA' -> 2273
