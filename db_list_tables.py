import sqlite3
import os
import config


def main() -> None:
    db_path = str(config.DB_PATH)
    print("DB_PATH=", db_path)
    print("Exists=", os.path.exists(db_path))
    if not os.path.exists(db_path):
        return

    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        rows = cur.fetchall() or []
        print("TABLES:")
        for r in rows:
            print(r[0])
    finally:
        try:
            con.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
