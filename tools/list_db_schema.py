import sqlite3
import sys


def main() -> int:
    db = r"c:/Users/ayhan/SATTUP/database/asil_system.db"
    if len(sys.argv) > 1 and str(sys.argv[1]).strip():
        db = str(sys.argv[1]).strip()

    con = sqlite3.connect(db)
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT name, type
            FROM sqlite_master
            WHERE type IN ('table','view')
              AND name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        )
        rows = cur.fetchall() or []
        print(f"DB: {db}")
        print(f"count: {len(rows)}")
        for name, typ in rows:
            print(f"{typ}:{name}")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
