import sqlite3
import os
from datetime import datetime
from config import DB_PATH, BASE_DIR

class DatabaseManager:
    def __init__(self):
        self.db_path = DB_PATH
        self.create_tables()
        self.migrate_contracts_table()
        self.migrate_trip_plan_table()
        self.migrate_trip_period_lock_table()
        self.create_trip_entries_tables()
        self._ensure_trip_prices_table()
        self.create_hakedis_tables()
        self.create_customers_table()
        self.create_vehicles_table()
        self.create_contract_links_table()
        self.create_repairs_table()
        self.create_employees_table()
        self.create_driver_documents_table()
        self.create_constants_table()
    
    def connect(self):
        try:
            # check_same_thread=False ekliyoruz ki farklı modüllerden erişirken sorun çıkmasın
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            return conn
        except Exception as e:
            print(f"Database connection error: {e}")
            return None

    def create_tables(self):
        conn = self.connect()
        if conn:
            cursor = conn.cursor()
            
            # 1. USERS (Personeller/Kullanıcılar)
            cursor.execute("""CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                full_name TEXT,
                role TEXT,
                is_active INTEGER DEFAULT 1
            )""")

            # 2. CUSTOMERS (Müşteriler)
            cursor.execute("""CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_code TEXT UNIQUE,
                title TEXT NOT NULL,
                tax_office TEXT,
                tax_number TEXT,
                address TEXT,
                phone TEXT,
                email TEXT,
                is_active INTEGER DEFAULT 1
            )""")

            # 3. VEHICLES (Araçlar)
            cursor.execute("""CREATE TABLE IF NOT EXISTS vehicles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_number TEXT UNIQUE NOT NULL,
                brand TEXT,
                model TEXT,
                capacity INTEGER,
                fuel_type TEXT,
                daily_cost REAL DEFAULT 0,
                is_active INTEGER DEFAULT 1
            )""")

            # 4. CONTRACTS (Sözleşmeler)
            cursor.execute("""CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                contract_number TEXT UNIQUE,
                start_date TEXT,
                end_date TEXT,
                contract_type TEXT,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (customer_id) REFERENCES customers (id)
            )""")

            # 5. TRIPS (Seferler - Operasyonun Kalbi)
            cursor.execute("""CREATE TABLE IF NOT EXISTS trips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_id INTEGER,
                vehicle_id INTEGER,
                user_id INTEGER,
                trip_date TEXT,
                route_info TEXT,
                status TEXT DEFAULT 'Planned',
                FOREIGN KEY (contract_id) REFERENCES contracts (id),
                FOREIGN KEY (vehicle_id) REFERENCES vehicles (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )""")

            cursor.execute("""CREATE TABLE IF NOT EXISTS trip_plan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_id INTEGER NOT NULL,
                route_params_id INTEGER NOT NULL,
                month TEXT NOT NULL,
                service_type TEXT NOT NULL,
                time_block TEXT NOT NULL,
                vehicle_id TEXT,
                driver_id TEXT,
                note TEXT,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE (contract_id, route_params_id, month, service_type, time_block)
            )""")

            cursor.execute("""CREATE TABLE IF NOT EXISTS trip_time_blocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_id INTEGER NOT NULL,
                month TEXT NOT NULL,
                service_type TEXT NOT NULL,
                custom1 TEXT,
                custom2 TEXT,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE (contract_id, month, service_type)
            )""")

            cursor.execute("""CREATE TABLE IF NOT EXISTS trip_period_lock (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_id INTEGER NOT NULL,
                month TEXT NOT NULL,
                service_type TEXT NOT NULL,
                locked INTEGER NOT NULL DEFAULT 0,
                locked_at TEXT,
                UNIQUE (contract_id, month, service_type)
            )""")
            cursor.execute("SELECT COUNT(*) FROM users")
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO users (username, password, full_name, role, is_active)
                    VALUES ('admin', '1234', 'SATTUP Admin', 'admin', 1)
                """)
                print("Bilgi: İlk admin kullanıcısı (admin/1234) oluşturuldu.")

            conn.commit()
            conn.close()

    def create_trip_entries_tables(self):
        conn = self.connect()
        if not conn:
            return
        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS trip_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contract_id INTEGER NOT NULL,
                    route_params_id INTEGER NOT NULL,
                    trip_date TEXT NOT NULL,
                    service_type TEXT NOT NULL,
                    time_block TEXT NOT NULL,
                    line_no INTEGER NOT NULL DEFAULT 0,
                    qty INTEGER NOT NULL DEFAULT 0,
                    time_text TEXT,
                    note TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    UNIQUE (contract_id, route_params_id, trip_date, service_type, time_block, line_no)
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS trip_allocations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contract_id INTEGER NOT NULL,
                    route_params_id INTEGER NOT NULL,
                    trip_date TEXT NOT NULL,
                    service_type TEXT NOT NULL,
                    time_block TEXT NOT NULL,
                    line_no INTEGER NOT NULL DEFAULT 0,
                    driver_id INTEGER,
                    vehicle_id INTEGER,
                    qty REAL NOT NULL DEFAULT 0,
                    time_text TEXT,
                    note TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    UNIQUE (contract_id, route_params_id, trip_date, service_type, time_block, line_no)
                )
                """
            )

            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_trip_entries_contract_date ON trip_entries(contract_id, trip_date)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_trip_allocations_contract_date ON trip_allocations(contract_id, trip_date)"
            )
            conn.commit()
        finally:
            conn.close()

        # trip_entries/trip_allocations eski DB'lerde line_no kolonuna sahip olmayabilir.
        self.migrate_trip_entries_allocations_line_no()

        # trip_allocations eski DB'lerde time_block kolonuna sahip olmayabilir.
        # Migration'ı index oluşturmadan önce çalıştır.
        self.migrate_trip_allocations_table()

        conn2 = self.connect()
        if not conn2:
            return
        try:
            cursor2 = conn2.cursor()
            cursor2.execute(
                "CREATE INDEX IF NOT EXISTS idx_trip_allocations_key ON trip_allocations(contract_id, trip_date, service_type, time_block)"
            )
            cursor2.execute(
                "CREATE INDEX IF NOT EXISTS idx_trip_allocations_key2 ON trip_allocations(contract_id, route_params_id, trip_date, service_type, time_block, line_no)"
            )
            conn2.commit()
        finally:
            conn2.close()

    def create_contract_links_table(self):
        conn = self.connect()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS contract_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    main_contract_id INTEGER NOT NULL,
                    subcontract_contract_id INTEGER NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT,
                    updated_at TEXT,
                    UNIQUE (main_contract_id, subcontract_contract_id),
                    FOREIGN KEY (main_contract_id) REFERENCES contracts (id),
                    FOREIGN KEY (subcontract_contract_id) REFERENCES contracts (id)
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_contract_links_main ON contract_links(main_contract_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_contract_links_sub ON contract_links(subcontract_contract_id)"
            )
            conn.commit()
        finally:
            conn.close()

    def migrate_trip_entries_allocations_line_no(self):
        conn = self.connect()
        if not conn:
            return
        try:
            cur = conn.cursor()

            # trip_entries
            try:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trip_entries'")
                if cur.fetchone() is not None:
                    cur.execute("PRAGMA table_info(trip_entries)")
                    cols = {row[1] for row in (cur.fetchall() or [])}
                    if "line_no" not in cols:
                        cur.execute(
                            """
                            CREATE TABLE IF NOT EXISTS trip_entries_new (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                contract_id INTEGER NOT NULL,
                                route_params_id INTEGER NOT NULL,
                                trip_date TEXT NOT NULL,
                                service_type TEXT NOT NULL,
                                time_block TEXT NOT NULL,
                                line_no INTEGER NOT NULL DEFAULT 0,
                                qty INTEGER NOT NULL DEFAULT 0,
                                time_text TEXT,
                                note TEXT,
                                created_at TEXT,
                                updated_at TEXT,
                                UNIQUE (contract_id, route_params_id, trip_date, service_type, time_block, line_no)
                            )
                            """
                        )
                        cur.execute(
                            """
                            INSERT INTO trip_entries_new (
                                id, contract_id, route_params_id, trip_date, service_type, time_block,
                                line_no, qty, time_text, note, created_at, updated_at
                            )
                            SELECT
                                id, contract_id, route_params_id, trip_date, service_type, time_block,
                                0, qty, time_text, note, created_at, updated_at
                            FROM trip_entries
                            """
                        )
                        cur.execute("DROP TABLE trip_entries")
                        cur.execute("ALTER TABLE trip_entries_new RENAME TO trip_entries")
                        cur.execute(
                            "CREATE INDEX IF NOT EXISTS idx_trip_entries_contract_date ON trip_entries(contract_id, trip_date)"
                        )
            except Exception:
                pass

            # trip_allocations
            try:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trip_allocations'")
                if cur.fetchone() is not None:
                    cur.execute("PRAGMA table_info(trip_allocations)")
                    cols2 = {row[1] for row in (cur.fetchall() or [])}
                    if "line_no" not in cols2:
                        cur.execute(
                            """
                            CREATE TABLE IF NOT EXISTS trip_allocations_new2 (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                contract_id INTEGER NOT NULL,
                                route_params_id INTEGER NOT NULL,
                                trip_date TEXT NOT NULL,
                                service_type TEXT NOT NULL,
                                time_block TEXT NOT NULL,
                                line_no INTEGER NOT NULL DEFAULT 0,
                                driver_id INTEGER,
                                vehicle_id INTEGER,
                                qty REAL NOT NULL DEFAULT 0,
                                time_text TEXT,
                                note TEXT,
                                created_at TEXT,
                                updated_at TEXT,
                                UNIQUE (contract_id, route_params_id, trip_date, service_type, time_block, line_no)
                            )
                            """
                        )
                        cur.execute(
                            """
                            INSERT INTO trip_allocations_new2 (
                                id, contract_id, route_params_id, trip_date, service_type, time_block,
                                line_no, driver_id, vehicle_id, qty, time_text, note, created_at, updated_at
                            )
                            SELECT
                                id, contract_id, route_params_id, trip_date, service_type, time_block,
                                0, driver_id, vehicle_id, qty, time_text, note, created_at, updated_at
                            FROM trip_allocations
                            """
                        )
                        cur.execute("DROP TABLE trip_allocations")
                        cur.execute("ALTER TABLE trip_allocations_new2 RENAME TO trip_allocations")
                        cur.execute(
                            "CREATE INDEX IF NOT EXISTS idx_trip_allocations_contract_date ON trip_allocations(contract_id, trip_date)"
                        )
                        cur.execute(
                            "CREATE INDEX IF NOT EXISTS idx_trip_allocations_key ON trip_allocations(contract_id, trip_date, service_type, time_block)"
                        )
            except Exception:
                pass

            conn.commit()
        finally:
            conn.close()

    def upsert_hakedis_header(
        self,
        contract_id: int,
        period: str,
        service_type: str | None = None,
        route_params_id: int | None = None,
        status: str = "TASLAK",
    ) -> int | None:
        self.create_hakedis_tables()
        conn = self.connect()
        if not conn:
            return None
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rp_id = int(route_params_id) if route_params_id is not None else 0
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO hakedis (
                    contract_id, period, service_type, route_params_id,
                    status, total_amount, deduction_amount, net_amount,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
                ON CONFLICT(contract_id, period, service_type, route_params_id)
                DO UPDATE SET
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (
                    int(contract_id),
                    str(period),
                    (service_type or "").strip() or None,
                    rp_id,
                    (status or "TASLAK").strip(),
                    now,
                    now,
                ),
            )

            cur.execute(
                """
                SELECT id
                FROM hakedis
                WHERE contract_id=? AND period=?
                  AND COALESCE(service_type,'') = ?
                  AND COALESCE(route_params_id, 0) = ?
                LIMIT 1
                """,
                (
                    int(contract_id),
                    str(period),
                    (service_type or "").strip(),
                    rp_id,
                ),
            )
            row = cur.fetchone()
            conn.commit()
            return int(row[0]) if row and row[0] is not None else None
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"upsert_hakedis_header error: {e}")
            return None
        finally:
            conn.close()

    def replace_hakedis_items(self, hakedis_id: int, items: list[dict]) -> bool:
        self.create_hakedis_tables()
        conn = self.connect()
        if not conn:
            return False
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM hakedis_items WHERE hakedis_id = ?", (int(hakedis_id),))

            for it in items or []:
                cur.execute(
                    """
                    INSERT INTO hakedis_items (
                        hakedis_id, item_date, route_params_id, vehicle_id, driver_id,
                        work_type, quantity, unit_price, amount, description, source_trip_id,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(hakedis_id),
                        (it.get("item_date") or ""),
                        it.get("route_params_id"),
                        it.get("vehicle_id"),
                        it.get("driver_id"),
                        (it.get("work_type") or ""),
                        float(it.get("quantity") or 0),
                        float(it.get("unit_price") or 0),
                        float(it.get("amount") or 0),
                        (it.get("description") or ""),
                        it.get("source_trip_id"),
                        now,
                        now,
                    ),
                )

            conn.commit()
            return True
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"replace_hakedis_items error: {e}")
            return False
        finally:
            conn.close()

    def update_hakedis_totals(self, hakedis_id: int) -> bool:
        self.create_hakedis_tables()
        conn = self.connect()
        if not conn:
            return False
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COALESCE(SUM(amount), 0)
                FROM hakedis_items
                WHERE hakedis_id = ?
                """,
                (int(hakedis_id),),
            )
            total = float((cur.fetchone() or [0])[0] or 0)

            cur.execute(
                """
                SELECT COALESCE(SUM(amount), 0)
                FROM hakedis_deductions
                WHERE hakedis_id = ?
                """,
                (int(hakedis_id),),
            )
            deduction = float((cur.fetchone() or [0])[0] or 0)
            net = float(total - deduction)

            cur.execute(
                """
                UPDATE hakedis
                SET total_amount=?, deduction_amount=?, net_amount=?, updated_at=?
                WHERE id = ?
                """,
                (float(total), float(deduction), float(net), now, int(hakedis_id)),
            )
            conn.commit()
            return True
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"update_hakedis_totals error: {e}")
            return False
        finally:
            conn.close()

    def create_hakedis_tables(self):
        conn = self.connect()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS hakedis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contract_id INTEGER NOT NULL,
                    period TEXT NOT NULL,
                    service_type TEXT,
                    route_params_id INTEGER,
                    status TEXT DEFAULT 'TASLAK',
                    total_amount REAL DEFAULT 0,
                    deduction_amount REAL DEFAULT 0,
                    net_amount REAL DEFAULT 0,
                    notes TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    approved_at TEXT,
                    invoiced_at TEXT,
                    UNIQUE (contract_id, period, service_type, route_params_id)
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_hakedis_key ON hakedis(contract_id, period, service_type, route_params_id)"
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS hakedis_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hakedis_id INTEGER NOT NULL,
                    item_date TEXT,
                    route_params_id INTEGER,
                    vehicle_id INTEGER,
                    driver_id INTEGER,
                    work_type TEXT,
                    quantity REAL DEFAULT 0,
                    unit_price REAL DEFAULT 0,
                    amount REAL DEFAULT 0,
                    description TEXT,
                    source_trip_id INTEGER,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_hakedis_items_parent ON hakedis_items(hakedis_id)"
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS hakedis_deductions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hakedis_id INTEGER NOT NULL,
                    deduction_type TEXT,
                    amount REAL DEFAULT 0,
                    description TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_hakedis_deductions_parent ON hakedis_deductions(hakedis_id)"
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS hakedis_docs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hakedis_id INTEGER NOT NULL,
                    doc_type TEXT,
                    file_name TEXT,
                    file_path TEXT,
                    uploaded_at TEXT,
                    description TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_hakedis_docs_hakedis ON hakedis_docs(hakedis_id)"
            )

            # Migration: eski db'lerde hakedis_docs kolonları eksik olabilir
            try:
                cursor.execute("PRAGMA table_info(hakedis_docs)")
                cols = [row[1] for row in (cursor.fetchall() or [])]
                if "description" not in cols:
                    cursor.execute("ALTER TABLE hakedis_docs ADD COLUMN description TEXT")
                if "created_at" not in cols:
                    cursor.execute("ALTER TABLE hakedis_docs ADD COLUMN created_at TEXT")
                if "updated_at" not in cols:
                    cursor.execute("ALTER TABLE hakedis_docs ADD COLUMN updated_at TEXT")
            except Exception:
                pass

            conn.commit()

            # NULL route_params_id alanında UNIQUE çalışmadığı için aynı anahtar tekrarı oluşabiliyor.
            # Genel hakediş için route_params_id'yi 0 normalize ediyoruz.
            self._migrate_hakedis_route_params_default(conn)
        finally:
            conn.close()

    def _migrate_hakedis_route_params_default(self, conn) -> None:
        try:
            cur = conn.cursor()

            # Duplicate kayıtları birleştir (NULL ve 0 aynı kabul).
            cur.execute(
                """
                SELECT contract_id,
                       period,
                       COALESCE(service_type,'') AS st,
                       COALESCE(route_params_id,0) AS rp,
                       COUNT(*) AS cnt
                FROM hakedis
                GROUP BY contract_id, period, st, rp
                HAVING cnt > 1
                """
            )
            dups = cur.fetchall() or []

            for contract_id, period, st, rp, _cnt in dups:
                cur.execute(
                    """
                    SELECT id
                    FROM hakedis
                    WHERE contract_id=? AND period=?
                      AND COALESCE(service_type,'')=?
                      AND COALESCE(route_params_id,0)=?
                    ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
                    LIMIT 1
                    """,
                    (int(contract_id), str(period), str(st), int(rp)),
                )
                keep_row = cur.fetchone()
                if not keep_row or keep_row[0] is None:
                    continue
                keep_id = int(keep_row[0])

                cur.execute(
                    """
                    SELECT id
                    FROM hakedis
                    WHERE contract_id=? AND period=?
                      AND COALESCE(service_type,'')=?
                      AND COALESCE(route_params_id,0)=?
                      AND id <> ?
                    """,
                    (int(contract_id), str(period), str(st), int(rp), int(keep_id)),
                )
                other_ids = [int(x[0]) for x in (cur.fetchall() or []) if x and x[0] is not None]

                for old_id in other_ids:
                    cur.execute(
                        "UPDATE hakedis_items SET hakedis_id=? WHERE hakedis_id=?",
                        (int(keep_id), int(old_id)),
                    )
                    cur.execute(
                        "UPDATE hakedis_deductions SET hakedis_id=? WHERE hakedis_id=?",
                        (int(keep_id), int(old_id)),
                    )
                    cur.execute(
                        "UPDATE hakedis_docs SET hakedis_id=? WHERE hakedis_id=?",
                        (int(keep_id), int(old_id)),
                    )
                    cur.execute("DELETE FROM hakedis WHERE id=?", (int(old_id),))

            # NULL olanları 0'a çek.
            cur.execute("UPDATE hakedis SET route_params_id=0 WHERE route_params_id IS NULL")
            conn.commit()
        except Exception as e:
            print(f"_migrate_hakedis_route_params_default error: {e}")
            try:
                conn.rollback()
            except Exception:
                pass

    def list_hakedis(
        self,
        contract_id: int | None = None,
        period: str | None = None,
        service_type: str | None = None,
        route_params_id: int | None = None,
        status: str | None = None,
        only_missing_docs: bool = False,
    ):
        self.create_hakedis_tables()
        conn = self.connect()
        if not conn:
            return []
        try:
            where = []
            params = []

            if contract_id is not None:
                where.append("h.contract_id = ?")
                params.append(int(contract_id))
            if period:
                where.append("h.period = ?")
                params.append(str(period))
            if service_type:
                where.append("COALESCE(h.service_type,'') = ?")
                params.append(str(service_type))
            if route_params_id is not None:
                where.append("COALESCE(h.route_params_id, 0) = ?")
                params.append(int(route_params_id))
            if status and str(status).strip() and str(status).strip().upper() != "TÜMÜ" and str(status).strip().upper() != "TUMU":
                where.append("COALESCE(h.status,'') = ?")
                params.append(str(status))
            if only_missing_docs:
                where.append(
                    "NOT EXISTS (SELECT 1 FROM hakedis_docs d WHERE d.hakedis_id = h.id LIMIT 1)"
                )

            where_sql = ("WHERE " + " AND ".join(where)) if where else ""

            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT
                    h.id,
                    COALESCE(h.period,''),
                    COALESCE(c.contract_number,''),
                    COALESCE(h.service_type,''),
                    COALESCE(rp.route_name,''),
                    COALESCE(h.total_amount,0),
                    COALESCE(h.deduction_amount,0),
                    COALESCE(h.net_amount,0),
                    COALESCE(h.status,''),
                    COALESCE(h.updated_at, COALESCE(h.created_at,''))
                FROM hakedis h
                LEFT JOIN contracts c ON c.id = h.contract_id
                LEFT JOIN route_params rp ON rp.id = h.route_params_id
                {where_sql}
                ORDER BY h.period DESC, h.id DESC
                """,
                tuple(params),
            )
            return cur.fetchall() or []
        finally:
            conn.close()

    def get_hakedis_items_rows(self, hakedis_id: int):
        self.create_hakedis_tables()
        conn = self.connect()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    COALESCE(i.item_date,''),
                    COALESCE(rp.route_name,''),
                    COALESCE(v.plate_number,''),
                    COALESCE(e.ad_soyad,''),
                    COALESCE(i.work_type,''),
                    COALESCE(i.quantity,0),
                    COALESCE(i.unit_price,0),
                    COALESCE(i.amount,0),
                    COALESCE(i.description,'')
                FROM hakedis_items i
                LEFT JOIN route_params rp ON rp.id = i.route_params_id
                LEFT JOIN vehicles v ON v.vehicle_code = i.vehicle_id
                LEFT JOIN employees e ON e.personel_kodu = i.driver_id
                WHERE i.hakedis_id = ?
                ORDER BY COALESCE(i.item_date,''), COALESCE(rp.route_name,''), COALESCE(i.work_type,'')
                """,
                (int(hakedis_id),),
            )
            return cur.fetchall() or []
        finally:
            conn.close()

    def get_hakedis_deductions_rows(self, hakedis_id: int):
        self.create_hakedis_tables()
        conn = self.connect()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    COALESCE(d.deduction_type,''),
                    COALESCE(d.amount,0),
                    COALESCE(d.description,'')
                FROM hakedis_deductions d
                WHERE d.hakedis_id = ?
                ORDER BY d.id
                """,
                (int(hakedis_id),),
            )
            return cur.fetchall() or []
        finally:
            conn.close()

    def get_hakedis_deductions_ui_rows(self, hakedis_id: int):
        self.create_hakedis_tables()
        conn = self.connect()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    d.id,
                    COALESCE(d.deduction_type,''),
                    COALESCE(d.amount,0),
                    COALESCE(d.description,'')
                FROM hakedis_deductions d
                WHERE d.hakedis_id = ?
                ORDER BY d.id
                """,
                (int(hakedis_id),),
            )
            return cur.fetchall() or []
        finally:
            conn.close()

    def add_hakedis_deduction(
        self,
        hakedis_id: int,
        deduction_type: str,
        amount: float,
        description: str = "",
    ) -> int | None:
        self.create_hakedis_tables()
        conn = self.connect()
        if not conn:
            return None
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO hakedis_deductions (
                    hakedis_id, deduction_type, amount, description, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(hakedis_id),
                    str(deduction_type or "").strip(),
                    float(amount or 0),
                    str(description or "").strip(),
                    now,
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid) if cur.lastrowid is not None else None
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"add_hakedis_deduction error: {e}")
            return None
        finally:
            conn.close()

    def delete_hakedis_deduction(self, deduction_id: int) -> bool:
        self.create_hakedis_tables()
        conn = self.connect()
        if not conn:
            return False
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM hakedis_deductions WHERE id = ?", (int(deduction_id),))
            conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"delete_hakedis_deduction error: {e}")
            return False
        finally:
            conn.close()

    def get_hakedis_docs_rows(self, hakedis_id: int):
        self.create_hakedis_tables()
        conn = self.connect()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    SELECT
                        COALESCE(doc_type,''),
                        COALESCE(file_name,''),
                        COALESCE(file_path,''),
                        COALESCE(uploaded_at,''),
                        COALESCE(description,'')
                    FROM hakedis_docs
                    WHERE hakedis_id = ?
                    ORDER BY id
                    """,
                    (int(hakedis_id),),
                )
            except sqlite3.OperationalError as e:
                # Eski DB'lerde hakedis_docs kolonları eksik olabiliyor; otomatik migrate edip tekrar dene.
                msg = str(e or "")
                if "no such column" in msg and "description" in msg:
                    try:
                        cur.execute("ALTER TABLE hakedis_docs ADD COLUMN description TEXT DEFAULT ''")
                    except Exception:
                        pass
                    try:
                        cur.execute("ALTER TABLE hakedis_docs ADD COLUMN created_at TEXT")
                    except Exception:
                        pass
                    try:
                        cur.execute("ALTER TABLE hakedis_docs ADD COLUMN updated_at TEXT")
                    except Exception:
                        pass
                    try:
                        conn.commit()
                    except Exception:
                        pass
                    cur.execute(
                        """
                        SELECT
                            COALESCE(doc_type,''),
                            COALESCE(file_name,''),
                            COALESCE(file_path,''),
                            COALESCE(uploaded_at,''),
                            COALESCE(description,'')
                        FROM hakedis_docs
                        WHERE hakedis_id = ?
                        ORDER BY id
                        """,
                        (int(hakedis_id),),
                    )
                else:
                    raise
            return cur.fetchall() or []
        finally:
            conn.close()

    def get_hakedis_docs_ui_rows(self, hakedis_id: int):
        self.create_hakedis_tables()
        conn = self.connect()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    SELECT
                        id,
                        COALESCE(doc_type,''),
                        COALESCE(file_name,''),
                        COALESCE(file_path,''),
                        COALESCE(uploaded_at,''),
                        COALESCE(description,'')
                    FROM hakedis_docs
                    WHERE hakedis_id = ?
                    ORDER BY id
                    """,
                    (int(hakedis_id),),
                )
            except sqlite3.OperationalError as e:
                msg = str(e or "")
                if "no such column" in msg and "description" in msg:
                    try:
                        cur.execute("ALTER TABLE hakedis_docs ADD COLUMN description TEXT DEFAULT ''")
                    except Exception:
                        pass
                    try:
                        cur.execute("ALTER TABLE hakedis_docs ADD COLUMN created_at TEXT")
                    except Exception:
                        pass
                    try:
                        cur.execute("ALTER TABLE hakedis_docs ADD COLUMN updated_at TEXT")
                    except Exception:
                        pass
                    try:
                        conn.commit()
                    except Exception:
                        pass
                    cur.execute(
                        """
                        SELECT
                            id,
                            COALESCE(doc_type,''),
                            COALESCE(file_name,''),
                            COALESCE(file_path,''),
                            COALESCE(uploaded_at,''),
                            COALESCE(description,'')
                        FROM hakedis_docs
                        WHERE hakedis_id = ?
                        ORDER BY id
                        """,
                        (int(hakedis_id),),
                    )
                else:
                    raise
            return cur.fetchall() or []
        finally:
            conn.close()

    def add_hakedis_doc(
        self,
        hakedis_id: int,
        doc_type: str,
        file_name: str,
        file_path: str,
        uploaded_at: str,
        description: str = "",
    ) -> int | None:
        self.create_hakedis_tables()
        conn = self.connect()
        if not conn:
            return None
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO hakedis_docs (
                    hakedis_id, doc_type, file_name, file_path, uploaded_at, description, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(hakedis_id),
                    str(doc_type or "").strip(),
                    str(file_name or "").strip(),
                    str(file_path or "").strip(),
                    str(uploaded_at or "").strip(),
                    str(description or "").strip(),
                    now,
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid) if cur.lastrowid is not None else None
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"add_hakedis_doc error: {e}")
            return None
        finally:
            conn.close()

    def delete_hakedis_doc(self, doc_id: int) -> bool:
        self.create_hakedis_tables()
        conn = self.connect()
        if not conn:
            return False
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM hakedis_docs WHERE id = ?", (int(doc_id),))
            conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"delete_hakedis_doc error: {e}")
            return False
        finally:
            conn.close()

    def set_hakedis_status(self, hakedis_id: int, status: str) -> bool:
        self.create_hakedis_tables()
        conn = self.connect()
        if not conn:
            return False
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st = str(status or "").strip().upper()
        try:
            cur = conn.cursor()
            if st == "ONAYLANDI":
                cur.execute(
                    """
                    UPDATE hakedis
                    SET status=?, approved_at=COALESCE(approved_at, ?), updated_at=?
                    WHERE id=?
                    """,
                    ("ONAYLANDI", now, now, int(hakedis_id)),
                )
            elif st == "FATURALANDI":
                cur.execute(
                    """
                    UPDATE hakedis
                    SET status=?, invoiced_at=COALESCE(invoiced_at, ?), updated_at=?
                    WHERE id=?
                    """,
                    ("FATURALANDI", now, now, int(hakedis_id)),
                )
            else:
                cur.execute(
                    """
                    UPDATE hakedis
                    SET status=?, updated_at=?
                    WHERE id=?
                    """,
                    (str(status or "").strip(), now, int(hakedis_id)),
                )

            conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"set_hakedis_status error: {e}")
            return False
        finally:
            conn.close()

    def month_has_operational_template(self, month: str) -> bool:
        """Seçilen ay için şablon veri var mı? (trip_plan / trip_prices / trip_time_blocks)"""
        self._ensure_trip_prices_table()
        conn = self.connect()
        if not conn:
            return False
        try:
            cur = conn.cursor()
            m = str(month)
            cur.execute("SELECT COUNT(*) FROM trip_plan WHERE month=?", (m,))
            c1 = int((cur.fetchone() or [0])[0] or 0)
            cur.execute("SELECT COUNT(*) FROM trip_prices WHERE month=?", (m,))
            c2 = int((cur.fetchone() or [0])[0] or 0)
            cur.execute("SELECT COUNT(*) FROM trip_time_blocks WHERE month=?", (m,))
            c3 = int((cur.fetchone() or [0])[0] or 0)
            return (c1 + c2 + c3) > 0
        except Exception:
            return False
        finally:
            conn.close()

    def has_trip_plan_for_context(self, contract_id: int, month: str, service_types: list[str]) -> bool:
        """Belirli sözleşme + ay + hizmet tipleri için trip_plan var mı?"""
        conn = self.connect()
        if not conn:
            return False
        try:
            st = [str(x) for x in (service_types or []) if str(x).strip()]
            if not st:
                return False
            placeholders = ",".join(["?"] * len(st))
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT 1
                FROM trip_plan
                WHERE contract_id=? AND month=? AND service_type IN ({placeholders})
                LIMIT 1
                """,
                (int(contract_id), str(month), *st),
            )
            return cur.fetchone() is not None
        except Exception:
            return False
        finally:
            conn.close()

    def copy_month_operational_template(self, from_month: str, to_month: str) -> bool:
        """Önceki aydan operasyonel şablon verilerini yeni aya kopyalar.

        Kopyalananlar:
        - trip_plan
        - trip_prices
        - trip_time_blocks
        Kopyalanmayanlar:
        - trip_entries / trip_allocations (fiili gerçekleşen veriler)
        """
        self._ensure_trip_prices_table()
        conn = self.connect()
        if not conn:
            return False
        try:
            cur = conn.cursor()
            fm = str(from_month)
            tm = str(to_month)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # trip_plan
            cur.execute(
                """
                INSERT INTO trip_plan (
                    contract_id, route_params_id, month, service_type, time_block,
                    vehicle_id, driver_id, note, created_at, updated_at
                )
                SELECT
                    contract_id, route_params_id, ?, service_type, time_block,
                    vehicle_id, driver_id, note, ?, ?
                FROM trip_plan
                WHERE month = ?
                ON CONFLICT(contract_id, route_params_id, month, service_type, time_block)
                DO UPDATE SET
                    vehicle_id=excluded.vehicle_id,
                    driver_id=excluded.driver_id,
                    note=excluded.note,
                    updated_at=excluded.updated_at
                """,
                (tm, now, now, fm),
            )

            # trip_prices
            cur.execute(
                """
                INSERT INTO trip_prices (
                    contract_id, route_params_id, month, service_type, time_block, price, updated_at
                )
                SELECT
                    contract_id, route_params_id, ?, service_type, time_block, price, ?
                FROM trip_prices
                WHERE month = ?
                ON CONFLICT(contract_id, route_params_id, month, service_type, time_block)
                DO UPDATE SET
                    price=excluded.price,
                    updated_at=excluded.updated_at
                """,
                (tm, now, fm),
            )

            # trip_time_blocks
            cur.execute(
                """
                INSERT INTO trip_time_blocks (
                    contract_id, month, service_type, custom1, custom2, created_at, updated_at
                )
                SELECT
                    contract_id, ?, service_type, custom1, custom2, ?, ?
                FROM trip_time_blocks
                WHERE month = ?
                ON CONFLICT(contract_id, month, service_type)
                DO UPDATE SET
                    custom1=excluded.custom1,
                    custom2=excluded.custom2,
                    updated_at=excluded.updated_at
                """,
                (tm, now, now, fm),
            )

            conn.commit()
            return True
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"copy_month_operational_template error: {e}")
            return False
        finally:
            conn.close()

    def migrate_trip_allocations_table(self):
        conn = self.connect()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trip_allocations'")
            if cursor.fetchone() is None:
                return

            cursor.execute("PRAGMA table_info(trip_allocations)")
            cols = [row[1] for row in (cursor.fetchall() or [])]
            if "time_block" in cols:
                return

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS trip_allocations_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contract_id INTEGER NOT NULL,
                    route_params_id INTEGER NOT NULL,
                    trip_date TEXT NOT NULL,
                    service_type TEXT NOT NULL,
                    time_block TEXT NOT NULL,
                    line_no INTEGER NOT NULL DEFAULT 0,
                    driver_id INTEGER,
                    vehicle_id INTEGER,
                    qty REAL NOT NULL DEFAULT 0,
                    time_text TEXT,
                    note TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    UNIQUE (contract_id, route_params_id, trip_date, service_type, time_block, line_no)
                )
                """
            )

            cursor.execute(
                """
                INSERT INTO trip_allocations_new (
                    id, contract_id, route_params_id, trip_date, service_type, time_block,
                    line_no, driver_id, vehicle_id, qty, time_text, note, created_at, updated_at
                )
                SELECT
                    id, contract_id, route_params_id, trip_date, service_type, 'GUN',
                    0, driver_id, vehicle_id, qty, time_text, note, created_at, updated_at
                FROM trip_allocations
                """
            )
            cursor.execute("DROP TABLE trip_allocations")
            cursor.execute("ALTER TABLE trip_allocations_new RENAME TO trip_allocations")

            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_trip_allocations_contract_date ON trip_allocations(contract_id, trip_date)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_trip_allocations_key ON trip_allocations(contract_id, trip_date, service_type, time_block)"
            )

            conn.commit()
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"Trip allocations migration error: {e}")
        finally:
            conn.close()

    def upsert_trip_allocation(
        self,
        contract_id: int,
        route_params_id: int,
        trip_date: str,
        service_type: str,
        time_block: str,
        vehicle_id,
        driver_id,
        qty: float,
        time_text: str = "",
        note: str = "",
        line_no: int = 0,
    ) -> bool:
        conn = self.connect()
        if not conn:
            return False
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trip_allocations (
                    contract_id, route_params_id, trip_date, service_type, time_block, line_no,
                    vehicle_id, driver_id, qty, time_text, note, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(contract_id, route_params_id, trip_date, service_type, time_block, line_no)
                DO UPDATE SET
                    vehicle_id=excluded.vehicle_id,
                    driver_id=excluded.driver_id,
                    qty=excluded.qty,
                    time_text=excluded.time_text,
                    note=excluded.note,
                    updated_at=excluded.updated_at
                """
            ,
                (
                    int(contract_id),
                    int(route_params_id),
                    str(trip_date),
                    str(service_type),
                    str(time_block),
                    int(line_no or 0),
                    vehicle_id,
                    driver_id,
                    float(qty or 0),
                    str(time_text or ""),
                    str(note or ""),
                    now,
                    now,
                ),
            )
            conn.commit()
            return True
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            return False
        finally:
            conn.close()

    def get_trip_allocations_for_range(self, contract_id: int, service_type: str, start_date: str, end_date: str):
        conn = self.connect()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT route_params_id, trip_date, time_block, line_no, vehicle_id, driver_id, qty, COALESCE(time_text,''), COALESCE(note,'')
                FROM trip_allocations
                WHERE contract_id = ?
                  AND service_type = ?
                  AND trip_date BETWEEN ? AND ?
                ORDER BY route_params_id, time_block, trip_date, line_no
                """,
                (int(contract_id), str(service_type), str(start_date), str(end_date)),
            )
            return cursor.fetchall() or []
        finally:
            conn.close()

    def _ensure_trip_prices_table(self):
        conn = self.connect()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS trip_prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contract_id INTEGER NOT NULL,
                    route_params_id INTEGER NOT NULL,
                    month TEXT NOT NULL,
                    service_type TEXT NOT NULL,
                    time_block TEXT NOT NULL,
                    price REAL NOT NULL DEFAULT 0,
                    updated_at TEXT,
                    UNIQUE (contract_id, route_params_id, month, service_type, time_block)
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_trip_prices_key ON trip_prices(contract_id, month, service_type)"
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_trip_price(
        self,
        contract_id: int,
        route_params_id: int,
        month: str,
        service_type: str,
        time_block: str,
        price: float,
    ) -> bool:
        self._ensure_trip_prices_table()
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                """
                INSERT INTO trip_prices (
                    contract_id, route_params_id, month, service_type, time_block, price, updated_at
                )
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(contract_id, route_params_id, month, service_type, time_block)
                DO UPDATE SET price=excluded.price, updated_at=excluded.updated_at
                """,
                (
                    int(contract_id),
                    int(route_params_id),
                    str(month),
                    str(service_type),
                    str(time_block),
                    float(price or 0.0),
                    now,
                ),
            )
            conn.commit()
            return True
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            return False
        finally:
            conn.close()

    def get_trip_prices_for_month(self, contract_id: int, month: str, service_type: str):
        self._ensure_trip_prices_table()
        conn = self.connect()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT route_params_id, time_block, price
                FROM trip_prices
                WHERE contract_id = ? AND month = ? AND service_type = ?
                """,
                (int(contract_id), str(month), str(service_type)),
            )
            return cursor.fetchall()
        finally:
            conn.close()

    def get_vehicle_subcontract_meta(self, vehicle_id: int):
        """Return (arac_turu, supplier_customer_id) for given vehicles.id."""
        conn = self.connect()
        if not conn:
            return ("", None)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COALESCE(arac_turu,''), supplier_customer_id
                FROM vehicles
                WHERE id = ?
                LIMIT 1
                """,
                (int(vehicle_id),),
            )
            row = cur.fetchone()
            if not row:
                return ("", None)
            arac_turu = str(row[0] or "")
            sid = row[1]
            try:
                sid_i = int(sid) if sid is not None and str(sid).strip() != "" else None
            except Exception:
                sid_i = None
            return (arac_turu, sid_i)
        finally:
            conn.close()

    def get_contract_price_matrix_json(self, contract_id: int) -> str:
        conn = self.connect()
        if not conn:
            return ""
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT COALESCE(price_matrix_json,'') FROM contracts WHERE id=? LIMIT 1",
                (int(contract_id),),
            )
            row = cur.fetchone()
            return (row[0] if row else "") or ""
        finally:
            conn.close()

    def resolve_subcontract_contract_id(
        self,
        main_contract_id: int,
        supplier_customer_id: int,
        trip_date: str,
    ) -> int | None:
        """Resolve subcontract contract (contracts.id) for a subcontractor customer on a date.

        Strategy:
        - Candidates: active contracts of supplier_customer_id.
        - Filter by date range if start/end are provided.
        - If multiple remain, prefer those linked via contract_links(main_contract_id -> subcontract_contract_id).
        """
        candidates = self.get_active_contracts_by_customer(int(supplier_customer_id))
        if not candidates:
            return None

        def _in_range(d: str, s: str, e: str) -> bool:
            ds = str(d or "").strip()
            ss = str(s or "").strip()
            es = str(e or "").strip()
            if not ds:
                return False
            if ss and ds < ss:
                return False
            if es and ds > es:
                return False
            return True

        filtered: list[tuple[int, str, str, str]] = []
        for cid, _cno, s, e in candidates:
            try:
                cid_i = int(cid)
            except Exception:
                continue
            if _in_range(str(trip_date or ""), str(s or ""), str(e or "")):
                filtered.append((cid_i, str(_cno or ""), str(s or ""), str(e or "")))

        if not filtered:
            # If no date match, fall back to latest active contract.
            try:
                return int(candidates[0][0])
            except Exception:
                return None

        if len(filtered) == 1:
            return int(filtered[0][0])

        # Disambiguate using contract_links if available.
        conn = self.connect()
        if not conn:
            return int(filtered[0][0])
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT subcontract_contract_id
                FROM contract_links
                WHERE main_contract_id = ?
                  AND COALESCE(is_active,1)=1
                """,
                (int(main_contract_id),),
            )
            linked = {int(r[0]) for r in (cur.fetchall() or []) if r and r[0] is not None}
        except Exception:
            linked = set()
        finally:
            conn.close()

        if linked:
            for cid_i, _cno, _s, _e in filtered:
                if int(cid_i) in linked:
                    return int(cid_i)

        return int(filtered[0][0])

    def get_trip_period_lock(self, contract_id: int, month: str, service_type: str):
        conn = self.connect()
        if not conn:
            return None
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT locked, locked_at, locked_by_user_id, unlocked_at, unlocked_by_user_id, unlock_reason
                FROM trip_period_lock
                WHERE contract_id = ? AND month = ? AND service_type = ?
                """,
                (int(contract_id), str(month), str(service_type)),
            )
            row = cursor.fetchone()
            if not row:
                return {
                    "locked": 0,
                    "locked_at": None,
                    "locked_by_user_id": None,
                    "unlocked_at": None,
                    "unlocked_by_user_id": None,
                    "unlock_reason": None,
                }
            return {
                "locked": int(row[0] or 0),
                "locked_at": row[1],
                "locked_by_user_id": row[2],
                "unlocked_at": row[3],
                "unlocked_by_user_id": row[4],
                "unlock_reason": row[5],
            }
        finally:
            conn.close()

    def set_trip_period_locked(self, contract_id: int, month: str, service_type: str, user_id: int):
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trip_period_lock (
                    contract_id, month, service_type, locked, locked_at, locked_by_user_id,
                    unlocked_at, unlocked_by_user_id, unlock_reason
                )
                VALUES (?, ?, ?, 1, datetime('now'), ?, NULL, NULL, NULL)
                ON CONFLICT(contract_id, month, service_type)
                DO UPDATE SET
                    locked = 1,
                    locked_at = datetime('now'),
                    locked_by_user_id = excluded.locked_by_user_id,
                    unlocked_at = NULL,
                    unlocked_by_user_id = NULL,
                    unlock_reason = NULL
                """,
                (int(contract_id), str(month), str(service_type), int(user_id)),
            )
            conn.commit()
            return True
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            return False
        finally:
            conn.close()

    def set_trip_period_unlocked(
        self,
        contract_id: int,
        month: str,
        service_type: str,
        admin_user_id: int,
        reason: str,
    ):
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trip_period_lock (
                    contract_id, month, service_type, locked, locked_at, locked_by_user_id,
                    unlocked_at, unlocked_by_user_id, unlock_reason
                )
                VALUES (?, ?, ?, 0, NULL, NULL, datetime('now'), ?, ?)
                ON CONFLICT(contract_id, month, service_type)
                DO UPDATE SET
                    locked = 0,
                    unlocked_at = datetime('now'),
                    unlocked_by_user_id = excluded.unlocked_by_user_id,
                    unlock_reason = excluded.unlock_reason
                """,
                (int(contract_id), str(month), str(service_type), int(admin_user_id), (reason or "").strip()),
            )
            conn.commit()
            return True
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            return False
        finally:
            conn.close()

    def migrate_contracts_table(self):
        conn = self.connect()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(contracts)")
            cols = {row[1] for row in cursor.fetchall()}
            migrations = [
                ("uzatma", "INTEGER DEFAULT 0"),
                ("arac_adedi", "INTEGER"),
                ("esnek_sefer", "INTEGER DEFAULT 0"),
                ("ucret_tipi", "TEXT"),
                ("toplam_tutar", "REAL"),
                ("kdv_orani", "REAL"),
                ("price_matrix_json", "TEXT"),
                ("isin_tanimi", "TEXT"),
                ("odeme_usulu", "TEXT"),
                ("vardiya", "INTEGER"),
                ("mesai", "INTEGER"),
                ("ek_ozel", "INTEGER"),
            ]
            for col, col_type in migrations:
                if col not in cols:
                    cursor.execute(f"ALTER TABLE contracts ADD COLUMN {col} {col_type}")
            conn.commit()
        finally:
            conn.close()

    def migrate_trip_plan_table(self):
        conn = self.connect()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trip_plan'")
            if cursor.fetchone() is None:
                return

            cursor.execute("PRAGMA table_info(trip_plan)")
            info = cursor.fetchall()
            col_types = {row[1]: (row[2] or "") for row in info}  # name -> declared type

            needs_migration = False
            for c in ["vehicle_id", "driver_id"]:
                declared = str(col_types.get(c, "")).upper().strip()
                if declared and declared != "TEXT":
                    needs_migration = True
            if not needs_migration:
                return

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS trip_plan_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contract_id INTEGER NOT NULL,
                    route_params_id INTEGER NOT NULL,
                    month TEXT NOT NULL,
                    service_type TEXT NOT NULL,
                    time_block TEXT NOT NULL,
                    vehicle_id TEXT,
                    driver_id TEXT,
                    note TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    UNIQUE (contract_id, route_params_id, month, service_type, time_block)
                )
                """
            )

            cursor.execute(
                """
                INSERT INTO trip_plan_new (
                    id, contract_id, route_params_id, month, service_type, time_block,
                    vehicle_id, driver_id, note, created_at, updated_at
                )
                SELECT
                    id, contract_id, route_params_id, month, service_type, time_block,
                    CAST(vehicle_id AS TEXT), CAST(driver_id AS TEXT), note, created_at, updated_at
                FROM trip_plan
                """
            )

            cursor.execute("DROP TABLE trip_plan")
            cursor.execute("ALTER TABLE trip_plan_new RENAME TO trip_plan")
            conn.commit()
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"Trip plan migration error: {e}")
        finally:
            conn.close()

    def migrate_trip_period_lock_table(self):
        conn = self.connect()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trip_period_lock'")
            if cursor.fetchone() is None:
                return

            cursor.execute("PRAGMA table_info(trip_period_lock)")
            cols = {row[1] for row in cursor.fetchall()}

            migrations = [
                ("locked_by_user_id", "INTEGER"),
                ("unlocked_by_user_id", "INTEGER"),
                ("unlocked_at", "TEXT"),
                ("unlock_reason", "TEXT"),
            ]
            for col, col_type in migrations:
                if col not in cols:
                    cursor.execute(f"ALTER TABLE trip_period_lock ADD COLUMN {col} {col_type}")

            conn.commit()
        finally:
            conn.close()

    def get_next_contract_number(self):
        conn = self.connect()
        if not conn:
            return "SOZ0001"
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT contract_number FROM contracts WHERE contract_number IS NOT NULL ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            if not row or not row[0]:
                return "SOZ0001"
            last_code = str(row[0])
            digits = "".join(ch for ch in last_code if ch.isdigit())
            num = int(digits) if digits else 0
            return f"SOZ{num + 1:04d}"
        except Exception:
            return "SOZ0001"
        finally:
            conn.close()

    def save_contract(self, data, is_update=False):
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            if is_update:
                placeholders = ", ".join([f"{key} = ?" for key in data.keys() if key != "contract_number"])
                values = [v for k, v in data.items() if k != "contract_number"]
                values.append(data["contract_number"])
                query = f"UPDATE contracts SET {placeholders} WHERE contract_number = ?"
                cursor.execute(query, tuple(values))
            else:
                columns = ", ".join(data.keys())
                placeholders = ", ".join(["?" for _ in data.keys()])
                query = f"INSERT INTO contracts ({columns}) VALUES ({placeholders})"
                cursor.execute(query, tuple(list(data.values())))
            conn.commit()
            return True
        except Exception as e:
            print(f"Sözleşme Kayıt Hatası: {e}")
            return False
        finally:
            conn.close()

    def get_contracts_list(self):
        conn = self.connect()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT c.contract_number,
                       COALESCE(c.start_date, ''),
                       COALESCE(c.end_date, ''),
                       COALESCE(c.contract_type, ''),
                       COALESCE(c.is_active, 1),
                       COALESCE(c.customer_id, NULL)
                FROM contracts c
                ORDER BY c.id ASC
                """
            )
            return cursor.fetchall()
        finally:
            conn.close()

    def get_contract_details_by_number(self, number):
        conn = self.connect()
        if not conn:
            return None
        conn.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM contracts WHERE contract_number = ?", (number,))
            return cursor.fetchone()
        finally:
            conn.close()

    def get_active_customers_list(self):
        conn = self.connect()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, COALESCE(title,'') FROM customers WHERE COALESCE(is_active,1)=1 ORDER BY title COLLATE NOCASE"
            )
            return cursor.fetchall()
        finally:
            conn.close()

    def get_active_contracts_by_customer(self, customer_id: int):
        conn = self.connect()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, contract_number, COALESCE(start_date,''), COALESCE(end_date,'')
                FROM contracts
                WHERE customer_id = ? AND COALESCE(is_active,1)=1
                ORDER BY start_date DESC
                """,
                (int(customer_id),),
            )
            return cursor.fetchall()
        finally:
            conn.close()

    def _ensure_route_params_table(self):
        conn = self.connect()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS route_params (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contract_id INTEGER NOT NULL,
                    contract_number TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    service_type TEXT,
                    route_name TEXT,
                    movement_type TEXT,
                    start_point TEXT,
                    stops TEXT,
                    distance_km REAL,
                    created_at TEXT,
                    FOREIGN KEY (contract_id) REFERENCES contracts (id)
                )
                """
            )

            try:
                cursor.execute("PRAGMA table_info(route_params)")
                cols = {row[1] for row in (cursor.fetchall() or [])}
                if "movement_type" not in cols:
                    cursor.execute("ALTER TABLE route_params ADD COLUMN movement_type TEXT")
            except Exception:
                pass
            conn.commit()
        finally:
            conn.close()

    def get_route_params_for_contract(self, contract_id: int, service_type: str):
        self._ensure_route_params_table()
        conn = self.connect()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT id,
                           COALESCE(route_name,''),
                           COALESCE(stops,''),
                           COALESCE(distance_km,0),
                           COALESCE(movement_type,'')
                    FROM route_params
                    WHERE contract_id = ? AND service_type = ?
                    ORDER BY id ASC
                    """,
                    (int(contract_id), (service_type or "").strip()),
                )
                return cursor.fetchall()
            except Exception:
                cursor.execute(
                    """
                    SELECT id,
                           COALESCE(route_name,''),
                           COALESCE(stops,''),
                           COALESCE(distance_km,0)
                    FROM route_params
                    WHERE contract_id = ? AND service_type = ?
                    ORDER BY id ASC
                    """,
                    (int(contract_id), (service_type or "").strip()),
                )
                return cursor.fetchall()
        finally:
            conn.close()

    def get_araclar_list_with_capacity(self, only_active: bool = True):
        conn = self.connect()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            if only_active:
                cursor.execute(
                    """
                    SELECT vehicle_code, plate_number, COALESCE(capacity,0)
                    FROM vehicles
                    WHERE vehicle_code IS NOT NULL
                      AND plate_number IS NOT NULL
                      AND is_active = 1
                    ORDER BY plate_number
                    """
                )
            else:
                cursor.execute(
                    """
                    SELECT vehicle_code, plate_number, COALESCE(capacity,0)
                    FROM vehicles
                    WHERE vehicle_code IS NOT NULL
                      AND plate_number IS NOT NULL
                    ORDER BY plate_number
                    """
                )
            return cursor.fetchall()
        finally:
            conn.close()

    def upsert_trip_entry(
        self,
        contract_id: int,
        route_params_id: int,
        trip_date: str,
        service_type: str,
        time_block: str,
        qty: int,
        time_text: str | None = None,
        note: str | None = None,
        line_no: int = 0,
    ) -> bool:
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                """
                INSERT INTO trip_entries (
                    contract_id, route_params_id, trip_date, service_type, time_block, line_no,
                    qty, time_text, note, created_at, updated_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(contract_id, route_params_id, trip_date, service_type, time_block, line_no)
                DO UPDATE SET
                    qty=excluded.qty,
                    time_text=excluded.time_text,
                    note=excluded.note,
                    updated_at=excluded.updated_at
                """,
                (
                    int(contract_id),
                    int(route_params_id),
                    (trip_date or "").strip(),
                    (service_type or "").strip(),
                    (time_block or "").strip(),
                    int(line_no or 0),
                    int(qty or 0),
                    (time_text or "").strip() if time_text is not None else None,
                    (note or "").strip() if note is not None else None,
                    now,
                    now,
                ),
            )
            conn.commit()
            return True
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            return False
        finally:
            conn.close()

    def delete_contract_by_number(self, number):
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM contracts WHERE contract_number = ?", (number,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Sözleşme Silme Hatası: {e}")
            return False
        finally:
            conn.close()

    def toggle_contract_active_status(self, number):
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT is_active FROM contracts WHERE contract_number = ?", (number,))
            row = cursor.fetchone()
            if not row or row[0] is None:
                return False
            new_status = 0 if int(row[0]) == 1 else 1
            cursor.execute("UPDATE contracts SET is_active = ? WHERE contract_number = ?", (new_status, number))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Sözleşme Aktif/Pasif Hatası: {e}")
            return False
        finally:
            conn.close()
    # --- MÜŞTERİLER (CUSTOMERS) MODÜLÜ METODLARI ---

    def create_customers_table(self):
        conn = self.connect()
        if not conn:
            return
        try:
            # create_tables zaten temel tabloyu oluşturuyor, burada migration yapıyoruz
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(customers)")
            cols = {row[1] for row in cursor.fetchall()}

            migrations = [
                ("musteri_turu", "TEXT"),
                ("kisilik", "TEXT"),
                ("sektor", "TEXT"),
                ("yetkili", "TEXT"),
                ("gorevi", "TEXT"),
                ("il", "TEXT"),
                ("ilce", "TEXT"),
                ("adres1", "TEXT"),
                ("adres2", "TEXT"),
                ("bakiye", "REAL DEFAULT 0"),
                ("iban", "TEXT"),
                ("vergi_dairesi", "TEXT"),
            ]

            for col, col_type in migrations:
                if col not in cols:
                    cursor.execute(f"ALTER TABLE customers ADD COLUMN {col} {col_type}")

            conn.commit()
        finally:
            conn.close()

    def get_next_customer_code(self):
        conn = self.connect()
        if not conn:
            return "MUS0001"
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT customer_code FROM customers WHERE customer_code IS NOT NULL ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            if not row or not row[0]:
                return "MUS0001"
            last_code = str(row[0])
            digits = "".join(ch for ch in last_code if ch.isdigit())
            num = int(digits) if digits else 0
            return f"MUS{num + 1:04d}"
        except Exception:
            return "MUS0001"
        finally:
            conn.close()

    def save_customer(self, data, is_update=False):
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            if is_update:
                placeholders = ", ".join([f"{key} = ?" for key in data.keys() if key != "customer_code"])
                values = [v for k, v in data.items() if k != "customer_code"]
                values.append(data["customer_code"])
                query = f"UPDATE customers SET {placeholders} WHERE customer_code = ?"
                cursor.execute(query, tuple(values))
            else:
                columns = ", ".join(data.keys())
                placeholders = ", ".join(["?" for _ in data.keys()])
                query = f"INSERT INTO customers ({columns}) VALUES ({placeholders})"
                cursor.execute(query, tuple(list(data.values())))

            conn.commit()
            return True
        except Exception as e:
            print(f"Müşteri Kayıt Hatası: {e}")
            return False
        finally:
            conn.close()

    def get_customer_details_by_code(self, code):
        conn = self.connect()
        if not conn:
            return None
        conn.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM customers WHERE customer_code = ?", (code,))
            return cursor.fetchone()
        finally:
            conn.close()

    def delete_customer_by_code(self, code):
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM customers WHERE customer_code = ?", (code,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Müşteri Silme Hatası: {e}")
            return False
        finally:
            conn.close()

    def toggle_customer_active_status(self, code):
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT is_active FROM customers WHERE customer_code = ?", (code,))
            row = cursor.fetchone()
            if not row or row[0] is None:
                return False
            new_status = 0 if int(row[0]) == 1 else 1
            cursor.execute("UPDATE customers SET is_active = ? WHERE customer_code = ?", (new_status, code))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Müşteri Aktif/Pasif Hatası: {e}")
            return False
        finally:
            conn.close()

    def check_customer_tax_number_exists(self, tax_number, current_code=None):
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            if current_code:
                cursor.execute(
                    "SELECT 1 FROM customers WHERE tax_number = ? AND customer_code != ? LIMIT 1",
                    (tax_number, current_code),
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM customers WHERE tax_number = ? LIMIT 1",
                    (tax_number,),
                )
            return cursor.fetchone() is not None
        finally:
            conn.close()

    # --- ARAÇLAR (VEHICLES) MODÜLÜ METODLARI ---

    def create_vehicles_table(self):
        conn = self.connect()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(vehicles)")
            cols = {row[1] for row in cursor.fetchall()}

            migrations = [
                ("vehicle_code", "TEXT"),
                ("arac_sahibi", "TEXT"),
                ("photo_path", "TEXT"),
                ("arac_turu", "TEXT"),
                ("supplier_customer_id", "INTEGER"),
                ("hizmet_turu", "TEXT"),
                ("kategori", "TEXT"),
                ("yil", "INTEGER"),
                ("muayene_tarihi", "TEXT"),
                ("sigorta_tarihi", "TEXT"),
                ("koltuk_tarihi", "TEXT"),
                ("kasko_tarihi", "TEXT"),
                ("calisma_ruhsati_tarihi", "TEXT"),
                ("guzergah_izin_tarihi", "TEXT"),
                ("arac_takip", "INTEGER DEFAULT 0"),
                ("arac_cam", "INTEGER DEFAULT 0"),
            ]

            for col, col_type in migrations:
                if col not in cols:
                    cursor.execute(f"ALTER TABLE vehicles ADD COLUMN {col} {col_type}")

            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_vehicles_vehicle_code ON vehicles(vehicle_code)"
            )

            conn.commit()
        finally:
            conn.close()

    def get_next_vehicle_code(self):
        conn = self.connect()
        if not conn:
            return "ARC0001"
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT vehicle_code FROM vehicles WHERE vehicle_code IS NOT NULL ORDER BY id DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if not row or not row[0]:
                return "ARC0001"
            last_code = str(row[0])
            digits = "".join(ch for ch in last_code if ch.isdigit())
            num = int(digits) if digits else 0
            return f"ARC{num + 1:04d}"
        except Exception:
            return "ARC0001"
        finally:
            conn.close()

    def check_vehicle_plate_exists(self, plate_number, current_code=None):
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            if current_code:
                cursor.execute(
                    "SELECT 1 FROM vehicles WHERE plate_number = ? AND vehicle_code != ? LIMIT 1",
                    (plate_number, current_code),
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM vehicles WHERE plate_number = ? LIMIT 1",
                    (plate_number,),
                )
            return cursor.fetchone() is not None
        finally:
            conn.close()

    def save_vehicle(self, data, is_update=False):
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            if is_update:
                placeholders = ", ".join([f"{key} = ?" for key in data.keys() if key != "vehicle_code"])
                values = [v for k, v in data.items() if k != "vehicle_code"]
                values.append(data["vehicle_code"])
                query = f"UPDATE vehicles SET {placeholders} WHERE vehicle_code = ?"
                cursor.execute(query, tuple(values))
            else:
                columns = ", ".join(data.keys())
                placeholders = ", ".join(["?" for _ in data.keys()])
                query = f"INSERT INTO vehicles ({columns}) VALUES ({placeholders})"
                cursor.execute(query, tuple(list(data.values())))

            conn.commit()
            return True
        except Exception as e:
            print(f"Araç Kayıt Hatası: {e}")
            return False
        finally:
            conn.close()

    def get_vehicle_details_by_code(self, code):
        conn = self.connect()
        if not conn:
            return None
        conn.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vehicles WHERE vehicle_code = ?", (code,))
            return cursor.fetchone()
        finally:
            conn.close()

    def delete_vehicle_by_code(self, code):
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM vehicles WHERE vehicle_code = ?", (code,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Araç Silme Hatası: {e}")
            return False
        finally:
            conn.close()

    def toggle_vehicle_active_status(self, code):
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT is_active FROM vehicles WHERE vehicle_code = ?", (code,))
            row = cursor.fetchone()
            if not row or row[0] is None:
                return False
            new_status = 0 if int(row[0]) == 1 else 1
            cursor.execute("UPDATE vehicles SET is_active = ? WHERE vehicle_code = ?", (new_status, code))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Araç Aktif/Pasif Hatası: {e}")
            return False
        finally:
            conn.close()

    def get_araclar_list(self, only_active=True):
        """Araç listesi: [(vehicle_code, plate_number), ...]"""
        conn = self.connect()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            if only_active:
                cursor.execute(
                    """
                    SELECT vehicle_code, plate_number
                    FROM vehicles
                    WHERE vehicle_code IS NOT NULL
                      AND plate_number IS NOT NULL
                      AND is_active = 1
                    ORDER BY plate_number
                    """
                )
            else:
                cursor.execute(
                    """
                    SELECT vehicle_code, plate_number
                    FROM vehicles
                    WHERE vehicle_code IS NOT NULL
                      AND plate_number IS NOT NULL
                    ORDER BY plate_number
                    """
                )
            return cursor.fetchall()
        finally:
            conn.close()

    # --- ARAÇ BAKIM (REPAIRS) MODÜLÜ METODLARI ---

    def create_repairs_table(self):
        conn = self.connect()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS arac_bakim (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vehicle_code TEXT NOT NULL,
                    bakim_tarihi TEXT,
                    bakim_km INTEGER,
                    bakim_turu TEXT,
                    firma_adi TEXT,
                    yapilan_islemler TEXT,
                    maliyet REAL DEFAULT 0,
                    fis_no TEXT,
                    sonraki_bakim_tarihi TEXT,
                    muhasebe_durum INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY (vehicle_code) REFERENCES vehicles(vehicle_code)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def get_bakim_listesi(self):
        """Tablo görünümü için bakım listesini döndürür.

        Kolonlar: ID, Plaka, Tarih, KM, Maliyet, Firma, Durum
        """
        conn = self.connect()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    ab.id,
                    COALESCE(v.plate_number, ''),
                    COALESCE(ab.bakim_tarihi, ''),
                    COALESCE(ab.bakim_km, 0),
                    COALESCE(ab.maliyet, 0),
                    COALESCE(ab.firma_adi, ''),
                    CASE WHEN COALESCE(ab.muhasebe_durum, 0) = 1 THEN 'Muhasebeleşti' ELSE 'Beklemede' END
                FROM arac_bakim ab
                LEFT JOIN vehicles v ON v.vehicle_code = ab.vehicle_code
                ORDER BY ab.id ASC
                """
            )
            return cursor.fetchall()
        finally:
            conn.close()

    def get_bakim_by_id(self, bakim_id):
        conn = self.connect()
        if not conn:
            return None
        conn.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM arac_bakim WHERE id = ?", (bakim_id,))
            return cursor.fetchone()
        finally:
            conn.close()

    def save_bakim(self, data):
        """Bakım kaydını ekler/günceller.

        Beklenen alanlar:
        - id (opsiyonel)
        - arac_kodu (vehicle_code)
        - bakim_tarihi, bakim_km, bakim_turu, firma_adi, yapilan_islemler,
          maliyet, fis_no, sonraki_bakim_tarihi, muhasebe_durum
        """
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            now = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            bakim_id = data.get("id")
            vehicle_code = data.get("arac_kodu")
            if not vehicle_code:
                return False

            values = (
                vehicle_code,
                data.get("bakim_tarihi"),
                int(data.get("bakim_km") or 0),
                data.get("bakim_turu"),
                data.get("firma_adi"),
                data.get("yapilan_islemler"),
                float(data.get("maliyet") or 0),
                data.get("fis_no"),
                data.get("sonraki_bakim_tarihi"),
                int(data.get("muhasebe_durum") or 0),
            )

            if bakim_id:
                cursor.execute(
                    """
                    UPDATE arac_bakim
                    SET
                        vehicle_code = ?,
                        bakim_tarihi = ?,
                        bakim_km = ?,
                        bakim_turu = ?,
                        firma_adi = ?,
                        yapilan_islemler = ?,
                        maliyet = ?,
                        fis_no = ?,
                        sonraki_bakim_tarihi = ?,
                        muhasebe_durum = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    values + (now, int(bakim_id)),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO arac_bakim (
                        vehicle_code,
                        bakim_tarihi,
                        bakim_km,
                        bakim_turu,
                        firma_adi,
                        yapilan_islemler,
                        maliyet,
                        fis_no,
                        sonraki_bakim_tarihi,
                        muhasebe_durum,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values + (now, now),
                )

            conn.commit()
            return True
        except Exception as e:
            print(f"Bakım Kayıt Hatası: {e}")
            return False
        finally:
            conn.close()

    def delete_bakim(self, bakim_id):
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM arac_bakim WHERE id = ?", (bakim_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Bakım Silme Hatası: {e}")
            return False
        finally:
            conn.close()

    # --- ŞOFÖRLER (DRIVERS) MODÜLÜ METODLARI ---

    def create_driver_documents_table(self):
        conn = self.connect()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS driver_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    personel_kodu TEXT NOT NULL UNIQUE,
                    ehliyet_sinifi TEXT,
                    ehliyet_tarihi TEXT,
                    src_durumu INTEGER DEFAULT 0,
                    src_turu TEXT,
                    src_tarihi TEXT,
                    psikoteknik_durumu INTEGER DEFAULT 0,
                    psikoteknik_tarihi TEXT,
                    sertifika_durumu INTEGER DEFAULT 0,
                    sertifika_metni TEXT,
                    resim_yolu TEXT,
                    updated_at TEXT,
                    FOREIGN KEY (personel_kodu) REFERENCES employees(personel_kodu)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def get_sofor_listesi(self):
        """Personel tablosundan görevi şoför olanları getirir."""
        conn = self.connect()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT personel_kodu, ad_soyad
                FROM employees
                WHERE is_active = 1
                  AND gorevi IS NOT NULL
                  AND (UPPER(gorevi) = 'ŞOFÖR' OR UPPER(gorevi) = 'SOFOR')
                ORDER BY
                    CASE
                        WHEN personel_kodu GLOB 'PER[0-9]*' THEN CAST(SUBSTR(personel_kodu, 4) AS INTEGER)
                        ELSE 999999
                    END,
                    personel_kodu
                """
            )
            return cursor.fetchall()
        finally:
            conn.close()

    def get_personel_details(self, personel_kodu):
        return self.get_employee_details(personel_kodu)

    def get_surucu_belgeleri(self, personel_kodu):
        conn = self.connect()
        if not conn:
            return None
        conn.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM driver_documents WHERE personel_kodu = ?",
                (personel_kodu,),
            )
            return cursor.fetchone()
        finally:
            conn.close()

    def save_surucu_belgeleri(self, data: dict):
        """Upsert şeklinde kaydeder."""
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM driver_documents WHERE personel_kodu = ? LIMIT 1",
                (data.get("personel_kodu"),),
            )
            exists = cursor.fetchone() is not None

            columns = [
                "personel_kodu",
                "ehliyet_sinifi",
                "ehliyet_tarihi",
                "src_durumu",
                "src_turu",
                "src_tarihi",
                "psikoteknik_durumu",
                "psikoteknik_tarihi",
                "sertifika_durumu",
                "sertifika_metni",
                "resim_yolu",
            ]

            payload = {k: data.get(k) for k in columns}

            if exists:
                set_clause = ", ".join([f"{k} = ?" for k in columns if k != "personel_kodu"])
                values = [payload[k] for k in columns if k != "personel_kodu"]
                values.append(payload["personel_kodu"])
                cursor.execute(
                    f"UPDATE driver_documents SET {set_clause} WHERE personel_kodu = ?",
                    tuple(values),
                )
            else:
                col_clause = ", ".join(columns)
                ph = ", ".join(["?"] * len(columns))
                cursor.execute(
                    f"INSERT INTO driver_documents ({col_clause}) VALUES ({ph})",
                    tuple(payload[k] for k in columns),
                )

            conn.commit()
            return True
        except Exception as e:
            print(f"Sürücü Belge Kayıt Hatası: {e}")
            return False
        finally:
            conn.close()

    def delete_surucu_belgeleri(self, personel_kodu):
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM driver_documents WHERE personel_kodu = ?",
                (personel_kodu,),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # --- PERSONEL (EMPLOYEES) MODÜLÜ METODLARI ---

    def create_employees_table(self):
        """Senin formundaki tüm alanları içeren tabloyu oluşturur"""
        query = """
        CREATE TABLE IF NOT EXISTS employees (
            personel_kodu TEXT PRIMARY KEY,
            personel_turu TEXT, tckn TEXT, ad_soyad TEXT,
            anne_adi TEXT, baba_adi TEXT, dogum_yeri TEXT, dogum_tarihi TEXT,
            gsm TEXT, email TEXT, gorevi TEXT, kan_grubu TEXT,
            il TEXT, ilce TEXT, adres1 TEXT, adres2 TEXT,
            banka_adi TEXT, iban TEXT, notlar1 TEXT, notlar2 TEXT,
            photo_path TEXT,
            is_active INTEGER DEFAULT 1
        )
        """
        conn = self.connect()
        if conn:
            try:
                conn.execute(query)
                conn.commit()

                # Backward-compatible migration: eski DB'lerde photo_path kolonu olmayabilir
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(employees)")
                cols = {row[1] for row in cursor.fetchall()}
                if "photo_path" not in cols:
                    cursor.execute("ALTER TABLE employees ADD COLUMN photo_path TEXT")
                    conn.commit()
            finally:
                conn.close()

    def save_employee(self, data, is_update=False):
        """Personel kaydeder veya günceller (Sözlük yapısıyla çalışır)"""
        conn = self.connect()
        if not conn: return False
        
        try:
            cursor = conn.cursor()
            if is_update:
                # Dinamik UPDATE sorgusu
                placeholders = ", ".join([f"{key} = ?" for key in data.keys() if key != "personel_kodu"])
                values = [v for k, v in data.items() if k != "personel_kodu"]
                values.append(data["personel_kodu"])
                query = f"UPDATE employees SET {placeholders} WHERE personel_kodu = ?"
                cursor.execute(query, tuple(values))
            else:
                # INSERT sorgusu
                columns = ", ".join(data.keys())
                placeholders = ", ".join(["?" for _ in data.keys()])
                query = f"INSERT INTO employees ({columns}) VALUES ({placeholders})"
                cursor.execute(query, tuple(list(data.values())))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Personel Kayıt Hatası: {e}")
            return False
        finally:
            conn.close()

    def get_all_employees(self):
        """Tüm personel listesini getirir"""
        conn = self.connect()
        if not conn: return []
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM employees WHERE is_active = 1")
        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_employee_details(self, kodu):
        """Formu doldurmak için tüm detayları getirir"""
        conn = self.connect()
        if not conn: return None
        conn.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM employees WHERE personel_kodu = ?", (kodu,))
            return cursor.fetchone()
        finally:
            conn.close()
    
    def check_tckn_exists(self, tckn, current_kod=None):
        """TCKN'nin veritabanında olup olmadığını kontrol eder."""
        conn = self.connect()
        cursor = conn.cursor()
        # Eğer güncelleme yapılıyorsak (current_kod varsa), personelin kendi kodunu sorgu dışı bırak
        if current_kod:
            query = "SELECT 1 FROM employees WHERE tckn = ? AND personel_kodu != ?"
            cursor.execute(query, (tckn, current_kod))
        else:
            query = "SELECT 1 FROM employees WHERE tckn = ?"
            cursor.execute(query, (tckn,))
        
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def check_iban_exists(self, iban, current_kod=None):
        """IBAN'ın veritabanında olup olmadığını kontrol eder."""
        conn = self.connect()
        cursor = conn.cursor()
        if current_kod:
            query = "SELECT 1 FROM employees WHERE iban = ? AND personel_kodu != ?"
            cursor.execute(query, (iban, current_kod))
        else:
            query = "SELECT 1 FROM employees WHERE iban = ?"
            cursor.execute(query, (iban,))
        
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def delete_employee(self, kodu):
        """Personeli koduna göre siler"""
        conn = self.connect()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM employees WHERE personel_kodu = ?", (kodu,))
            conn.commit()
            return True
        except Exception as e:
            print(f"Silme hatası: {e}")
            return False
        finally:
            conn.close()

    def get_employee_active_status(self, kodu):
        conn = self.connect()
        if not conn:
            return None
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT is_active FROM employees WHERE personel_kodu = ?", (kodu,))
            row = cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else None
        finally:
            conn.close()

    def set_employee_active_status(self, kodu, is_active: int):
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE employees SET is_active = ? WHERE personel_kodu = ?",
                (1 if int(is_active) else 0, kodu),
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Aktif/Pasif güncelleme hatası: {e}")
            return False
        finally:
            conn.close()

    def toggle_employee_active_status(self, kodu):
        conn = self.connect()
        if not conn:
            return False
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT is_active FROM employees WHERE personel_kodu = ?", (kodu,))
            row = cursor.fetchone()
            if row and row[0] is not None:
                new_status = 1 if row[0] == 0 else 0
                cursor.execute("UPDATE employees SET is_active = ? WHERE personel_kodu = ?", (new_status, kodu))
                conn.commit()
                return cursor.rowcount > 0
            else:
                return False
        except Exception as e:
            print(f"Aktif/Pasif güncelleme hatası: {e}")
            return False
        finally:
            conn.close()

    def get_last_value(self, table, column):
        """Herhangi bir tablodaki son değeri getirir"""
        query = f"SELECT {column} FROM {table} ORDER BY rowid DESC LIMIT 1"
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(query)
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def get_personel_by_kod(self, p_kodu):
        """Veritabanından tek bir personelin tüm bilgilerini getirir"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM employees WHERE personel_kodu = ?", (p_kodu,))
        row = cursor.fetchone()
        conn.close()
        return row
    
    def create_constants_table(self):
        """Sabitleri tutacak hiyerarşik tabloyu oluşturur."""
        query = """
        CREATE TABLE IF NOT EXISTS constants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT NOT NULL,  -- 'banka', 'il', 'gorev' vb.
            value TEXT NOT NULL,       -- 'Ziraat', 'Sakarya', 'Şoför' vb.
            parent_id INTEGER,         -- İlçe ise ilin id'sini tutar
            FOREIGN KEY (parent_id) REFERENCES constants (id)
        )
        """
        conn = self.connect()
        conn.execute(query)
        conn.commit()
        conn.close()

    def get_constants(self, group_name, parent_id=None):
        """Belirli bir gruptaki sabitleri getirir."""
        conn = self.connect()
        cursor = conn.cursor()
        if parent_id is not None:
            cursor.execute("SELECT id, value FROM constants WHERE group_name = ? AND parent_id = ?", (group_name, parent_id))
        else:
            cursor.execute("SELECT id, value FROM constants WHERE group_name = ? AND parent_id IS NULL", (group_name,))
        data = cursor.fetchall()
        conn.close()
        return data

    def update_or_insert_constant(self, group_name, value, constant_id=None, parent_id=None):
        """Sabit ekler veya günceller."""
        conn = self.connect()
        cursor = conn.cursor()
        if constant_id:
            cursor.execute("UPDATE constants SET value = ? WHERE id = ?", (value, constant_id))
        else:
            cursor.execute("INSERT INTO constants (group_name, value, parent_id) VALUES (?, ?, ?)", (group_name, value, parent_id))
            constant_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return constant_id

    def delete_constant(self, constant_id):
        """Sabiti siler."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM constants WHERE id = ? OR parent_id = ?", (constant_id, constant_id))
        conn.commit()
        conn.close()
