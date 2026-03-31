import sqlite3
import os
import json
import threading
from datetime import datetime, timedelta
from time import sleep
from typing import Optional
from config import DB_PATH, BASE_DIR


# Türk alfabesi sırası: a b c ç d e f g ğ h ı i j k l m n o ö p r s ş t u ü v y z
# Türk alfabesinde olmayan q, w, x gibi harfleri en sona atıyoruz.
_TR_ALPHABET = " 0123456789abcçdefgğhıijklmnoöprsştuüvyzqwx"
_TR_ORDER = {ch: i for i, ch in enumerate(_TR_ALPHABET)}


def _tr_lower(s: str) -> str:
    s = str(s or "")
    return s.replace("I", "ı").replace("İ", "i").lower()


def _tr_key(s: str):
    s2 = _tr_lower(s)
    return tuple(_TR_ORDER.get(ch, 1000 + ord(ch)) for ch in s2)


def _tr_collate(a: str, b: str) -> int:
    ka = _tr_key(a)
    kb = _tr_key(b)
    if ka < kb:
        return -1
    if ka > kb:
        return 1
    return 0

class DatabaseManager:
    _bootstrapped = False
    _write_lock = threading.RLock()

    def __init__(self):
        self.db_path = DB_PATH
        if bool(DatabaseManager._bootstrapped):
            return

        DatabaseManager._bootstrapped = True

        self.create_tables()
        self.migrate_contracts_table()
        self.migrate_trip_plan_table()
        self.migrate_trip_period_lock_table()
        self.create_trip_entries_tables()
        self._ensure_trip_prices_table()
        self._ensure_bulk_puantaj_manual_rows_table()
        self.create_hakedis_tables()
        self.create_customers_table()
        self.create_vehicles_table()
        self.create_contract_links_table()
        self.create_repairs_table()
        self.create_employees_table()
        self.create_driver_documents_table()
        self.create_constants_table()
    
    def connect(self, timeout: float = 5, busy_timeout_ms: int = 5000):
        try:
            # check_same_thread=False ekliyoruz ki farklı modüllerden erişirken sorun çıkmasın
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=float(timeout or 0))
            try:
                conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms or 0)}")
            except Exception:
                pass
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except Exception:
                pass
            try:
                conn.execute("PRAGMA synchronous=NORMAL")
            except Exception:
                pass
            try:
                conn.create_collation("TRNOCASE", _tr_collate)
            except Exception:
                pass
            return conn
        except Exception as e:
            print(f"Database connection error: {e}")
            return None

    def _ensure_bulk_puantaj_manual_rows_table(self):
        conn = self.connect()
        if not conn:
            return
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS bulk_puantaj_manual_rows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contract_id INTEGER NOT NULL,
                    month TEXT NOT NULL,
                    service_type TEXT NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    guzergah TEXT,
                    vehicle_id TEXT,
                    driver_id TEXT,
                    movement_type TEXT,
                    time_text TEXT,
                    unit_price REAL DEFAULT 0,
                    day_qty_json TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_bulk_puantaj_manual_rows_ctx
                ON bulk_puantaj_manual_rows(contract_id, month, service_type)
                """
            )
            conn.commit()
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def get_bulk_puantaj_manual_rows(self, contract_id: int, month: str, service_type: str):
        self._ensure_bulk_puantaj_manual_rows_table()
        conn = self.connect()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT sort_order, guzergah, vehicle_id, driver_id, movement_type, time_text, unit_price, day_qty_json
                FROM bulk_puantaj_manual_rows
                WHERE contract_id=? AND month=? AND service_type=?
                ORDER BY sort_order ASC, id ASC
                """,
                (int(contract_id), str(month), str(service_type)),
            )
            return cur.fetchall() or []
        finally:
            conn.close()

    def _clone_table_schema(self, src_conn: sqlite3.Connection, dst_conn: sqlite3.Connection, table: str) -> bool:
        try:
            s_cur = src_conn.cursor()
            s_cur.execute(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type='table' AND name=?
                """,
                (str(table),),
            )
            row = s_cur.fetchone()
            sql = (row or [None])[0]
            if not sql:
                return False

            d_cur = dst_conn.cursor()
            d_cur.execute(str(sql))
            return True
        except Exception:
            return False

    def create_full_backup(self, target_path: str) -> dict:
        src = self.connect()
        if not src:
            return {"ok": False, "path": "", "error": "DB bağlantısı kurulamadı."}
        try:
            os.makedirs(os.path.dirname(str(target_path)), exist_ok=True)
        except Exception:
            pass

        try:
            dst = sqlite3.connect(str(target_path))
        except Exception as e:
            try:
                src.close()
            except Exception:
                pass
            return {"ok": False, "path": str(target_path), "error": str(e)}

        try:
            try:
                src.backup(dst)
            except Exception:
                src.backup(dst, pages=0)
            try:
                dst.commit()
            except Exception:
                pass
            return {"ok": True, "path": str(target_path), "error": ""}
        except Exception as e:
            return {"ok": False, "path": str(target_path), "error": str(e)}
        finally:
            try:
                dst.close()
            except Exception:
                pass
            try:
                src.close()
            except Exception:
                pass

    def create_monthly_backup(self, month: str, target_dir: str = "") -> dict:
        m = str(month or "").strip()[:7]
        if len(m) != 7 or m[4] != "-":
            return {"ok": False, "path": "", "error": "Geçersiz dönem (YYYY-MM)."}

        if not target_dir:
            try:
                target_dir = os.path.join(str(BASE_DIR), "database", "backups", "monthly")
            except Exception:
                target_dir = ""

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"ops_{m}_{ts}.db"
        out_path = os.path.join(str(target_dir), fname) if target_dir else fname

        src = self.connect()
        if not src:
            return {"ok": False, "path": str(out_path), "error": "DB bağlantısı kurulamadı."}
        try:
            try:
                os.makedirs(os.path.dirname(str(out_path)), exist_ok=True)
            except Exception:
                pass

            dst = sqlite3.connect(str(out_path))
        except Exception as e:
            try:
                src.close()
            except Exception:
                pass
            return {"ok": False, "path": str(out_path), "error": str(e)}

        try:
            try:
                self.create_trip_entries_tables()
            except Exception:
                pass
            try:
                self.migrate_trip_plan_table()
            except Exception:
                pass
            try:
                self.migrate_trip_period_lock_table()
            except Exception:
                pass
            try:
                self._ensure_trip_prices_table()
            except Exception:
                pass
            try:
                self._ensure_bulk_puantaj_manual_rows_table()
            except Exception:
                pass
            try:
                self.create_hakedis_tables()
            except Exception:
                pass

            try:
                dcur = dst.cursor()
                dcur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS backup_meta (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        month TEXT,
                        created_at TEXT,
                        source_db_path TEXT
                    )
                    """
                )
                dcur.execute(
                    "INSERT INTO backup_meta(month, created_at, source_db_path) VALUES (?, datetime('now'), ?) ",
                    (str(m), str(self.db_path)),
                )
            except Exception:
                pass

            tables = [
                "trip_entries",
                "trip_allocations",
                "trip_plan",
                "trip_period_lock",
                "period_close",
                "bulk_puantaj_manual_rows",
                "trip_prices",
                "hakedis",
                "hakedis_items",
                "hakedis_deductions",
                "hakedis_docs",
            ]

            existing = set()
            try:
                s_cur = src.cursor()
                s_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                existing = {str(r[0]) for r in (s_cur.fetchall() or []) if r and r[0]}
            except Exception:
                existing = set()

            for t in tables:
                if t not in existing:
                    continue
                self._clone_table_schema(src, dst, str(t))

            s_cur = src.cursor()
            d_cur = dst.cursor()

            start_date = f"{m}-01"
            end_date = f"{m}-31"

            if "trip_entries" in existing:
                s_cur.execute(
                    """
                    SELECT * FROM trip_entries
                    WHERE trip_date BETWEEN ? AND ?
                    """,
                    (str(start_date), str(end_date)),
                )
                rows = s_cur.fetchall() or []
                if rows:
                    cols = [d[0] for d in (s_cur.description or [])]
                    d_cur.executemany(
                        f"INSERT INTO trip_entries({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
                        rows,
                    )

            if "trip_allocations" in existing:
                s_cur.execute(
                    """
                    SELECT * FROM trip_allocations
                    WHERE trip_date BETWEEN ? AND ?
                    """,
                    (str(start_date), str(end_date)),
                )
                rows = s_cur.fetchall() or []
                if rows:
                    cols = [d[0] for d in (s_cur.description or [])]
                    d_cur.executemany(
                        f"INSERT INTO trip_allocations({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
                        rows,
                    )

            if "trip_plan" in existing:
                s_cur.execute("SELECT * FROM trip_plan WHERE month = ?", (str(m),))
                rows = s_cur.fetchall() or []
                if rows:
                    cols = [d[0] for d in (s_cur.description or [])]
                    d_cur.executemany(
                        f"INSERT INTO trip_plan({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
                        rows,
                    )

            if "trip_period_lock" in existing:
                s_cur.execute("SELECT * FROM trip_period_lock WHERE month = ?", (str(m),))
                rows = s_cur.fetchall() or []
                if rows:
                    cols = [d[0] for d in (s_cur.description or [])]
                    d_cur.executemany(
                        f"INSERT INTO trip_period_lock({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
                        rows,
                    )

            if "period_close" in existing:
                s_cur.execute("SELECT * FROM period_close WHERE month = ?", (str(m),))
                rows = s_cur.fetchall() or []
                if rows:
                    cols = [d[0] for d in (s_cur.description or [])]
                    d_cur.executemany(
                        f"INSERT INTO period_close({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
                        rows,
                    )

            if "bulk_puantaj_manual_rows" in existing:
                s_cur.execute("SELECT * FROM bulk_puantaj_manual_rows WHERE month = ?", (str(m),))
                rows = s_cur.fetchall() or []
                if rows:
                    cols = [d[0] for d in (s_cur.description or [])]
                    d_cur.executemany(
                        f"INSERT INTO bulk_puantaj_manual_rows({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
                        rows,
                    )

            if "trip_prices" in existing:
                s_cur.execute(
                    """
                    SELECT * FROM trip_prices
                    WHERE effective_from <= ?
                    """,
                    (str(end_date),),
                )
                rows = s_cur.fetchall() or []
                if rows:
                    cols = [d[0] for d in (s_cur.description or [])]
                    d_cur.executemany(
                        f"INSERT INTO trip_prices({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
                        rows,
                    )

            hakedis_ids: list[int] = []
            if "hakedis" in existing:
                s_cur.execute("SELECT * FROM hakedis WHERE period = ?", (str(m),))
                rows = s_cur.fetchall() or []
                if rows:
                    cols = [d[0] for d in (s_cur.description or [])]
                    try:
                        id_idx = cols.index("id")
                    except Exception:
                        id_idx = -1
                    if id_idx >= 0:
                        for r in rows:
                            try:
                                hakedis_ids.append(int(r[id_idx] or 0))
                            except Exception:
                                pass
                    d_cur.executemany(
                        f"INSERT INTO hakedis({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
                        rows,
                    )

            if hakedis_ids:
                placeholders = ",".join(["?"] * len(hakedis_ids))
                for child in ("hakedis_items", "hakedis_deductions", "hakedis_docs"):
                    if child not in existing:
                        continue
                    s_cur.execute(f"SELECT * FROM {child} WHERE hakedis_id IN ({placeholders})", tuple(hakedis_ids))
                    rows = s_cur.fetchall() or []
                    if not rows:
                        continue
                    cols = [d[0] for d in (s_cur.description or [])]
                    d_cur.executemany(
                        f"INSERT INTO {child}({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
                        rows,
                    )

            dst.commit()
            return {"ok": True, "path": str(out_path), "error": ""}
        except Exception as e:
            try:
                dst.rollback()
            except Exception:
                pass
            return {"ok": False, "path": str(out_path), "error": str(e)}
        finally:
            try:
                dst.close()
            except Exception:
                pass
            try:
                src.close()
            except Exception:
                pass

    def reset_operational_data(self) -> bool:
        """Hard-delete all operational data while preserving master records.

        Preserves: users/customers/vehicles/employees/drivers/constants/repairs etc.
        Deletes: contracts and all dependent operational tables (routes, trips, puantaj, hakedis...).
        """
        conn = self.connect()
        if not conn:
            return False
        try:
            cur = conn.cursor()

            try:
                conn.execute("PRAGMA busy_timeout = 15000")
            except Exception:
                pass

            try:
                conn.execute("PRAGMA foreign_keys = OFF")
            except Exception:
                pass

            try:
                self.create_trip_entries_tables()
            except Exception:
                pass
            try:
                self.migrate_trip_plan_table()
            except Exception:
                pass
            try:
                self.migrate_trip_period_lock_table()
            except Exception:
                pass
            try:
                self._ensure_trip_prices_table()
            except Exception:
                pass
            try:
                self.create_hakedis_tables()
            except Exception:
                pass
            try:
                self._ensure_bulk_puantaj_manual_rows_table()
            except Exception:
                pass
            try:
                self._ensure_contract_special_items_table()
            except Exception:
                pass

            existing_tables = set()
            try:
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                existing_tables = {str(r[0]) for r in (cur.fetchall() or []) if r and r[0]}
            except Exception:
                existing_tables = set()

            cur.execute("BEGIN")

            errors = []

            # Hakediş alt tabloları
            for tbl in (
                "hakedis_docs",
                "hakedis_deductions",
                "hakedis_items",
                "hakedis",
            ):
                try:
                    if tbl in existing_tables:
                        cur.execute(f"DELETE FROM {tbl}")
                except Exception as e:
                    errors.append((tbl, str(e)))
                    try:
                        print(f"reset_operational_data: DELETE {tbl} failed: {e}")
                    except Exception:
                        pass

            # Puantaj / sefer plan
            for tbl in (
                "bulk_puantaj_manual_rows",
                "trip_allocations",
                "trip_entries",
                "trip_plan",
                "trip_time_blocks",
                "trip_period_lock",
                "period_close",
                "trips",
            ):
                try:
                    if tbl in existing_tables:
                        cur.execute(f"DELETE FROM {tbl}")
                except Exception as e:
                    errors.append((tbl, str(e)))
                    try:
                        print(f"reset_operational_data: DELETE {tbl} failed: {e}")
                    except Exception:
                        pass

            # Rota + sözleşme tarifeleri
            for tbl in (
                "trip_prices",
                "contract_special_items",
                "route_params",
            ):
                try:
                    if tbl in existing_tables:
                        cur.execute(f"DELETE FROM {tbl}")
                except Exception as e:
                    errors.append((tbl, str(e)))
                    try:
                        print(f"reset_operational_data: DELETE {tbl} failed: {e}")
                    except Exception:
                        pass

            # Sözleşmeler
            try:
                if "contracts" in existing_tables:
                    cur.execute("DELETE FROM contracts")
            except Exception as e:
                errors.append(("contracts", str(e)))
                try:
                    print(f"reset_operational_data: DELETE contracts failed: {e}")
                except Exception:
                    pass

            if errors:
                try:
                    conn.rollback()
                except Exception:
                    pass
                try:
                    print(f"reset_operational_data failed on db: {self.db_path}")
                    print(f"reset_operational_data errors: {errors}")
                except Exception:
                    pass
                return False

            conn.commit()

            try:
                print(f"reset_operational_data OK on db: {self.db_path}")
                for t in ("trip_allocations", "trip_entries", "trip_plan", "trip_prices"):
                    if t not in existing_tables:
                        continue
                    try:
                        cur.execute(f"SELECT COUNT(1) FROM {t}")
                        cnt = int((cur.fetchone() or [0])[0] or 0)
                        print(f"reset_operational_data verify: {t}={cnt}")
                    except Exception as _e:
                        print(f"reset_operational_data verify: {t} ERR: {_e}")
            except Exception:
                pass
            return True
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                print(f"reset_operational_data error: {e}")
            except Exception:
                pass
            return False
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def delete_trip_puantaj_for_context(self, contract_id: int, service_type: str, month: str) -> int:
        """Delete trip_entries + trip_allocations for (contract_id, service_type, month).

        Returns total deleted row count.
        """
        try:
            cid = int(contract_id or 0)
        except Exception:
            return 0
        st = str(service_type or "").strip()
        m = str(month or "").strip()[:7]
        if cid <= 0 or (not st) or len(m) != 7:
            return 0

        start_date = f"{m}-01"
        end_date = f"{m}-31"

        try:
            self.create_trip_entries_tables()
        except Exception:
            pass

        conn = self.connect()
        if not conn:
            return 0
        deleted = 0
        try:
            cur = conn.cursor()
            cur.execute("BEGIN")
            cur.execute(
                """
                DELETE FROM trip_allocations
                WHERE contract_id = ?
                  AND service_type = ?
                  AND trip_date BETWEEN ? AND ?
                """,
                (int(cid), str(st), str(start_date), str(end_date)),
            )
            deleted += int(cur.rowcount or 0)
            cur.execute(
                """
                DELETE FROM trip_entries
                WHERE contract_id = ?
                  AND service_type = ?
                  AND trip_date BETWEEN ? AND ?
                """,
                (int(cid), str(st), str(start_date), str(end_date)),
            )
            deleted += int(cur.rowcount or 0)
            conn.commit()
            return int(deleted)
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                print(f"delete_trip_puantaj_for_context error: {e}")
            except Exception:
                pass
            return 0
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def replace_bulk_puantaj_manual_rows(
        self,
        contract_id: int,
        month: str,
        service_type: str,
        rows: list[dict],
    ) -> bool:
        self._ensure_bulk_puantaj_manual_rows_table()
        last_err = None
        for attempt in range(6):
            conn = self.connect()
            if not conn:
                last_err = RuntimeError("Veritabanı bağlantısı kurulamadı")
                break
            try:
                cur = conn.cursor()
                try:
                    cur.execute("BEGIN IMMEDIATE")
                except Exception:
                    pass

                cur.execute(
                    "DELETE FROM bulk_puantaj_manual_rows WHERE contract_id=? AND month=? AND service_type=?",
                    (int(contract_id), str(month), str(service_type)),
                )
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for i, rec in enumerate(rows or []):
                    if not isinstance(rec, dict):
                        continue
                    cur.execute(
                        """
                        INSERT INTO bulk_puantaj_manual_rows (
                            contract_id, month, service_type, sort_order,
                            guzergah, vehicle_id, driver_id, movement_type, time_text,
                            unit_price, day_qty_json, created_at, updated_at
                        )
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            int(contract_id),
                            str(month),
                            str(service_type),
                            int(rec.get("sort_order") if rec.get("sort_order") is not None else i),
                            str(rec.get("guzergah") or ""),
                            (None if rec.get("vehicle_id") is None else str(rec.get("vehicle_id"))),
                            (None if rec.get("driver_id") is None else str(rec.get("driver_id"))),
                            str(rec.get("movement_type") or ""),
                            str(rec.get("time_text") or ""),
                            float(rec.get("unit_price") or 0.0),
                            str(rec.get("day_qty_json") or ""),
                            now,
                            now,
                        ),
                    )
                conn.commit()
                conn.close()
                last_err = None
                break
            except Exception as e:
                last_err = e
                msg = ""
                try:
                    msg = str(e or "")
                except Exception:
                    msg = ""
                try:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    try:
                        conn.close()
                    except Exception:
                        pass
                except Exception:
                    pass
                if "locked" in msg.lower() and attempt < 5:
                    try:
                        sleep(0.15 * float(attempt + 1))
                    except Exception:
                        pass
                    continue
                break

        return bool(last_err is None)

    def create_tables(self):
        last_err = None
        for attempt in range(6):
            conn = self.connect()
            if not conn:
                last_err = RuntimeError("Veritabanı bağlantısı kurulamadı")
                break
            try:
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

                cursor.execute(
                    """CREATE TABLE IF NOT EXISTS period_close (
                    month TEXT PRIMARY KEY,
                    closed INTEGER NOT NULL DEFAULT 0,
                    closed_at TEXT,
                    closed_by_user_id INTEGER,
                    note TEXT
                )"""
                )
                cursor.execute("SELECT COUNT(*) FROM users")
                if cursor.fetchone()[0] == 0:
                    cursor.execute("""
                        INSERT INTO users (username, password, full_name, role, is_active)
                        VALUES ('admin', '1234', 'SATTUP Admin', 'admin', 1)
                    """)
                    print("Bilgi: İlk admin kullanıcısı (admin/1234) oluşturuldu.")

                conn.commit()
                conn.close()
                last_err = None
                break
            except Exception as e:
                last_err = e
                msg = ""
                try:
                    msg = str(e or "")
                except Exception:
                    msg = ""
                try:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    try:
                        conn.close()
                    except Exception:
                        pass
                except Exception:
                    pass
                if "locked" in msg.lower() and attempt < 5:
                    try:
                        sleep(0.2 * float(attempt + 1))
                    except Exception:
                        pass
                    continue
                break

        if last_err is not None:
            raise last_err

    def get_period_close(self, month: str):
        conn = self.connect()
        if not conn:
            return None
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT closed, closed_at, closed_by_user_id, note
                FROM period_close
                WHERE month = ?
                """,
                (str(month),),
            )
            row = cur.fetchone()
            if not row:
                return {
                    "month": str(month),
                    "closed": 0,
                    "closed_at": None,
                    "closed_by_user_id": None,
                    "note": None,
                }
            return {
                "month": str(month),
                "closed": int(row[0] or 0),
                "closed_at": row[1],
                "closed_by_user_id": row[2],
                "note": row[3],
            }
        finally:
            conn.close()

    def list_trip_tariff_effective_from_dates(self, contract_id: int, service_type: str) -> list[str]:
        """Return distinct effective_from dates (YYYY-MM-DD) for tariff rows."""
        self._ensure_trip_prices_table()
        conn = self.connect()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT DISTINCT effective_from
                FROM trip_prices
                WHERE contract_id=?
                  AND service_type=?
                  AND COALESCE(pricing_category,'') <> ''
                  AND COALESCE(effective_from,'') <> ''
                ORDER BY effective_from DESC
                """,
                (int(contract_id), str(service_type)),
            )
            return [str(r[0]) for r in (cur.fetchall() or []) if r and r[0]]
        finally:
            conn.close()

    def upsert_trip_tariff_price(
        self,
        contract_id: int,
        service_type: str,
        route_params_id: int,
        pricing_category: str,
        effective_from: str,
        price: float,
        subcontractor_price: float = 0.0,
    ) -> bool:
        """Upsert a tariff price row (pricing_category+effective_from based).

        Notes:
        - We store these in trip_prices for now, but use a special time_block that won't match
          operational allocations, to avoid interfering with attendance/hakediş legacy lookups.
        - get_trip_price_for_date() does NOT depend on month/time_block.
        """
        self._ensure_trip_prices_table()
        conn = self.connect()
        if not conn:
            return False
        try:
            cur = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            eff = str(effective_from or "").strip()
            if not eff:
                return False
            pc = str(pricing_category or "").strip().upper()
            if not pc:
                return False
            month = eff[:7] if len(eff) >= 7 else ""
            tb = f"TARIFE|{pc}|{eff}"
            cur.execute(
                """
                INSERT INTO trip_prices(
                    contract_id, route_params_id, month, service_type, time_block,
                    pricing_category, effective_from, price, subcontractor_price, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(contract_id, route_params_id, month, service_type, time_block)
                DO UPDATE SET
                    pricing_category=excluded.pricing_category,
                    effective_from=excluded.effective_from,
                    price=excluded.price,
                    subcontractor_price=excluded.subcontractor_price,
                    updated_at=excluded.updated_at
                """,
                (
                    int(contract_id),
                    int(route_params_id),
                    str(month),
                    str(service_type),
                    str(tb),
                    str(pc),
                    str(eff),
                    float(price or 0.0),
                    float(subcontractor_price or 0.0),
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

    def list_trip_tariff_prices_for_effective_from(
        self,
        contract_id: int,
        service_type: str,
        effective_from: str,
    ):
        """Return rows: (route_params_id, pricing_category, price, subcontractor_price)."""
        self._ensure_trip_prices_table()
        conn = self.connect()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            eff = str(effective_from or "").strip()
            cur.execute(
                """
                SELECT route_params_id, UPPER(COALESCE(pricing_category,'')), COALESCE(price,0), COALESCE(subcontractor_price,0)
                FROM trip_prices
                WHERE contract_id=?
                  AND service_type=?
                  AND COALESCE(effective_from,'') = ?
                  AND COALESCE(pricing_category,'') <> ''
                """,
                (int(contract_id), str(service_type), str(eff)),
            )
            return cur.fetchall() or []
        finally:
            conn.close()

    def delete_trip_tariff_prices_for_effective_from(
        self,
        contract_id: int,
        service_type: str,
        effective_from: str,
    ) -> bool:
        self._ensure_trip_prices_table()
        conn = self.connect()
        if not conn:
            return False
        try:
            cur = conn.cursor()
            eff = str(effective_from or "").strip()
            cur.execute(
                """
                DELETE FROM trip_prices
                WHERE contract_id=?
                  AND service_type=?
                  AND COALESCE(effective_from,'') = ?
                  AND COALESCE(pricing_category,'') <> ''
                """,
                (int(contract_id), str(service_type), str(eff)),
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

    def delete_contract_special_items_for_context(self, contract_id: int, period: str, service_type: str) -> bool:
        self._ensure_contract_special_items_table()
        conn = self.connect()
        if not conn:
            return False
        try:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM contract_special_items WHERE contract_id=? AND period=? AND service_type=?",
                (int(contract_id), str(period), str(service_type)),
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

    def _ensure_contract_special_items_table(self):
        conn = self.connect()
        if not conn:
            return
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS contract_special_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contract_id INTEGER NOT NULL,
                    period TEXT NOT NULL,
                    service_type TEXT NOT NULL,
                    title TEXT,
                    date_from TEXT,
                    date_to TEXT,
                    time_text TEXT,
                    distance_km REAL NOT NULL DEFAULT 0,
                    qty_days REAL NOT NULL DEFAULT 0,
                    unit_price REAL NOT NULL DEFAULT 0,
                    total_amount REAL NOT NULL DEFAULT 0,
                    note TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_csi_key ON contract_special_items(contract_id, period, service_type)"
            )
            conn.commit()
        finally:
            conn.close()

    def list_contract_special_items(self, contract_id: int, period: str, service_type: str):
        self._ensure_contract_special_items_table()
        conn = self.connect()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, COALESCE(title,''), COALESCE(date_from,''), COALESCE(date_to,''),
                       COALESCE(time_text,''), COALESCE(distance_km,0), COALESCE(qty_days,0),
                       COALESCE(unit_price,0), COALESCE(total_amount,0), COALESCE(note,'')
                FROM contract_special_items
                WHERE contract_id=? AND period=? AND service_type=?
                ORDER BY id ASC
                """,
                (int(contract_id), str(period), str(service_type)),
            )
            return cur.fetchall() or []
        finally:
            conn.close()

    def upsert_contract_special_item(
        self,
        contract_id: int,
        period: str,
        service_type: str,
        title: str,
        qty_days: float = 0.0,
        unit_price: float = 0.0,
        total_amount: float = 0.0,
        date_from: str | None = None,
        date_to: str | None = None,
        time_text: str | None = None,
        distance_km: float = 0.0,
        note: str | None = None,
        item_id: int | None = None,
    ) -> int | None:
        self._ensure_contract_special_items_table()
        conn = self.connect()
        if not conn:
            return None
        try:
            cur = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if item_id is not None:
                cur.execute(
                    """
                    UPDATE contract_special_items
                    SET title=?, date_from=?, date_to=?, time_text=?, distance_km=?,
                        qty_days=?, unit_price=?, total_amount=?, note=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        str(title or ""),
                        str(date_from or ""),
                        str(date_to or ""),
                        str(time_text or ""),
                        float(distance_km or 0.0),
                        float(qty_days or 0.0),
                        float(unit_price or 0.0),
                        float(total_amount or 0.0),
                        str(note or ""),
                        now,
                        int(item_id),
                    ),
                )
                conn.commit()
                return int(item_id)

            cur.execute(
                """
                INSERT INTO contract_special_items(
                    contract_id, period, service_type, title,
                    date_from, date_to, time_text, distance_km,
                    qty_days, unit_price, total_amount, note,
                    created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    int(contract_id),
                    str(period),
                    str(service_type),
                    str(title or ""),
                    str(date_from or ""),
                    str(date_to or ""),
                    str(time_text or ""),
                    float(distance_km or 0.0),
                    float(qty_days or 0.0),
                    float(unit_price or 0.0),
                    float(total_amount or 0.0),
                    str(note or ""),
                    now,
                    now,
                ),
            )
            new_id = cur.lastrowid
            conn.commit()
            try:
                return int(new_id)
            except Exception:
                return None
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            return None
        finally:
            conn.close()

    def delete_contract_special_item(self, item_id: int) -> bool:
        self._ensure_contract_special_items_table()
        conn = self.connect()
        if not conn:
            return False
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM contract_special_items WHERE id=?", (int(item_id),))
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

    def _parse_hhmm_to_minutes(self, s: str) -> Optional[int]:
        try:
            txt = str(s or "").strip()
            if not txt:
                return None
            parts = txt.split(":")
            if len(parts) != 2:
                return None
            if (not parts[0].isdigit()) or (not parts[1].isdigit()):
                return None
            hh = int(parts[0])
            mm = int(parts[1])
            if hh < 0 or hh > 23 or mm < 0 or mm > 59:
                return None
            return hh * 60 + mm
        except Exception:
            return None

    def _parse_time_range_minutes(self, time_block: str, time_text: str = "") -> tuple[Optional[int], Optional[int]]:
        t = str(time_text or "").strip()
        if not t:
            t = str(time_block or "").strip()
        if not t:
            return None, None

        if "-" in t:
            left, right = (t.split("-", 1) + [""])[:2]
            m1 = self._parse_hhmm_to_minutes(left.strip())
            m2 = self._parse_hhmm_to_minutes(right.strip())
            if m1 is None or m2 is None:
                return None, None
            if m2 == m1:
                return m1, (m1 + 15) % 1440
            return m1, m2

        m = self._parse_hhmm_to_minutes(t)
        if m is None:
            return None, None
        return m, (m + 15) % 1440

    def _ranges_overlap(self, a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
        def _segments(s: int, e: int):
            if s < 0 or e < 0:
                return []
            if s == e:
                return [(s, (s + 1) % 1440)]
            if s < e:
                return [(s, e)]
            return [(s, 1440), (0, e)]

        for s1, e1 in _segments(int(a_start), int(a_end)):
            for s2, e2 in _segments(int(b_start), int(b_end)):
                if max(s1, s2) < min(e1, e2):
                    return True
        return False

    def get_vehicle_movements_for_day(self, contract_id: int, trip_date: str, vehicle_id) -> int:
        conn = self.connect()
        if not conn:
            return 0
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(*)
                FROM trip_allocations
                WHERE contract_id=?
                  AND trip_date=?
                  AND vehicle_id=?
                  AND COALESCE(qty,0) > 0
                """,
                (int(contract_id), str(trip_date), vehicle_id),
            )
            return int((cur.fetchone() or [0])[0] or 0)
        except Exception:
            return 0
        finally:
            conn.close()

    def find_allocation_conflict(
        self,
        contract_id: int,
        trip_date: str,
        service_type: str,
        time_block: str,
        vehicle_id=None,
        driver_id=None,
        time_text: str = "",
        route_params_id: int | None = None,
        line_no: int | None = None,
        qty: float | None = None,
        note: str = "",
        exclude_route_params_id: int | None = None,
        exclude_time_block: str | None = None,
        exclude_line_no: int | None = None,
    ) -> dict | None:
        start_m, end_m = self._parse_time_range_minutes(str(time_block or ""), str(time_text or ""))
        if start_m is None or end_m is None:
            return None

        conn = self.connect()
        if not conn:
            return None
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT route_params_id, time_block, line_no, vehicle_id, driver_id, COALESCE(time_text,''), COALESCE(qty,0)
                FROM trip_allocations
                WHERE contract_id=?
                  AND trip_date=?
                  AND service_type=?
                  AND COALESCE(qty,0) > 0
                  AND (
                        (? IS NOT NULL AND vehicle_id = ?)
                     OR (? IS NOT NULL AND driver_id = ?)
                  )
                """,
                (
                    int(contract_id),
                    str(trip_date),
                    str(service_type),
                    vehicle_id,
                    vehicle_id,
                    driver_id,
                    driver_id,
                ),
            )
            rows = cur.fetchall() or []
        except Exception:
            rows = []
        finally:
            try:
                conn.close()
            except Exception:
                pass

        for rid, tb, ln, vid, did, tt, qty in rows:
            try:
                if exclude_route_params_id is not None and int(rid or 0) == int(exclude_route_params_id):
                    if exclude_time_block is not None and str(tb or "") == str(exclude_time_block or ""):
                        if exclude_line_no is not None and int(ln or 0) == int(exclude_line_no or 0):
                            continue
            except Exception:
                pass

            s2, e2 = self._parse_time_range_minutes(str(tb or ""), str(tt or ""))
            if s2 is None or e2 is None:
                continue
            if self._ranges_overlap(int(start_m), int(end_m), int(s2), int(e2)):
                return {
                    "route_params_id": int(rid or 0),
                    "time_block": str(tb or ""),
                    "line_no": int(ln or 0),
                    "vehicle_id": vid,
                    "driver_id": did,
                    "time_text": str(tt or ""),
                    "qty": float(qty or 0),
                }
        return None

    def _month_keys_in_range(self, start_date: str, end_date: str) -> list[str]:
        try:
            sd = datetime.strptime(str(start_date), "%Y-%m-%d")
            ed = datetime.strptime(str(end_date), "%Y-%m-%d")
        except Exception:
            return []

        if ed < sd:
            sd, ed = ed, sd

        out: list[str] = []
        y = int(sd.year)
        m = int(sd.month)
        end_y = int(ed.year)
        end_m = int(ed.month)

        while (y < end_y) or (y == end_y and m <= end_m):
            out.append(f"{y:04d}-{m:02d}")
            m += 1
            if m > 12:
                m = 1
                y += 1
        return out

    def _find_seed_month_for_contract(self, contract_id: int, months: list[str]) -> str | None:
        conn = self.connect()
        if not conn:
            return None
        try:
            cur = conn.cursor()

            for mk in months or []:
                try:
                    cur.execute(
                        """
                        SELECT 1
                        FROM trip_plan
                        WHERE contract_id=? AND month=?
                        LIMIT 1
                        """,
                        (int(contract_id), str(mk)),
                    )
                    if cur.fetchone() is not None:
                        return str(mk)
                except Exception:
                    continue

            cur.execute(
                """
                SELECT month
                FROM trip_plan
                WHERE contract_id=?
                ORDER BY month ASC
                LIMIT 1
                """,
                (int(contract_id),),
            )
            row = cur.fetchone()
            if row and row[0]:
                return str(row[0])
            return None
        finally:
            conn.close()

    def sync_contract_operational_templates(self, contract_id: int, start_date: str, end_date: str) -> bool:
        """Sözleşmenin tarih aralığındaki tüm aylar için operasyon şablonlarını üretir/günceller.

        Not: Bu fonksiyon, sözleşmede zaten mevcut olan bir plan ayını (seed) bulup, aynı sözleşme
        için diğer aylara kopyalar. Seed bulunamazsa (hiç plan yoksa) işlem yapılmaz.
        """
        months = self._month_keys_in_range(str(start_date or ""), str(end_date or ""))
        if not months:
            return False

        seed = self._find_seed_month_for_contract(int(contract_id), months)
        if not seed:
            return False

        ok_any = False
        for mk in months:
            if str(mk) == str(seed):
                ok_any = True
                continue
            if self.copy_month_operational_template(str(seed), str(mk)):
                ok_any = True
        return ok_any

    def set_period_closed(self, month: str, user_id: int, note: str = "") -> bool:
        conn = self.connect()
        if not conn:
            return False
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO period_close (month, closed, closed_at, closed_by_user_id, note)
                VALUES (?, 1, datetime('now'), ?, ?)
                ON CONFLICT(month)
                DO UPDATE SET
                    closed = 1,
                    closed_at = datetime('now'),
                    closed_by_user_id = excluded.closed_by_user_id,
                    note = excluded.note
                """,
                (str(month), int(user_id or 0), str(note or "")),
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

    def set_period_opened(self, month: str, user_id: int, reason: str = "") -> bool:
        conn = self.connect()
        if not conn:
            return False
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO period_close (month, closed, closed_at, closed_by_user_id, note)
                VALUES (?, 0, NULL, ?, ?)
                ON CONFLICT(month)
                DO UPDATE SET
                    closed = 0,
                    closed_at = NULL,
                    closed_by_user_id = excluded.closed_by_user_id,
                    note = excluded.note
                """,
                (str(month), int(user_id or 0), str(reason or "")),
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
            # Startup can race with other DB operations; avoid spamming console on transient locks.
            try:
                msg = str(e or "")
            except Exception:
                msg = ""
            if "locked" not in msg.lower():
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
                    driver_id, vehicle_id, qty, time_text, note, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(contract_id, route_params_id, trip_date, service_type, time_block, line_no)
                DO UPDATE SET
                    driver_id=excluded.driver_id,
                    vehicle_id=excluded.vehicle_id,
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
                    driver_id,
                    vehicle_id,
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

    def migrate_trip_route_for_month(
        self,
        contract_id: int,
        service_type: str,
        month: str,
        old_route_params_id: int,
        new_route_params_id: int,
    ) -> bool:
        """Move trip_entries + trip_allocations from old route_params_id to new route_params_id.

        This is used when an assignment was corrected after data entry. Hakediş reads from
        trip_allocations, so allocations must be migrated as well.

        - Scope is limited to (contract_id, service_type, month).
        - If a target row already exists, quantities are merged (summed).
        """

        try:
            cid = int(contract_id or 0)
            old_rid = int(old_route_params_id or 0)
            new_rid = int(new_route_params_id or 0)
        except Exception:
            return False
        st = str(service_type or "").strip()
        m = str(month or "").strip()[:7]
        if cid <= 0 or old_rid <= 0 or new_rid <= 0 or (not st) or len(m) != 7:
            return False

        if old_rid == new_rid:
            return True

        # Ensure tables exist
        try:
            self.create_trip_entries_tables()
        except Exception:
            pass

        start_date = f"{m}-01"
        end_date = f"{m}-31"

        conn = self.connect()
        if not conn:
            return False
        try:
            cur = conn.cursor()
            cur.execute("BEGIN")

            # trip_allocations: merge qty, keep existing non-empty time_text/note when present
            cur.execute(
                """
                INSERT INTO trip_allocations (
                    contract_id, route_params_id, trip_date, service_type, time_block, line_no,
                    driver_id, vehicle_id, qty, time_text, note, created_at, updated_at
                )
                SELECT
                    contract_id, ?, trip_date, service_type, time_block, line_no,
                    driver_id, vehicle_id, qty, time_text, note, created_at, updated_at
                FROM trip_allocations
                WHERE contract_id = ?
                  AND route_params_id = ?
                  AND service_type = ?
                  AND trip_date BETWEEN ? AND ?
                ON CONFLICT(contract_id, route_params_id, trip_date, service_type, time_block, line_no)
                DO UPDATE SET
                    qty = COALESCE(trip_allocations.qty,0) + COALESCE(excluded.qty,0),
                    driver_id = COALESCE(excluded.driver_id, trip_allocations.driver_id),
                    vehicle_id = COALESCE(excluded.vehicle_id, trip_allocations.vehicle_id),
                    time_text = CASE
                        WHEN COALESCE(trip_allocations.time_text,'') <> '' THEN trip_allocations.time_text
                        ELSE COALESCE(excluded.time_text,'')
                    END,
                    note = CASE
                        WHEN COALESCE(trip_allocations.note,'') <> '' THEN trip_allocations.note
                        ELSE COALESCE(excluded.note,'')
                    END,
                    updated_at = COALESCE(excluded.updated_at, trip_allocations.updated_at)
                """,
                (int(new_rid), int(cid), int(old_rid), str(st), str(start_date), str(end_date)),
            )
            cur.execute(
                """
                DELETE FROM trip_allocations
                WHERE contract_id = ?
                  AND route_params_id = ?
                  AND service_type = ?
                  AND trip_date BETWEEN ? AND ?
                """,
                (int(cid), int(old_rid), str(st), str(start_date), str(end_date)),
            )

            # trip_entries: merge qty (integer)
            cur.execute(
                """
                INSERT INTO trip_entries (
                    contract_id, route_params_id, trip_date, service_type, time_block, line_no,
                    qty, time_text, note, created_at, updated_at
                )
                SELECT
                    contract_id, ?, trip_date, service_type, time_block, line_no,
                    qty, time_text, note, created_at, updated_at
                FROM trip_entries
                WHERE contract_id = ?
                  AND route_params_id = ?
                  AND service_type = ?
                  AND trip_date BETWEEN ? AND ?
                ON CONFLICT(contract_id, route_params_id, trip_date, service_type, time_block, line_no)
                DO UPDATE SET
                    qty = COALESCE(trip_entries.qty,0) + COALESCE(excluded.qty,0),
                    time_text = CASE
                        WHEN COALESCE(trip_entries.time_text,'') <> '' THEN trip_entries.time_text
                        ELSE COALESCE(excluded.time_text,'')
                    END,
                    note = CASE
                        WHEN COALESCE(trip_entries.note,'') <> '' THEN trip_entries.note
                        ELSE COALESCE(excluded.note,'')
                    END,
                    updated_at = COALESCE(excluded.updated_at, trip_entries.updated_at)
                """,
                (int(new_rid), int(cid), int(old_rid), str(st), str(start_date), str(end_date)),
            )
            cur.execute(
                """
                DELETE FROM trip_entries
                WHERE contract_id = ?
                  AND route_params_id = ?
                  AND service_type = ?
                  AND trip_date BETWEEN ? AND ?
                """,
                (int(cid), int(old_rid), str(st), str(start_date), str(end_date)),
            )

            conn.commit()
            return True
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                print(f"migrate_trip_route_for_month error: {e}")
            except Exception:
                pass
            return False
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def has_trip_allocations_for_route_month(
        self,
        contract_id: int,
        service_type: str,
        month: str,
        route_params_id: int,
    ) -> bool:
        try:
            cid = int(contract_id or 0)
            rid = int(route_params_id or 0)
        except Exception:
            return False
        st = str(service_type or "").strip()
        m = str(month or "").strip()[:7]
        if cid <= 0 or rid <= 0 or (not st) or len(m) != 7:
            return False

        start_date = f"{m}-01"
        end_date = f"{m}-31"

        conn = self.connect()
        if not conn:
            return False
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT 1
                FROM trip_allocations
                WHERE contract_id = ?
                  AND route_params_id = ?
                  AND service_type = ?
                  AND trip_date BETWEEN ? AND ?
                LIMIT 1
                """,
                (int(cid), int(rid), str(st), str(start_date), str(end_date)),
            )
            return cur.fetchone() is not None
        except Exception:
            return False
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def apply_trip_plan_to_allocations_for_route_month(
        self,
        contract_id: int,
        service_type: str,
        month: str,
        route_params_id: int,
    ) -> int:
        """Update trip_allocations vehicle_id/driver_id based on trip_plan for the given month/route.

        Returns number of affected rows.
        """

        try:
            cid = int(contract_id or 0)
            rid = int(route_params_id or 0)
        except Exception:
            return 0
        st = str(service_type or "").strip()
        m = str(month or "").strip()[:7]
        if cid <= 0 or rid <= 0 or (not st) or len(m) != 7:
            return 0

        start_date = f"{m}-01"
        end_date = f"{m}-31"

        conn = self.connect()
        if not conn:
            return 0
        try:
            cur = conn.cursor()
            cur.execute("BEGIN")
            cur.execute(
                """
                UPDATE trip_allocations
                SET
                    vehicle_id = (
                        SELECT tp.vehicle_id
                        FROM trip_plan tp
                        WHERE tp.contract_id = trip_allocations.contract_id
                          AND tp.route_params_id = trip_allocations.route_params_id
                          AND tp.month = ?
                          AND tp.service_type = trip_allocations.service_type
                          AND tp.time_block = trip_allocations.time_block
                        LIMIT 1
                    ),
                    driver_id = (
                        SELECT tp.driver_id
                        FROM trip_plan tp
                        WHERE tp.contract_id = trip_allocations.contract_id
                          AND tp.route_params_id = trip_allocations.route_params_id
                          AND tp.month = ?
                          AND tp.service_type = trip_allocations.service_type
                          AND tp.time_block = trip_allocations.time_block
                        LIMIT 1
                    ),
                    updated_at = COALESCE(updated_at, '')
                WHERE contract_id = ?
                  AND route_params_id = ?
                  AND service_type = ?
                  AND trip_date BETWEEN ? AND ?
                  AND EXISTS (
                    SELECT 1
                    FROM trip_plan tp
                    WHERE tp.contract_id = trip_allocations.contract_id
                      AND tp.route_params_id = trip_allocations.route_params_id
                      AND tp.month = ?
                      AND tp.service_type = trip_allocations.service_type
                      AND tp.time_block = trip_allocations.time_block
                  )
                """,
                (
                    str(m),
                    str(m),
                    int(cid),
                    int(rid),
                    str(st),
                    str(start_date),
                    str(end_date),
                    str(m),
                ),
            )
            affected = int(cur.rowcount or 0)
            conn.commit()
            return affected
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                print(f"apply_trip_plan_to_allocations_for_route_month error: {e}")
            except Exception:
                pass
            return 0
        finally:
            try:
                conn.close()
            except Exception:
                pass

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
                    pricing_category TEXT DEFAULT '',
                    effective_from TEXT DEFAULT '',
                    price REAL NOT NULL DEFAULT 0,
                    subcontractor_price REAL NOT NULL DEFAULT 0,
                    updated_at TEXT,
                    UNIQUE (contract_id, route_params_id, month, service_type, time_block)
                )
                """
            )

            # --- schema migrations (backward compatible) ---
            cursor.execute("PRAGMA table_info(trip_prices)")
            cols = {row[1] for row in cursor.fetchall()}
            if "pricing_category" not in cols:
                cursor.execute("ALTER TABLE trip_prices ADD COLUMN pricing_category TEXT DEFAULT ''")
            if "effective_from" not in cols:
                cursor.execute("ALTER TABLE trip_prices ADD COLUMN effective_from TEXT DEFAULT ''")
            if "subcontractor_price" not in cols:
                cursor.execute("ALTER TABLE trip_prices ADD COLUMN subcontractor_price REAL NOT NULL DEFAULT 0")

            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_trip_prices_key ON trip_prices(contract_id, month, service_type)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_trip_prices_effective ON trip_prices(contract_id, service_type, route_params_id, pricing_category, effective_from)"
            )
            conn.commit()
        finally:
            conn.close()

    def _ensure_contract_pricing_model_history_table(self):
        conn = self.connect()
        if not conn:
            return
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS contract_pricing_model_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contract_id INTEGER NOT NULL,
                    effective_from TEXT NOT NULL,
                    pricing_model TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT,
                    UNIQUE(contract_id, effective_from)
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_cpmh_key ON contract_pricing_model_history(contract_id, effective_from)"
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_contract_pricing_model_change(
        self,
        contract_id: int,
        effective_from: str,
        pricing_model: str,
        note: str | None = None,
    ) -> bool:
        """Insert/update a pricing model change for a contract.

        pricing_model: VARDIYALI / VARDIYASIZ
        effective_from: YYYY-MM-DD
        """
        self._ensure_contract_pricing_model_history_table()
        conn = self.connect()
        if not conn:
            return False
        try:
            cur = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            pm = str(pricing_model or "").strip().upper()
            if pm not in ("VARDIYALI", "VARDIYASIZ"):
                pm = "VARDIYALI"
            eff = str(effective_from or "").strip()
            if not eff:
                return False
            cur.execute(
                """
                INSERT INTO contract_pricing_model_history(
                    contract_id, effective_from, pricing_model, note, created_at
                ) VALUES (?,?,?,?,?)
                ON CONFLICT(contract_id, effective_from)
                DO UPDATE SET pricing_model=excluded.pricing_model, note=excluded.note
                """,
                (int(contract_id), eff, pm, str(note or ""), now),
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

    def get_pricing_model_for_date(self, contract_id: int, trip_date: str) -> str:
        """Return pricing model (VARDIYALI/VARDIYASIZ) for given contract and trip_date.

        Falls back to customers.pricing_model if no history exists.
        """
        self._ensure_contract_pricing_model_history_table()
        conn = self.connect()
        if not conn:
            return "VARDIYALI"
        try:
            cur = conn.cursor()
            d = str(trip_date or "").strip()
            cur.execute(
                """
                SELECT pricing_model
                FROM contract_pricing_model_history
                WHERE contract_id = ? AND effective_from <= ?
                ORDER BY effective_from DESC
                LIMIT 1
                """,
                (int(contract_id), d),
            )
            row = cur.fetchone()
            if row and str(row[0] or "").strip():
                pm = str(row[0]).strip().upper()
                return pm if pm in ("VARDIYALI", "VARDIYASIZ") else "VARDIYALI"

            # fallback: customer.pricing_model (default)
            cur.execute(
                """
                SELECT COALESCE(cu.pricing_model,'')
                FROM contracts co
                LEFT JOIN customers cu ON cu.id = co.customer_id
                WHERE co.id = ?
                LIMIT 1
                """,
                (int(contract_id),),
            )
            row2 = cur.fetchone()
            pm2 = str(row2[0] if row2 else "").strip().upper()
            return pm2 if pm2 in ("VARDIYALI", "VARDIYASIZ") else "VARDIYALI"
        except Exception:
            return "VARDIYALI"
        finally:
            conn.close()

    def get_trip_price_for_date(
        self,
        contract_id: int,
        service_type: str,
        route_params_id: int,
        pricing_category: str,
        trip_date: str,
    ) -> tuple[float, float, str] | None:
        """Return (price, subcontractor_price, effective_from) for trip_date.

        Looks up trip_prices by latest effective_from <= trip_date.
        """
        self._ensure_trip_prices_table()
        conn = self.connect()
        if not conn:
            return None
        try:
            cur = conn.cursor()
            d = str(trip_date or "").strip()
            pc = str(pricing_category or "").strip().upper()
            row = None

            # 1) Exact category match
            cur.execute(
                """
                SELECT price, subcontractor_price, effective_from
                FROM trip_prices
                WHERE contract_id = ?
                  AND service_type = ?
                  AND route_params_id = ?
                  AND UPPER(COALESCE(pricing_category,'')) = ?
                  AND COALESCE(effective_from,'') <> ''
                  AND effective_from <= ?
                ORDER BY effective_from DESC
                LIMIT 1
                """,
                (int(contract_id), str(service_type), int(route_params_id), pc, d),
            )
            row = cur.fetchone()

            # 2) Fallback: empty/unspecified pricing_category
            if not row:
                cur.execute(
                    """
                    SELECT price, subcontractor_price, effective_from
                    FROM trip_prices
                    WHERE contract_id = ?
                      AND service_type = ?
                      AND route_params_id = ?
                      AND (COALESCE(pricing_category,'') = '')
                      AND COALESCE(effective_from,'') <> ''
                      AND effective_from <= ?
                    ORDER BY effective_from DESC
                    LIMIT 1
                    """,
                    (int(contract_id), str(service_type), int(route_params_id), d),
                )
                row = cur.fetchone()

            # 3) Last resort: any category for same contract/service/route
            if not row:
                cur.execute(
                    """
                    SELECT price, subcontractor_price, effective_from
                    FROM trip_prices
                    WHERE contract_id = ?
                      AND service_type = ?
                      AND route_params_id = ?
                      AND COALESCE(effective_from,'') <> ''
                      AND effective_from <= ?
                    ORDER BY effective_from DESC
                    LIMIT 1
                    """,
                    (int(contract_id), str(service_type), int(route_params_id), d),
                )
                row = cur.fetchone()

            if not row:
                return None
            try:
                p = float(row[0] or 0.0)
            except Exception:
                p = 0.0
            try:
                sp = float(row[1] or 0.0)
            except Exception:
                sp = 0.0
            eff = str(row[2] or "")
            return (p, sp, eff)
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

    def _pricing_category_from_movement_type(self, movement_type: str | None) -> str:
        mt = str(movement_type or "").strip().upper()
        if not mt:
            return "TEK_SERVIS"

        # NOTE: business rule from user: GRŞ/ÇKŞ (dolu/dolu) corresponds to ÇİFT.
        mt2 = (
            mt.replace("Ş", "S")
            .replace("İ", "I")
            .replace("Ğ", "G")
            .replace("Ü", "U")
            .replace("Ö", "O")
            .replace("Ç", "C")
        )

        if "MESA" in mt2:
            return "MESAI"
        if "PAKET" in mt2 or ("SABAH" in mt2 and "AKSAM" in mt2):
            return "PAKET_SERVIS"
        if "GRS" in mt2 or "GIRIS" in mt2 or "CIKIS" in mt2 or "CIFT" in mt2:
            return "CIFT_SERVIS"
        if "TEK" in mt2:
            return "TEK_SERVIS"
        return "TEK_SERVIS"

    def get_hakedis_tab1_yuklenici_araclari_rows(
        self,
        contract_id: int,
        period: str,
        service_type: str,
        customer_id: int | None = None,
        require_locked: bool = True,
    ):
        """Return Tablo-1 rows (YÜKLENİCİ ARAÇLARI) for a given month.

        Output columns (in order):
        - FİRMA, GÜZERGAH, ŞAHIS(arac_sahibi), HAREKET(movement_type), GÜN TEK(qty sum),
          TUTAR(unit subcontractor price), TOPLAM, KDV, ARA TOP, TEVKIFAT, G TOPLAM

        Rules:
        - Only subcontractor vehicles (vehicles.arac_turu contains 'TAŞERON ARACI' variants)
        - Only locked/onaylı periods when require_locked=True (trip_period_lock.locked=1)
        - movement_type is taken from route_params.movement_type
        - pricing_category is derived from movement_type and used to resolve trip_prices.subcontractor_price
        - KDV = TOPLAM * 0.20
        - TEVKIFAT = KDV * 0.50
        - G TOPLAM = (TOPLAM + KDV) - TEVKIFAT
        """

        if not contract_id or not period or not service_type:
            return []

        month = str(period).strip()[:7]
        if len(month) != 7 or month[4] != "-":
            return []

        if require_locked:
            st = self.get_trip_period_lock(int(contract_id), str(month), str(service_type)) or {}
            if not bool(st.get("locked")):
                return []

        # month date range: YYYY-MM-01 .. last day
        try:
            d0 = datetime.strptime(month + "-01", "%Y-%m-%d")
        except Exception:
            return []
        if d0.month == 12:
            d1 = datetime(d0.year + 1, 1, 1)
        else:
            d1 = datetime(d0.year, d0.month + 1, 1)
        start_date = d0.strftime("%Y-%m-%d")
        end_date = (d1 - timedelta(days=1)).strftime("%Y-%m-%d")

        self.create_employees_table()

        conn = self.connect()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            params: list[object] = [
                int(contract_id),
                str(service_type),
                str(start_date),
                str(end_date),
                int(contract_id),
                str(service_type),
                str(start_date),
                str(end_date),
                int(contract_id),
                str(service_type),
                str(start_date),
                str(end_date),
            ]
            customer_filter_sql = ""
            if customer_id is not None:
                customer_filter_sql = " AND cu.id = ? "
                params.append(int(customer_id))

            # subcontractor vehicle filter: accept common variations
            # We use ascii-normalized LIKE checks.
            cur.execute(
                f"""
                WITH split_groups AS (
                    SELECT
                        contract_id,
                        route_params_id,
                        trip_date,
                        service_type,
                        time_block,
                        1 AS has_split
                    FROM (
                        SELECT
                            contract_id,
                            route_params_id,
                            trip_date,
                            service_type,
                            COALESCE(TRIM(time_block), '') AS time_block,
                            MAX(COALESCE(line_no,0)) AS max_ln
                        FROM trip_entries
                        WHERE contract_id = ?
                          AND service_type = ?
                          AND trip_date BETWEEN ? AND ?
                        GROUP BY contract_id, route_params_id, trip_date, service_type, COALESCE(TRIM(time_block), '')

                        UNION ALL

                        SELECT
                            contract_id,
                            route_params_id,
                            trip_date,
                            service_type,
                            COALESCE(TRIM(time_block), '') AS time_block,
                            MAX(COALESCE(line_no,0)) AS max_ln
                        FROM trip_allocations
                        WHERE contract_id = ?
                          AND service_type = ?
                          AND trip_date BETWEEN ? AND ?
                        GROUP BY contract_id, route_params_id, trip_date, service_type, COALESCE(TRIM(time_block), '')
                    ) u
                    WHERE COALESCE(u.max_ln,0) > 0
                    GROUP BY contract_id, route_params_id, trip_date, service_type, time_block
                )
                SELECT
                    COALESCE(cu.title, '') AS firma,
                    (COALESCE(rp.route_name, '') || CASE WHEN COALESCE(rp.stops,'') <> '' THEN (' | ' || COALESCE(rp.stops,'')) ELSE '' END) AS guzergah,
                    COALESCE(v.arac_sahibi, COALESCE(e.ad_soyad,''), '') AS sahis,
                    COALESCE(rp.movement_type, '') AS hareket,
                    SUM(CASE WHEN COALESCE(sg.has_split,0)=1 THEN (COALESCE(ta.qty,0) / 2.0) ELSE COALESCE(ta.qty,0) END) AS qty_sum,
                    MAX(COALESCE(ta.trip_date, '')) AS last_trip_date,
                    rp.id AS route_params_id
                FROM trip_allocations ta
                LEFT JOIN split_groups sg
                  ON sg.contract_id = ta.contract_id
                 AND sg.route_params_id = ta.route_params_id
                 AND sg.trip_date = ta.trip_date
                 AND sg.service_type = ta.service_type
                 AND sg.time_block = COALESCE(TRIM(ta.time_block), '')
                LEFT JOIN route_params rp ON rp.id = ta.route_params_id
                LEFT JOIN vehicles v ON (v.id = ta.vehicle_id OR v.vehicle_code = CAST(ta.vehicle_id AS TEXT))
                LEFT JOIN employees e ON e.personel_kodu = CAST(ta.driver_id AS TEXT)
                LEFT JOIN contracts co ON co.id = ta.contract_id
                LEFT JOIN customers cu ON cu.id = co.customer_id
                WHERE ta.contract_id = ?
                  AND ta.service_type = ?
                  AND ta.trip_date BETWEEN ? AND ?
                  AND (
                        (
                            v.id IS NOT NULL
                            AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(v.arac_turu,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%TASERON%'
                            AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(v.arac_turu,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%ARAC%'
                        )
                        OR (
                            v.id IS NULL
                            AND COALESCE(e.ad_soyad, CAST(ta.driver_id AS TEXT), '') <> ''
                            AND NOT (
                                REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(e.ad_soyad,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%ASIL%'
                                AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(e.ad_soyad,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%TUR%'
                            )
                        )
                  )
                  AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(rp.movement_type,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') NOT LIKE '%CENAZE%'
                  {customer_filter_sql}
                GROUP BY
                    COALESCE(cu.title, ''),
                    (COALESCE(rp.route_name, '') || CASE WHEN COALESCE(rp.stops,'') <> '' THEN (' | ' || COALESCE(rp.stops,'')) ELSE '' END),
                    COALESCE(v.arac_sahibi, COALESCE(e.ad_soyad,''), ''),
                    COALESCE(rp.movement_type, ''),
                    rp.id
                ORDER BY firma, sahis, guzergah
                """,
                tuple(params),
            )
            grouped = cur.fetchall() or []
        finally:
            try:
                conn.close()
            except Exception:
                pass

        out_rows = []
        # price cache: (route_params_id, pricing_category, trip_date) -> subcontractor_price
        price_cache: dict[tuple[int, str, str], float] = {}

        for firma, guzergah, sahis, hareket, qty_sum, last_trip_date, route_params_id in grouped:
            try:
                rid = int(route_params_id or 0)
            except Exception:
                rid = 0
            if rid <= 0:
                continue

            try:
                qty_f = float(qty_sum or 0.0)
            except Exception:
                qty_f = 0.0
            if qty_f <= 0:
                continue

            unit_price = 0.0
            st = str(service_type or "").strip()
            if st:
                pc = self._pricing_category_from_movement_type(str(hareket or ""))
                d_for_price = str(last_trip_date or "").strip() or str(end_date)
                key = (rid, pc, d_for_price)
                if key in price_cache:
                    unit_price = float(price_cache.get(key) or 0.0)
                else:
                    unit_price = 0.0
                    try:
                        pr = self.get_trip_price_for_date(
                            contract_id=int(contract_id),
                            service_type=str(st),
                            route_params_id=int(rid),
                            pricing_category=str(pc),
                            trip_date=str(d_for_price),
                        )
                        if pr:
                            unit_price = float(pr[1] or 0.0)
                    except Exception:
                        unit_price = 0.0
                    price_cache[key] = float(unit_price or 0.0)

            total = float(qty_f * float(unit_price or 0.0))
            kdv = float(total * 0.20)
            ara_top = float(total + kdv)
            tevkifat = float(kdv * 0.50)
            g_toplam = float(ara_top - tevkifat)

            out_rows.append(
                (
                    str(firma or ""),
                    str(guzergah or ""),
                    str(sahis or ""),
                    str(hareket or ""),
                    qty_f,
                    float(unit_price or 0.0),
                    total,
                    kdv,
                    ara_top,
                    tevkifat,
                    g_toplam,
                )
            )

        return out_rows

    def get_hakedis_tab1_owner_list_for_period(
        self,
        period: str,
        customer_id: int | None = None,
    ) -> list[str]:
        month = str(period).strip()[:7]
        if len(month) != 7 or month[4] != "-":
            return []

        try:
            d0 = datetime.strptime(month + "-01", "%Y-%m-%d")
        except Exception:
            return []
        if d0.month == 12:
            d1 = datetime(d0.year + 1, 1, 1)
        else:
            d1 = datetime(d0.year, d0.month + 1, 1)
        start_date = d0.strftime("%Y-%m-%d")
        end_date = (d1 - timedelta(days=1)).strftime("%Y-%m-%d")

        conn = self.connect()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            customer_filter_sql = ""
            if customer_id is not None:
                customer_filter_sql = " AND cu.id = ? "

            params: list[object] = [
                # eff: trip_entries
                str(start_date),
                str(end_date),
                # eff: trip_allocations (entries not found)
                str(start_date),
                str(end_date),
                # owners (ta.trip_date filter)
                str(start_date),
                str(end_date),
            ]
            if customer_id is not None:
                params.append(int(customer_id))

            cur.execute(
                f"""
                SELECT DISTINCT owner FROM (
                    WITH eff AS (
                        SELECT
                            te.contract_id,
                            te.route_params_id,
                            te.trip_date,
                            te.service_type,
                            COALESCE(TRIM(te.time_block), '') AS time_block,
                            COALESCE(te.line_no, 0) AS line_no,
                            COALESCE(ta.vehicle_id, tp.vehicle_id) AS vehicle_id,
                            COALESCE(ta.driver_id, tp.driver_id) AS driver_id,
                            COALESCE(ta.qty, te.qty, 0) AS qty,
                            COALESCE(ta.time_text, te.time_text, '') AS time_text,
                            COALESCE(ta.note, '') AS note
                        FROM trip_entries te
                        LEFT JOIN trip_plan tp
                          ON tp.contract_id = te.contract_id
                         AND tp.route_params_id = te.route_params_id
                         AND tp.service_type = te.service_type
                         AND COALESCE(TRIM(tp.time_block), '') = COALESCE(TRIM(te.time_block), '')
                         AND COALESCE(TRIM(tp.month), '') = SUBSTR(COALESCE(te.trip_date,''), 1, 7)
                        LEFT JOIN trip_allocations ta
                          ON ta.contract_id = te.contract_id
                         AND ta.route_params_id = te.route_params_id
                         AND ta.trip_date = te.trip_date
                         AND ta.service_type = te.service_type
                         AND COALESCE(TRIM(ta.time_block), '') = COALESCE(TRIM(te.time_block), '')
                         AND COALESCE(ta.line_no, 0) = COALESCE(te.line_no, 0)
                        WHERE te.trip_date BETWEEN ? AND ?

                        UNION ALL

                        SELECT
                            ta.contract_id,
                            ta.route_params_id,
                            ta.trip_date,
                            ta.service_type,
                            COALESCE(TRIM(ta.time_block), '') AS time_block,
                            COALESCE(ta.line_no, 0) AS line_no,
                            ta.vehicle_id,
                            ta.driver_id,
                            COALESCE(ta.qty, 0) AS qty,
                            COALESCE(ta.time_text, '') AS time_text,
                            COALESCE(ta.note, '') AS note
                        FROM trip_allocations ta
                        LEFT JOIN trip_entries te
                          ON te.contract_id = ta.contract_id
                         AND te.route_params_id = ta.route_params_id
                         AND te.trip_date = ta.trip_date
                         AND te.service_type = ta.service_type
                         AND COALESCE(TRIM(te.time_block), '') = COALESCE(TRIM(ta.time_block), '')
                         AND COALESCE(te.line_no, 0) = COALESCE(ta.line_no, 0)
                        WHERE te.contract_id IS NULL
                          AND ta.trip_date BETWEEN ? AND ?
                    )

                    SELECT COALESCE(v.arac_sahibi,'') AS owner
                    FROM eff ta
                    LEFT JOIN vehicles v ON (v.id = ta.vehicle_id OR v.vehicle_code = CAST(ta.vehicle_id AS TEXT))
                    LEFT JOIN contracts co ON co.id = ta.contract_id
                    LEFT JOIN customers cu ON cu.id = co.customer_id
                    WHERE v.id IS NOT NULL
                      AND COALESCE(v.arac_sahibi,'') <> ''
                      AND ta.trip_date BETWEEN ? AND ?
                      AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(v.arac_turu,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%TASERON%'
                      AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(v.arac_turu,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%ARAC%'
                      {customer_filter_sql}
                )
                WHERE COALESCE(owner,'') <> ''
                ORDER BY owner
                """,
                tuple(params),
            )
            owners = [str(r[0] or "").strip() for r in (cur.fetchall() or [])]
        finally:
            try:
                conn.close()
            except Exception:
                pass

        return [o for o in owners if o]

    def get_hakedis_tab1_owner_report_rows_all(
        self,
        period: str,
        owner: str,
        customer_id: int | None = None,
    ):
        month = str(period).strip()[:7]
        if len(month) != 7 or month[4] != "-":
            return []
        if not str(owner or "").strip():
            return []

        try:
            d0 = datetime.strptime(month + "-01", "%Y-%m-%d")
        except Exception:
            return []
        if d0.month == 12:
            d1 = datetime(d0.year + 1, 1, 1)
        else:
            d1 = datetime(d0.year, d0.month + 1, 1)
        start_date = d0.strftime("%Y-%m-%d")
        end_date = (d1 - timedelta(days=1)).strftime("%Y-%m-%d")

        self.create_employees_table()

        owner_param = str(owner or "").strip()
        conn = self.connect()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            params: list[object] = [
                # eff: trip_entries
                str(start_date),
                str(end_date),
                # eff: trip_allocations (entries not found)
                str(start_date),
                str(end_date),
                # split_groups: eff.trip_date between
                str(start_date),
                str(end_date),
                # main WHERE ta.trip_date between
                str(start_date),
                str(end_date),
                str(owner_param),
            ]
            customer_filter_sql = ""
            if customer_id is not None:
                customer_filter_sql = " AND cu.id = ? "
                params.append(int(customer_id))

            cur.execute(
                f"""
                WITH eff AS (
                    SELECT
                        te.contract_id,
                        te.route_params_id,
                        te.trip_date,
                        te.service_type,
                        COALESCE(TRIM(te.time_block), '') AS time_block,
                        COALESCE(te.line_no, 0) AS line_no,
                        COALESCE(ta.vehicle_id, tp.vehicle_id) AS vehicle_id,
                        COALESCE(ta.driver_id, tp.driver_id) AS driver_id,
                        COALESCE(ta.qty, te.qty, 0) AS qty,
                        COALESCE(ta.time_text, te.time_text, '') AS time_text,
                        COALESCE(ta.note, '') AS note
                    FROM trip_entries te
                    LEFT JOIN trip_plan tp
                      ON tp.contract_id = te.contract_id
                     AND tp.route_params_id = te.route_params_id
                     AND tp.service_type = te.service_type
                     AND COALESCE(TRIM(tp.time_block), '') = COALESCE(TRIM(te.time_block), '')
                     AND COALESCE(TRIM(tp.month), '') = SUBSTR(COALESCE(te.trip_date,''), 1, 7)
                    LEFT JOIN trip_allocations ta
                      ON ta.contract_id = te.contract_id
                     AND ta.route_params_id = te.route_params_id
                     AND ta.trip_date = te.trip_date
                     AND ta.service_type = te.service_type
                     AND COALESCE(TRIM(ta.time_block), '') = COALESCE(TRIM(te.time_block), '')
                     AND COALESCE(ta.line_no, 0) = COALESCE(te.line_no, 0)
                    WHERE te.trip_date BETWEEN ? AND ?

                    UNION ALL

                    SELECT
                        ta.contract_id,
                        ta.route_params_id,
                        ta.trip_date,
                        ta.service_type,
                        COALESCE(TRIM(ta.time_block), '') AS time_block,
                        COALESCE(ta.line_no, 0) AS line_no,
                        ta.vehicle_id,
                        ta.driver_id,
                        COALESCE(ta.qty, 0) AS qty,
                        COALESCE(ta.time_text, '') AS time_text,
                        COALESCE(ta.note, '') AS note
                    FROM trip_allocations ta
                    LEFT JOIN trip_entries te
                      ON te.contract_id = ta.contract_id
                     AND te.route_params_id = ta.route_params_id
                     AND te.trip_date = ta.trip_date
                     AND te.service_type = ta.service_type
                     AND COALESCE(TRIM(te.time_block), '') = COALESCE(TRIM(ta.time_block), '')
                     AND COALESCE(te.line_no, 0) = COALESCE(ta.line_no, 0)
                    WHERE te.contract_id IS NULL
                      AND ta.trip_date BETWEEN ? AND ?
                ),

                split_groups AS (
                    SELECT
                        contract_id,
                        route_params_id,
                        trip_date,
                        service_type,
                        COALESCE(TRIM(time_block), '') AS time_block,
                        1 AS has_split
                    FROM eff
                    WHERE trip_date BETWEEN ? AND ?
                    GROUP BY contract_id, route_params_id, trip_date, service_type, COALESCE(TRIM(time_block), '')
                    HAVING MAX(COALESCE(line_no,0)) > 0
                )
                SELECT
                    COALESCE(cu.title, '') AS firma,
                    (COALESCE(rp.route_name, '') || CASE WHEN COALESCE(rp.stops,'') <> '' THEN (' | ' || COALESCE(rp.stops,'')) ELSE '' END) AS guzergah,
                    COALESCE(v.arac_sahibi,'') AS owner,
                    COALESCE(e.ad_soyad, CAST(ta.driver_id AS TEXT), '') AS sofor,
                    COALESCE(v.plate_number,'') AS plaka,
                    COALESCE(rp.movement_type, '') AS hareket,
                    SUM(CASE WHEN COALESCE(sg.has_split,0)=1 THEN (COALESCE(ta.qty,0) / 2.0) ELSE COALESCE(ta.qty,0) END) AS qty_sum,
                    MAX(COALESCE(ta.trip_date, '')) AS last_trip_date,
                    rp.id AS route_params_id,
                    ta.contract_id AS contract_id,
                    COALESCE(ta.service_type,'') AS service_type
                FROM eff ta
                LEFT JOIN split_groups sg
                  ON sg.contract_id = ta.contract_id
                 AND sg.route_params_id = ta.route_params_id
                 AND sg.trip_date = ta.trip_date
                 AND sg.service_type = ta.service_type
                 AND sg.time_block = COALESCE(TRIM(ta.time_block), '')
                LEFT JOIN route_params rp ON rp.id = ta.route_params_id
                LEFT JOIN vehicles v ON (v.id = ta.vehicle_id OR v.vehicle_code = CAST(ta.vehicle_id AS TEXT))
                LEFT JOIN employees e ON (
                    TRIM(COALESCE(e.personel_kodu,'')) = TRIM(CAST(ta.driver_id AS TEXT))
                    OR LTRIM(TRIM(COALESCE(e.personel_kodu,'')), '0') = LTRIM(TRIM(CAST(ta.driver_id AS TEXT)), '0')
                )
                LEFT JOIN contracts co ON co.id = ta.contract_id
                LEFT JOIN customers cu ON cu.id = co.customer_id
                WHERE ta.trip_date BETWEEN ? AND ?
                  AND v.id IS NOT NULL
                  AND COALESCE(v.arac_sahibi,'') <> ''
                  AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(v.arac_turu,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%TASERON%'
                  AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(v.arac_turu,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%ARAC%'
                  AND (
                        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(v.arac_sahibi,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C')
                        =
                        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(? ,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C')
                  )
                  AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(rp.movement_type,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') NOT LIKE '%CENAZE%'
                  {customer_filter_sql}
                GROUP BY
                    COALESCE(cu.title, ''),
                    (COALESCE(rp.route_name, '') || CASE WHEN COALESCE(rp.stops,'') <> '' THEN (' | ' || COALESCE(rp.stops,'')) ELSE '' END),
                    COALESCE(v.arac_sahibi,''),
                    COALESCE(e.ad_soyad,''),
                    COALESCE(v.plate_number,''),
                    COALESCE(rp.movement_type, ''),
                    rp.id,
                    ta.contract_id,
                    COALESCE(ta.service_type,'')
                ORDER BY firma, guzergah, hareket, plaka
                """,
                tuple(params),
            )
            grouped = cur.fetchall() or []
        finally:
            try:
                conn.close()
            except Exception:
                pass

        out_rows = []
        price_cache: dict[tuple[int, str, str, int, str], float] = {}

        for (
            firma,
            guzergah,
            owner2,
            sofor,
            plaka,
            hareket,
            qty_sum,
            last_trip_date,
            route_params_id,
            contract_id,
            service_type,
        ) in grouped:
            try:
                rid = int(route_params_id or 0)
            except Exception:
                rid = 0
            if rid <= 0:
                continue

            try:
                cid = int(contract_id or 0)
            except Exception:
                cid = 0
            if cid <= 0:
                continue

            st = str(service_type or "").strip()

            try:
                qty_f = float(qty_sum or 0.0)
            except Exception:
                qty_f = 0.0
            if qty_f <= 0:
                continue

            unit_price = 0.0
            if st:
                pc = self._pricing_category_from_movement_type(str(hareket or ""))
                d_for_price = str(last_trip_date or "").strip() or str(end_date)
                key = (rid, pc, d_for_price, cid, st)
                if key in price_cache:
                    unit_price = float(price_cache.get(key) or 0.0)
                else:
                    unit_price = 0.0
                    try:
                        pr = self.get_trip_price_for_date(
                            contract_id=int(cid),
                            service_type=str(st),
                            route_params_id=int(rid),
                            pricing_category=str(pc),
                            trip_date=str(d_for_price),
                        )
                        if pr:
                            unit_price = float(pr[1] or 0.0)
                    except Exception:
                        unit_price = 0.0
                    price_cache[key] = float(unit_price or 0.0)

            total = float(qty_f * float(unit_price or 0.0))
            kdv = float(total * 0.20)
            ara_top = float(total + kdv)
            tevkifat = float(kdv * 0.50)
            g_toplam = float(ara_top - tevkifat)

            sahis = (str(owner2 or "").strip() + (" / " + str(sofor or "").strip() if str(sofor or "").strip() else "")).strip()

            out_rows.append(
                (
                    str(firma or ""),
                    str(guzergah or ""),
                    str(sahis or ""),
                    str(plaka or ""),
                    str(hareket or ""),
                    qty_f,
                    float(unit_price or 0.0),
                    total,
                    kdv,
                    ara_top,
                    tevkifat,
                    g_toplam,
                )
            )

        return out_rows

    def get_hakedis_tab1_yuklenici_araclari_rows_all(
        self,
        period: str,
        customer_id: int | None = None,
    ):
        """Return Tablo-1 rows (YÜKLENİCİ ARAÇLARI) across ALL contracts for a given month.

        Output columns (in order):
        - FİRMA, GÜZERGAH, ŞAHIS(arac_sahibi), HAREKET(movement_type), GÜN TOP(qty sum),
          TUTAR(unit subcontractor price), TOPLAM, KDV, ARA TOP, TEVKIFAT, G TOPLAM
        """

        month = str(period).strip()[:7]
        if len(month) != 7 or month[4] != "-":
            return []

        try:
            d0 = datetime.strptime(month + "-01", "%Y-%m-%d")
        except Exception:
            return []
        if d0.month == 12:
            d1 = datetime(d0.year + 1, 1, 1)
        else:
            d1 = datetime(d0.year, d0.month + 1, 1)
        start_date = d0.strftime("%Y-%m-%d")
        end_date = (d1 - timedelta(days=1)).strftime("%Y-%m-%d")

        self.create_employees_table()

        conn = self.connect()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            params: list[object] = [
                str(start_date),
                str(end_date),
                str(start_date),
                str(end_date),
                str(start_date),
                str(end_date),
                str(start_date),
                str(end_date),
            ]
            customer_filter_sql = ""
            if customer_id is not None:
                customer_filter_sql = " AND cu.id = ? "
                params.append(int(customer_id))

            cur.execute(
                f"""
                WITH eff AS (
                    SELECT
                        te.contract_id,
                        te.route_params_id,
                        te.trip_date,
                        te.service_type,
                        COALESCE(TRIM(te.time_block), '') AS time_block,
                        COALESCE(te.line_no, 0) AS line_no,
                        COALESCE(ta.vehicle_id, tp.vehicle_id) AS vehicle_id,
                        COALESCE(ta.driver_id, tp.driver_id) AS driver_id,
                        COALESCE(ta.qty, te.qty, 0) AS qty,
                        COALESCE(ta.time_text, te.time_text, '') AS time_text,
                        COALESCE(ta.note, '') AS note
                    FROM trip_entries te
                    LEFT JOIN trip_plan tp
                      ON tp.contract_id = te.contract_id
                     AND tp.route_params_id = te.route_params_id
                     AND tp.service_type = te.service_type
                     AND COALESCE(TRIM(tp.time_block), '') = COALESCE(TRIM(te.time_block), '')
                     AND COALESCE(TRIM(tp.month), '') = SUBSTR(COALESCE(te.trip_date,''), 1, 7)
                    LEFT JOIN trip_allocations ta
                      ON ta.contract_id = te.contract_id
                     AND ta.route_params_id = te.route_params_id
                     AND ta.trip_date = te.trip_date
                     AND ta.service_type = te.service_type
                     AND COALESCE(TRIM(ta.time_block), '') = COALESCE(TRIM(te.time_block), '')
                     AND COALESCE(ta.line_no, 0) = COALESCE(te.line_no, 0)
                    WHERE te.trip_date BETWEEN ? AND ?

                    UNION ALL

                    SELECT
                        ta.contract_id,
                        ta.route_params_id,
                        ta.trip_date,
                        ta.service_type,
                        COALESCE(TRIM(ta.time_block), '') AS time_block,
                        COALESCE(ta.line_no, 0) AS line_no,
                        ta.vehicle_id,
                        ta.driver_id,
                        COALESCE(ta.qty, 0) AS qty,
                        COALESCE(ta.time_text, '') AS time_text,
                        COALESCE(ta.note, '') AS note
                    FROM trip_allocations ta
                    LEFT JOIN trip_entries te
                      ON te.contract_id = ta.contract_id
                     AND te.route_params_id = ta.route_params_id
                     AND te.trip_date = ta.trip_date
                     AND te.service_type = ta.service_type
                     AND COALESCE(TRIM(te.time_block), '') = COALESCE(TRIM(ta.time_block), '')
                     AND COALESCE(te.line_no, 0) = COALESCE(ta.line_no, 0)
                    WHERE te.contract_id IS NULL
                      AND ta.trip_date BETWEEN ? AND ?
                ),

                split_groups AS (
                    SELECT
                        contract_id,
                        route_params_id,
                        trip_date,
                        service_type,
                        COALESCE(TRIM(time_block), '') AS time_block,
                        1 AS has_split
                    FROM eff
                    WHERE trip_date BETWEEN ? AND ?
                    GROUP BY contract_id, route_params_id, trip_date, service_type, COALESCE(TRIM(time_block), '')
                    HAVING MAX(COALESCE(line_no,0)) > 0
                )
                SELECT
                    COALESCE(cu.title, '') AS firma,
                    (COALESCE(rp.route_name, '') || CASE WHEN COALESCE(rp.stops,'') <> '' THEN (' | ' || COALESCE(rp.stops,'')) ELSE '' END) AS guzergah,
                    COALESCE(v.arac_sahibi, COALESCE(e.ad_soyad, CAST(ta.driver_id AS TEXT), ''), '') AS sahis,
                    COALESCE(rp.movement_type, '') AS hareket,
                    SUM(CASE WHEN COALESCE(sg.has_split,0)=1 THEN (COALESCE(ta.qty,0) / 2.0) ELSE COALESCE(ta.qty,0) END) AS qty_sum,
                    MAX(COALESCE(ta.trip_date, '')) AS last_trip_date,
                    rp.id AS route_params_id,
                    ta.contract_id AS contract_id,
                    COALESCE(ta.service_type,'') AS service_type
                FROM eff ta
                LEFT JOIN split_groups sg
                  ON sg.contract_id = ta.contract_id
                 AND sg.route_params_id = ta.route_params_id
                 AND sg.trip_date = ta.trip_date
                 AND sg.service_type = ta.service_type
                 AND sg.time_block = COALESCE(TRIM(ta.time_block), '')
                LEFT JOIN route_params rp ON rp.id = ta.route_params_id
                LEFT JOIN vehicles v ON (v.id = ta.vehicle_id OR v.vehicle_code = CAST(ta.vehicle_id AS TEXT))
                LEFT JOIN employees e ON (
                    TRIM(COALESCE(e.personel_kodu,'')) = TRIM(CAST(ta.driver_id AS TEXT))
                    OR LTRIM(TRIM(COALESCE(e.personel_kodu,'')), '0') = LTRIM(TRIM(CAST(ta.driver_id AS TEXT)), '0')
                )
                LEFT JOIN contracts co ON co.id = ta.contract_id
                LEFT JOIN customers cu ON cu.id = co.customer_id
                WHERE ta.trip_date BETWEEN ? AND ?
                  AND (
                        (
                            v.id IS NOT NULL
                            AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(v.arac_turu,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%TASERON%'
                            AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(v.arac_turu,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%ARAC%'
                        )
                        OR (
                            v.id IS NULL
                            AND COALESCE(e.ad_soyad, CAST(ta.driver_id AS TEXT), '') <> ''
                            AND NOT (
                                REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(e.ad_soyad,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%ASIL%'
                                AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(e.ad_soyad,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%TUR%'
                            )
                        )
                  )
                  AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(rp.movement_type,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') NOT LIKE '%CENAZE%'
                  {customer_filter_sql}
                GROUP BY
                    COALESCE(cu.title, ''),
                    (COALESCE(rp.route_name, '') || CASE WHEN COALESCE(rp.stops,'') <> '' THEN (' | ' || COALESCE(rp.stops,'')) ELSE '' END),
                    COALESCE(v.arac_sahibi, COALESCE(e.ad_soyad,''), ''),
                    COALESCE(rp.movement_type, ''),
                    rp.id,
                    ta.contract_id,
                    COALESCE(ta.service_type,'')
                ORDER BY firma, sahis, guzergah
                """,
                tuple(params),
            )
            grouped = cur.fetchall() or []
        finally:
            try:
                conn.close()
            except Exception:
                pass

        out_rows = []
        price_cache: dict[tuple[int, str, str, int, str], float] = {}

        for (
            firma,
            guzergah,
            sahis,
            hareket,
            qty_sum,
            last_trip_date,
            route_params_id,
            contract_id,
            service_type,
        ) in grouped:
            try:
                rid = int(route_params_id or 0)
            except Exception:
                rid = 0
            if rid <= 0:
                continue

            try:
                cid = int(contract_id or 0)
            except Exception:
                cid = 0
            if cid <= 0:
                continue

            st = str(service_type or "").strip()

            try:
                qty_f = float(qty_sum or 0.0)
            except Exception:
                qty_f = 0.0
            if qty_f <= 0:
                continue

            unit_price = 0.0
            if st:
                pc = self._pricing_category_from_movement_type(str(hareket or ""))
                d_for_price = str(last_trip_date or "").strip() or str(end_date)
                key = (rid, pc, d_for_price, cid, st)
                if key in price_cache:
                    unit_price = float(price_cache.get(key) or 0.0)
                else:
                    unit_price = 0.0
                    try:
                        pr = self.get_trip_price_for_date(
                            contract_id=int(cid),
                            service_type=str(st),
                            route_params_id=int(rid),
                            pricing_category=str(pc),
                            trip_date=str(d_for_price),
                        )
                        if pr:
                            unit_price = float(pr[1] or 0.0)
                    except Exception:
                        unit_price = 0.0
                    price_cache[key] = float(unit_price or 0.0)

            total = float(qty_f * float(unit_price or 0.0))
            kdv = float(total * 0.20)
            ara_top = float(total + kdv)
            tevkifat = float(kdv * 0.50)
            g_toplam = float(ara_top - tevkifat)

            out_rows.append(
                (
                    str(firma or ""),
                    str(guzergah or ""),
                    str(sahis or ""),
                    str(hareket or ""),
                    qty_f,
                    float(unit_price or 0.0),
                    total,
                    kdv,
                    ara_top,
                    tevkifat,
                    g_toplam,
                )
            )

        return out_rows

    def get_hakedis_tab2_sirket_araclari_rows_all(
        self,
        period: str,
        customer_id: int | None = None,
    ):
        """Return Tablo-2 rows (ŞİRKET ARAÇLARI) across ALL contracts for a given month.

        Output columns (in order):
        - GÜZERGAH, ŞAHIS(arac_sahibi), PLAKA, HAREKET(movement_type), GÜN TOP(qty sum),
          TUTAR(unit price), TOPLAM, KDV, ARA TOP, TEVKIFAT, G TOPLAM
        """

        month = str(period).strip()[:7]
        if len(month) != 7 or month[4] != "-":
            return []

        try:
            d0 = datetime.strptime(month + "-01", "%Y-%m-%d")
        except Exception:
            return []
        if d0.month == 12:
            d1 = datetime(d0.year + 1, 1, 1)
        else:
            d1 = datetime(d0.year, d0.month + 1, 1)
        start_date = d0.strftime("%Y-%m-%d")
        end_date = (d1 - timedelta(days=1)).strftime("%Y-%m-%d")

        self.create_employees_table()

        conn = self.connect()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            params: list[object] = [
                str(start_date),
                str(end_date),
                str(start_date),
                str(end_date),
                str(start_date),
                str(end_date),
                str(start_date),
                str(end_date),
            ]
            customer_filter_sql = ""
            if customer_id is not None:
                customer_filter_sql = " AND cu.id = ? "
                params.append(int(customer_id))

            cur.execute(
                f"""
                WITH eff AS (
                    SELECT
                        te.contract_id,
                        te.route_params_id,
                        te.trip_date,
                        te.service_type,
                        COALESCE(TRIM(te.time_block), '') AS time_block,
                        COALESCE(te.line_no, 0) AS line_no,
                        COALESCE(ta.vehicle_id, tp.vehicle_id) AS vehicle_id,
                        COALESCE(ta.driver_id, tp.driver_id) AS driver_id,
                        COALESCE(ta.qty, te.qty, 0) AS qty,
                        COALESCE(ta.time_text, te.time_text, '') AS time_text,
                        COALESCE(ta.note, '') AS note
                    FROM trip_entries te
                    LEFT JOIN trip_plan tp
                      ON tp.contract_id = te.contract_id
                     AND tp.route_params_id = te.route_params_id
                     AND tp.service_type = te.service_type
                     AND COALESCE(TRIM(tp.time_block), '') = COALESCE(TRIM(te.time_block), '')
                     AND COALESCE(TRIM(tp.month), '') = SUBSTR(COALESCE(te.trip_date,''), 1, 7)
                    LEFT JOIN trip_allocations ta
                      ON ta.contract_id = te.contract_id
                     AND ta.route_params_id = te.route_params_id
                     AND ta.trip_date = te.trip_date
                     AND ta.service_type = te.service_type
                     AND COALESCE(TRIM(ta.time_block), '') = COALESCE(TRIM(te.time_block), '')
                     AND COALESCE(ta.line_no, 0) = COALESCE(te.line_no, 0)
                    WHERE te.trip_date BETWEEN ? AND ?

                    UNION ALL

                    SELECT
                        ta.contract_id,
                        ta.route_params_id,
                        ta.trip_date,
                        ta.service_type,
                        COALESCE(TRIM(ta.time_block), '') AS time_block,
                        COALESCE(ta.line_no, 0) AS line_no,
                        ta.vehicle_id,
                        ta.driver_id,
                        COALESCE(ta.qty, 0) AS qty,
                        COALESCE(ta.time_text, '') AS time_text,
                        COALESCE(ta.note, '') AS note
                    FROM trip_allocations ta
                    LEFT JOIN trip_entries te
                      ON te.contract_id = ta.contract_id
                     AND te.route_params_id = ta.route_params_id
                     AND te.trip_date = ta.trip_date
                     AND te.service_type = ta.service_type
                     AND COALESCE(TRIM(te.time_block), '') = COALESCE(TRIM(ta.time_block), '')
                     AND COALESCE(te.line_no, 0) = COALESCE(ta.line_no, 0)
                    WHERE te.contract_id IS NULL
                      AND ta.trip_date BETWEEN ? AND ?
                ),

                split_groups AS (
                    SELECT
                        contract_id,
                        route_params_id,
                        trip_date,
                        service_type,
                        COALESCE(TRIM(time_block), '') AS time_block,
                        1 AS has_split
                    FROM eff
                    WHERE trip_date BETWEEN ? AND ?
                    GROUP BY contract_id, route_params_id, trip_date, service_type, COALESCE(TRIM(time_block), '')
                    HAVING MAX(COALESCE(line_no,0)) > 0
                )
                SELECT
                    COALESCE(cu.title, '') AS firma,
                    (COALESCE(rp.route_name, '') || CASE WHEN COALESCE(rp.stops,'') <> '' THEN (' | ' || COALESCE(rp.stops,'')) ELSE '' END) AS guzergah,
                    COALESCE(v.arac_sahibi, COALESCE(e.ad_soyad, CAST(ta.driver_id AS TEXT), ''), '') AS sahis,
                    COALESCE(v.plate_number, '') AS plaka,
                    COALESCE(rp.movement_type, '') AS hareket,
                    SUM(CASE WHEN COALESCE(sg.has_split,0)=1 THEN (COALESCE(ta.qty,0) / 2.0) ELSE COALESCE(ta.qty,0) END) AS qty_sum,
                    MAX(COALESCE(ta.trip_date, '')) AS last_trip_date,
                    rp.id AS route_params_id,
                    ta.contract_id AS contract_id,
                    COALESCE(ta.service_type,'') AS service_type
                FROM eff ta
                LEFT JOIN split_groups sg
                  ON sg.contract_id = ta.contract_id
                 AND sg.route_params_id = ta.route_params_id
                 AND sg.trip_date = ta.trip_date
                 AND sg.service_type = ta.service_type
                 AND sg.time_block = COALESCE(TRIM(ta.time_block), '')
                LEFT JOIN route_params rp ON rp.id = ta.route_params_id
                LEFT JOIN vehicles v ON (v.id = ta.vehicle_id OR v.vehicle_code = CAST(ta.vehicle_id AS TEXT))
                LEFT JOIN employees e ON (
                    TRIM(COALESCE(e.personel_kodu,'')) = TRIM(CAST(ta.driver_id AS TEXT))
                    OR LTRIM(TRIM(COALESCE(e.personel_kodu,'')), '0') = LTRIM(TRIM(CAST(ta.driver_id AS TEXT)), '0')
                )
                LEFT JOIN contracts co ON co.id = ta.contract_id
                LEFT JOIN customers cu ON cu.id = co.customer_id
                WHERE ta.trip_date BETWEEN ? AND ?
                  AND (
                        (
                            v.id IS NOT NULL
                            AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(v.arac_sahibi,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%ASIL%'
                            AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(v.arac_sahibi,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%TUR%'
                        )
                        OR (
                            v.id IS NULL
                            AND COALESCE(e.ad_soyad, CAST(ta.driver_id AS TEXT), '') <> ''
                            AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(e.ad_soyad,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%ASIL%'
                            AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(e.ad_soyad,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%TUR%'
                        )
                  )
                  AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(rp.movement_type,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') NOT LIKE '%CENAZE%'
                  {customer_filter_sql}
                GROUP BY
                    COALESCE(cu.title, ''),
                    (COALESCE(rp.route_name, '') || CASE WHEN COALESCE(rp.stops,'') <> '' THEN (' | ' || COALESCE(rp.stops,'')) ELSE '' END),
                    COALESCE(v.arac_sahibi, COALESCE(e.ad_soyad, CAST(ta.driver_id AS TEXT), ''), ''),
                    COALESCE(v.plate_number, ''),
                    COALESCE(rp.movement_type, ''),
                    rp.id,
                    ta.contract_id,
                    COALESCE(ta.service_type,'')
                ORDER BY firma, guzergah, plaka
                """,
                tuple(params),
            )
            grouped = cur.fetchall() or []
        finally:
            try:
                conn.close()
            except Exception:
                pass

        out_rows = []
        price_cache: dict[tuple[int, str, str, int, str], float] = {}

        for (
            firma,
            guzergah,
            sahis,
            plaka,
            hareket,
            qty_sum,
            last_trip_date,
            route_params_id,
            contract_id,
            service_type,
        ) in grouped:
            try:
                rid = int(route_params_id or 0)
            except Exception:
                rid = 0
            if rid <= 0:
                continue

            try:
                cid = int(contract_id or 0)
            except Exception:
                cid = 0
            if cid <= 0:
                continue

            st = str(service_type or "").strip()

            try:
                qty_f = float(qty_sum or 0.0)
            except Exception:
                qty_f = 0.0
            if qty_f <= 0:
                continue

            unit_price = 0.0
            if st:
                pc = self._pricing_category_from_movement_type(str(hareket or ""))
                d_for_price = str(last_trip_date or "").strip() or str(end_date)
                key = (rid, pc, d_for_price, cid, st)
                if key in price_cache:
                    unit_price = float(price_cache.get(key) or 0.0)
                else:
                    unit_price = 0.0
                    try:
                        pr = self.get_trip_price_for_date(
                            contract_id=int(cid),
                            service_type=str(st),
                            route_params_id=int(rid),
                            pricing_category=str(pc),
                            trip_date=str(d_for_price),
                        )
                        if pr:
                            unit_price = float(pr[0] or 0.0)
                    except Exception:
                        unit_price = 0.0
                    price_cache[key] = float(unit_price or 0.0)

            total = float(qty_f * float(unit_price or 0.0))
            kdv = float(total * 0.20)
            ara_top = float(total + kdv)
            tevkifat = float(kdv * 0.50)
            g_toplam = float(ara_top - tevkifat)

            out_rows.append(
                (
                    str(firma or ""),
                    str(guzergah or ""),
                    str(sahis or ""),
                    str(plaka or ""),
                    str(hareket or ""),
                    qty_f,
                    float(unit_price or 0.0),
                    total,
                    kdv,
                    ara_top,
                    tevkifat,
                    g_toplam,
                )
            )

        return out_rows

    def get_hakedis_tab2_sirket_araclari_rows(
        self,
        contract_id: int,
        period: str,
        service_type: str,
        customer_id: int | None = None,
        require_locked: bool = True,
    ):
        """Return Tablo-2 rows (ŞİRKET ARAÇLARI) for a given month.

        Output columns (in order):
        - GÜZERGAH, ŞAHIS(arac_sahibi), PLAKA, HAREKET(movement_type), GÜN(qty sum),
          TUTAR(unit price), TOPLAM, KDV, ARA TOP, TEVKIFAT, G TOPLAM

        Rules:
        - Only company vehicles (NOT 'TAŞERON ARACI' variations)
        - Only locked/onaylı periods when require_locked=True (trip_period_lock.locked=1)
        - movement_type is taken from route_params.movement_type
        - pricing_category is derived from movement_type and used to resolve trip_prices.price
        - KDV = TOPLAM * 0.20
        - TEVKIFAT = KDV * 0.50
        - G TOPLAM = (TOPLAM + KDV) - TEVKIFAT
        """

        if not contract_id or not period or not service_type:
            return []

        month = str(period).strip()[:7]
        if len(month) != 7 or month[4] != "-":
            return []

        if require_locked:
            st = self.get_trip_period_lock(int(contract_id), str(month), str(service_type)) or {}
            if not bool(st.get("locked")):
                return []

        try:
            d0 = datetime.strptime(month + "-01", "%Y-%m-%d")
        except Exception:
            return []
        if d0.month == 12:
            d1 = datetime(d0.year + 1, 1, 1)
        else:
            d1 = datetime(d0.year, d0.month + 1, 1)
        start_date = d0.strftime("%Y-%m-%d")
        end_date = (d1 - timedelta(days=1)).strftime("%Y-%m-%d")

        self.create_employees_table()

        conn = self.connect()
        if not conn:
            return []
        try:
            cur = conn.cursor()
            params: list[object] = [
                int(contract_id),
                str(service_type),
                str(start_date),
                str(end_date),
                int(contract_id),
                str(service_type),
                str(start_date),
                str(end_date),
            ]
            customer_filter_sql = ""
            if customer_id is not None:
                customer_filter_sql = " AND cu.id = ? "
                params.append(int(customer_id))

            cur.execute(
                f"""
                WITH split_groups AS (
                    SELECT
                        contract_id,
                        route_params_id,
                        trip_date,
                        service_type,
                        COALESCE(TRIM(time_block), '') AS time_block,
                        1 AS has_split
                    FROM trip_entries
                    WHERE contract_id = ?
                      AND service_type = ?
                      AND trip_date BETWEEN ? AND ?
                    GROUP BY contract_id, route_params_id, trip_date, service_type, COALESCE(TRIM(time_block), '')
                    HAVING MAX(COALESCE(line_no,0)) > 0
                )
                SELECT
                    COALESCE(cu.title, '') AS firma,
                    (COALESCE(rp.route_name, '') || CASE WHEN COALESCE(rp.stops,'') <> '' THEN (' | ' || COALESCE(rp.stops,'')) ELSE '' END) AS guzergah,
                    COALESCE(v.arac_sahibi, COALESCE(e.ad_soyad,''), '') AS sahis,
                    COALESCE(v.plate_number, '') AS plaka,
                    COALESCE(rp.movement_type, '') AS hareket,
                    SUM(CASE WHEN COALESCE(sg.has_split,0)=1 THEN (COALESCE(ta.qty,0) / 2.0) ELSE COALESCE(ta.qty,0) END) AS qty_sum,
                    MAX(COALESCE(ta.trip_date, '')) AS last_trip_date,
                    rp.id AS route_params_id
                FROM trip_allocations ta
                LEFT JOIN split_groups sg
                  ON sg.contract_id = ta.contract_id
                 AND sg.route_params_id = ta.route_params_id
                 AND sg.trip_date = ta.trip_date
                 AND sg.service_type = ta.service_type
                 AND sg.time_block = COALESCE(TRIM(ta.time_block), '')
                LEFT JOIN route_params rp ON rp.id = ta.route_params_id
                LEFT JOIN vehicles v ON (v.id = ta.vehicle_id OR v.vehicle_code = CAST(ta.vehicle_id AS TEXT))
                LEFT JOIN employees e ON e.personel_kodu = CAST(ta.driver_id AS TEXT)
                LEFT JOIN contracts co ON co.id = ta.contract_id
                LEFT JOIN customers cu ON cu.id = co.customer_id
                WHERE ta.contract_id = ?
                  AND ta.service_type = ?
                  AND ta.trip_date BETWEEN ? AND ?
                  AND (
                        (
                            v.id IS NOT NULL
                            AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(v.arac_sahibi,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%ASIL%'
                            AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(v.arac_sahibi,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%TUR%'
                        )
                        OR (
                            v.id IS NULL
                            AND COALESCE(e.ad_soyad,'') <> ''
                            AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(e.ad_soyad,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%ASIL%'
                            AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(e.ad_soyad,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') LIKE '%TUR%'
                        )
                  )
                  AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(COALESCE(rp.movement_type,'')),'Ş','S'),'İ','I'),'Ğ','G'),'Ü','U'),'Ö','O'),'Ç','C') NOT LIKE '%CENAZE%'
                  {customer_filter_sql}
                GROUP BY
                    COALESCE(cu.title, ''),
                    (COALESCE(rp.route_name, '') || CASE WHEN COALESCE(rp.stops,'') <> '' THEN (' | ' || COALESCE(rp.stops,'')) ELSE '' END),
                    COALESCE(v.arac_sahibi, COALESCE(e.ad_soyad,''), ''),
                    COALESCE(v.plate_number, ''),
                    COALESCE(rp.movement_type, ''),
                    rp.id
                ORDER BY firma, guzergah, plaka
                """,
                tuple(params),
            )
            grouped = cur.fetchall() or []
        finally:
            try:
                conn.close()
            except Exception:
                pass

        out_rows = []
        price_cache: dict[tuple[int, str, str], float] = {}

        for firma, guzergah, sahis, plaka, hareket, qty_sum, last_trip_date, route_params_id in grouped:
            try:
                rid = int(route_params_id or 0)
            except Exception:
                rid = 0
            if rid <= 0:
                continue

            try:
                qty_f = float(qty_sum or 0.0)
            except Exception:
                qty_f = 0.0
            if qty_f <= 0:
                continue

            pc = self._pricing_category_from_movement_type(str(hareket or ""))
            d_for_price = str(last_trip_date or "").strip() or str(end_date)
            key = (rid, pc, d_for_price)
            if key in price_cache:
                unit_price = float(price_cache.get(key) or 0.0)
            else:
                unit_price = 0.0
                try:
                    pr = self.get_trip_price_for_date(
                        contract_id=int(contract_id),
                        service_type=str(service_type),
                        route_params_id=int(rid),
                        pricing_category=str(pc),
                        trip_date=str(d_for_price),
                    )
                    if pr:
                        unit_price = float(pr[0] or 0.0)
                except Exception:
                    unit_price = 0.0
                price_cache[key] = float(unit_price or 0.0)

            total = float(qty_f * float(unit_price or 0.0))
            kdv = float(total * 0.20)
            ara_top = float(total + kdv)
            tevkifat = float(kdv * 0.50)
            g_toplam = float(ara_top - tevkifat)

            out_rows.append(
                (
                    str(firma or ""),
                    str(guzergah or ""),
                    str(sahis or ""),
                    str(plaka or ""),
                    str(hareket or ""),
                    qty_f,
                    float(unit_price or 0.0),
                    total,
                    kdv,
                    ara_top,
                    tevkifat,
                    g_toplam,
                )
            )

        return out_rows

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

    @staticmethod
    def _normalize_price_matrix_movement_type(raw: str) -> tuple[str, str]:
        """Return (pricing_category, movement_type_norm).

        pricing_category: TEK_SERVIS / PAKET / FAZLA_MESAI
        movement_type_norm: tek servis / sabah-akşam / fazla mesai
        """
        s = str(raw or "").strip().lower()
        if "mesai" in s:
            return ("FAZLA_MESAI", "fazla mesai")
        if "paket" in s or (("sabah" in s) and ("akşam" in s or "aksam" in s)):
            return ("PAKET", "sabah-akşam")
        if "cift" in s or "çift" in s:
            return ("CIFT_SERVIS", "cift servis")
        if "tek" in s:
            return ("TEK_SERVIS", "tek servis")
        if s == "teks" or s == "tekservis":
            return ("TEK_SERVIS", "tek servis")
        # Default: treat as TEK_SERVIS but keep whatever free-form text normalized.
        return ("TEK_SERVIS", s)

    def parse_contract_price_matrix_rows(self, price_matrix_json: str, service_type: str | None = None) -> list[dict]:
        """Parse and normalize a price_matrix_json payload.

        Does NOT mutate DB.
        - Ensures each row has 'pricing_category' and 'movement_type_norm'
        - Supports legacy keys and free-form movement texts like 'TEK SERVİS'/'ÇİFT SERVİS'
        - Optional service_type filter using row['_service_type'] or row['service_type']
        """
        try:
            parsed = json.loads(price_matrix_json) if price_matrix_json else []
        except Exception:
            parsed = []
        if not isinstance(parsed, list):
            return []

        out: list[dict] = []
        st_filter = str(service_type or "").strip().lower()

        for rec in parsed:
            if not isinstance(rec, dict):
                continue

            st = str(rec.get("_service_type") or rec.get("service_type") or "").strip().lower()
            if st_filter and st and st != st_filter:
                continue

            # Determine movement source in order of preference.
            raw_mov = (
                rec.get("movement_type_norm")
                or rec.get("pricing_category")
                or rec.get("gidis_gelis")
                or rec.get("movement_type")
                or rec.get("hareket_turu")
                or rec.get("hareket")
                or rec.get("hareketTuru")
                or rec.get("hareket_tipi")
                or rec.get("tip")
                or ""
            )
            cat, mt_norm = self._normalize_price_matrix_movement_type(str(raw_mov))

            # Create a shallow copy and fill canonical fields.
            rr = dict(rec)
            if not str(rr.get("pricing_category") or "").strip():
                rr["pricing_category"] = cat
            if not str(rr.get("movement_type_norm") or "").strip():
                rr["movement_type_norm"] = mt_norm

            # Normalize subcontractor price legacy key.
            if rr.get("alt_yuklenici_fiyat") is None and rr.get("ay_fiyati") is not None:
                rr["alt_yuklenici_fiyat"] = rr.get("ay_fiyati")

            out.append(rr)

        return out

    def get_contract_price_matrix_rows(self, contract_id: int, service_type: str | None = None) -> list[dict]:
        raw = self.get_contract_price_matrix_json(int(contract_id))
        return self.parse_contract_price_matrix_rows(raw, service_type=service_type)

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
            try:
                if isinstance(data, dict) and "contract_number" in data:
                    data["contract_number"] = str(data.get("contract_number") or "").strip()
            except Exception:
                pass
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
                "SELECT id, COALESCE(title,'') FROM customers WHERE COALESCE(is_active,1)=1 ORDER BY title COLLATE TRNOCASE"
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
                    vehicle_capacity REAL,
                    note TEXT,
                    sort_order INTEGER,
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
                if "vehicle_capacity" not in cols:
                    cursor.execute("ALTER TABLE route_params ADD COLUMN vehicle_capacity REAL")
                if "note" not in cols:
                    cursor.execute("ALTER TABLE route_params ADD COLUMN note TEXT")
                if "sort_order" not in cols:
                    cursor.execute("ALTER TABLE route_params ADD COLUMN sort_order INTEGER")
            except Exception:
                pass

            try:
                cursor.execute(
                    "SELECT id, contract_id, COALESCE(service_type,'') FROM route_params WHERE sort_order IS NULL ORDER BY contract_id, COALESCE(service_type,''), id"
                )
                rows = cursor.fetchall() or []
                if rows:
                    last_key = None
                    seq = -1
                    for rid, cid, st in rows:
                        key = (int(cid or 0), str(st or "").strip())
                        if key != last_key:
                            last_key = key
                            seq = 0
                        else:
                            seq += 1
                        cursor.execute(
                            "UPDATE route_params SET sort_order = ? WHERE id = ? AND sort_order IS NULL",
                            (int(seq), int(rid)),
                        )
            except Exception:
                pass
            conn.commit()
        finally:
            conn.close()

    def replace_route_params_for_contract(
        self,
        contract_id: int,
        contract_number: str,
        start_date: str,
        end_date: str,
        service_type: str,
        rows: list[dict],
    ) -> bool:
        self._ensure_route_params_table()
        conn = self.connect()
        if not conn:
            return False
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            cur = conn.cursor()
            cur.execute("BEGIN")
            ctx_contract_id = int(contract_id)
            ctx_service_type = str(service_type or "").strip()

            # Keep stable IDs to avoid breaking trip_prices.route_params_id references.
            cur.execute(
                "SELECT id FROM route_params WHERE contract_id=? AND service_type=?",
                (ctx_contract_id, ctx_service_type),
            )
            existing_ids = {int(r[0]) for r in (cur.fetchall() or []) if r and r[0] is not None}
            kept_ids: set[int] = set()

            for r in rows or []:
                route_name = str((r or {}).get("route_name") or "").strip()
                movement_type = str((r or {}).get("movement_type") or "").strip()
                note = str((r or {}).get("note") or "").strip()
                try:
                    sort_order = (r or {}).get("sort_order")
                    sort_order = None if sort_order is None or str(sort_order).strip() == "" else int(sort_order)
                except Exception:
                    sort_order = None
                try:
                    distance_km = float((r or {}).get("distance_km") or 0)
                except Exception:
                    distance_km = 0.0
                try:
                    cap = (r or {}).get("vehicle_capacity")
                    vehicle_capacity = None if cap is None or str(cap).strip() == "" else float(cap)
                except Exception:
                    vehicle_capacity = None

                if not any([route_name, movement_type, distance_km, vehicle_capacity]):
                    continue

                rid = (r or {}).get("id")
                try:
                    rid_int = int(rid) if rid is not None and str(rid).strip() != "" else None
                except Exception:
                    rid_int = None

                if rid_int is not None and rid_int in existing_ids:
                    cur.execute(
                        """
                        UPDATE route_params
                        SET contract_number=?, start_date=?, end_date=?,
                            route_name=?, movement_type=?, stops=?, distance_km=?, vehicle_capacity=?, note=?, sort_order=?
                        WHERE id=? AND contract_id=? AND service_type=?
                        """,
                        (
                            str(contract_number or "").strip(),
                            str(start_date or "").strip(),
                            str(end_date or "").strip(),
                            route_name,
                            movement_type,
                            "",
                            float(distance_km or 0.0),
                            vehicle_capacity,
                            note,
                            sort_order,
                            int(rid_int),
                            ctx_contract_id,
                            ctx_service_type,
                        ),
                    )
                    kept_ids.add(int(rid_int))
                else:
                    cur.execute(
                        """
                        INSERT INTO route_params (
                            contract_id, contract_number, start_date, end_date, service_type,
                            route_name, movement_type, stops, distance_km, vehicle_capacity, note, sort_order, created_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            ctx_contract_id,
                            str(contract_number or "").strip(),
                            str(start_date or "").strip(),
                            str(end_date or "").strip(),
                            ctx_service_type,
                            route_name,
                            movement_type,
                            "",
                            float(distance_km or 0.0),
                            vehicle_capacity,
                            note,
                            sort_order,
                            now,
                        ),
                    )
                    try:
                        kept_ids.add(int(cur.lastrowid))
                    except Exception:
                        pass

            # Delete rows removed from UI (and clean up tariff prices tied to them).
            removed_ids = sorted(existing_ids - kept_ids)
            if removed_ids:
                placeholders = ",".join(["?"] * len(removed_ids))
                try:
                    cur.execute(
                        f"DELETE FROM trip_prices WHERE contract_id=? AND route_params_id IN ({placeholders})",
                        (ctx_contract_id, *removed_ids),
                    )
                except Exception:
                    pass
                cur.execute(
                    f"DELETE FROM route_params WHERE contract_id=? AND service_type=? AND id IN ({placeholders})",
                    (ctx_contract_id, ctx_service_type, *removed_ids),
                )

            conn.commit()
            return True
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"replace_route_params_for_contract error: {e}")
            return False
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
                           COALESCE(movement_type,''),
                           COALESCE(vehicle_capacity,0),
                           COALESCE(note,'')
                    FROM route_params
                    WHERE contract_id = ? AND service_type = ?
                    ORDER BY COALESCE(sort_order, id) ASC, id ASC
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
            num = str(number or "").strip()
            cursor.execute(
                "SELECT id, contract_number FROM contracts WHERE contract_number = ? LIMIT 1",
                (num,),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    "SELECT id, contract_number FROM contracts WHERE TRIM(contract_number) = ? LIMIT 1",
                    (num,),
                )
                row = cursor.fetchone()
            if row is None:
                return False
            contract_id = int(row[0])

            cursor.execute("BEGIN")

            try:
                cursor.execute("DELETE FROM trip_plan WHERE contract_id = ?", (contract_id,))
            except Exception:
                pass
            try:
                cursor.execute("DELETE FROM trip_time_blocks WHERE contract_id = ?", (contract_id,))
            except Exception:
                pass
            try:
                cursor.execute("DELETE FROM trip_period_lock WHERE contract_id = ?", (contract_id,))
            except Exception:
                pass

            try:
                cursor.execute("DELETE FROM trip_prices WHERE contract_id = ?", (contract_id,))
            except Exception:
                pass

            try:
                cursor.execute("DELETE FROM contract_special_items WHERE contract_id = ?", (contract_id,))
            except Exception:
                pass
            try:
                cursor.execute("DELETE FROM bulk_puantaj_manual_rows WHERE contract_id = ?", (contract_id,))
            except Exception:
                pass
            try:
                cursor.execute("DELETE FROM hakedis WHERE contract_id = ?", (contract_id,))
            except Exception:
                pass

            try:
                cursor.execute("DELETE FROM trip_allocations WHERE contract_id = ?", (contract_id,))
            except Exception:
                pass
            try:
                cursor.execute("DELETE FROM trip_entries WHERE contract_id = ?", (contract_id,))
            except Exception:
                pass

            try:
                cursor.execute("DELETE FROM trips WHERE contract_id = ?", (contract_id,))
            except Exception:
                pass

            try:
                cursor.execute("DELETE FROM route_params WHERE contract_id = ?", (contract_id,))
            except Exception:
                pass

            cursor.execute("DELETE FROM contracts WHERE id = ?", (contract_id,))
            conn.commit()
            return True
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
                ("pricing_model", "TEXT DEFAULT 'VARDIYALI'"),
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
                ORDER BY ad_soyad COLLATE TRNOCASE ASC, personel_kodu COLLATE TRNOCASE ASC
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
