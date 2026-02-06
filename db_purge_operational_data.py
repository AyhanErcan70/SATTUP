import os
import shutil
import sqlite3
from datetime import datetime

import config


KEEP_TABLES = {
    "customers",
    "vehicles",
    "employees",
    "users",
    "driver_documents",
    "arac_bakim",
    "constants",
    "sqlite_sequence",
}

DELETE_TABLES = [
    "hakedis_deductions",
    "hakedis_docs",
    "hakedis_items",
    "hakedis",
    "trip_allocations",
    "trip_entries",
    "trip_plan",
    "trip_prices",
    "trip_time_blocks",
    "trip_period_lock",
    "trips",
    "period_close",
    "route_params",
    "contract_links",
    "contracts",
]


def _list_tables(con: sqlite3.Connection) -> list[str]:
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    rows = cur.fetchall() or []
    return [str(r[0]) for r in rows if r and r[0]]


def _count_rows(con: sqlite3.Connection, table: str) -> int:
    cur = con.cursor()
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        return int((cur.fetchone() or [0])[0] or 0)
    except Exception:
        return -1


def backup_db(db_path: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.{ts}.bak"
    shutil.copy2(db_path, backup_path)
    return backup_path


def purge(db_path: str, vacuum: bool = False) -> None:
    if not os.path.exists(db_path):
        raise FileNotFoundError(db_path)

    con = sqlite3.connect(db_path)
    try:
        existing = set(_list_tables(con))

        missing = [t for t in DELETE_TABLES if t not in existing]
        targets = [t for t in DELETE_TABLES if t in existing]

        print("DB_PATH=", db_path)
        if missing:
            print("Missing delete tables (skipped):", ", ".join(missing))

        print("Will keep tables:")
        for t in sorted([x for x in KEEP_TABLES if x in existing]):
            print("  ", t)

        print("Will delete data from tables:")
        for t in targets:
            print("  ", t, "rows=", _count_rows(con, t))

        con.execute("BEGIN")
        try:
            cur = con.cursor()
            for t in targets:
                cur.execute(f"DELETE FROM {t}")
            con.commit()
        except Exception:
            con.rollback()
            raise

        print("Deleted.")

        if vacuum:
            try:
                con.execute("VACUUM")
                print("VACUUM done.")
            except Exception as e:
                print("VACUUM failed:", e)

        print("After delete row counts:")
        for t in targets:
            print("  ", t, "rows=", _count_rows(con, t))

    finally:
        try:
            con.close()
        except Exception:
            pass


def main() -> None:
    db_path = str(config.DB_PATH)
    print("Exists=", os.path.exists(db_path))
    if not os.path.exists(db_path):
        return

    backup_path = backup_db(db_path)
    print("Backup created:", backup_path)

    purge(db_path, vacuum=False)


if __name__ == "__main__":
    main()
