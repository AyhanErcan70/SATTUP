import argparse
import sqlite3


def _month_range(month: str) -> tuple[str, str]:
    m = str(month or "").strip()[:7]
    if len(m) != 7 or m[4] != "-":
        raise ValueError("month must be YYYY-MM")
    return m + "-01", m + "-31"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True, help="YYYY-MM")
    ap.add_argument("--db", default="", help="DB path. If empty, uses config.DB_PATH")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    if args.db:
        import os

        os.environ["SATTUP_DB_PATH"] = str(args.db)

    import config

    db_path = str(args.db or config.DB_PATH)
    start_date, end_date = _month_range(args.month)

    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()

        cur.execute(
            """
            SELECT
                co.id AS contract_id,
                COALESCE(cu.title,'') AS customer_title,
                COALESCE(co.contract_number,'') AS contract_number,
                SUM(CASE WHEN te.id IS NOT NULL THEN 1 ELSE 0 END) AS trip_entries_cnt,
                SUM(CASE WHEN ta.id IS NOT NULL THEN 1 ELSE 0 END) AS trip_allocations_cnt
            FROM contracts co
            LEFT JOIN customers cu ON cu.id = co.customer_id
            LEFT JOIN trip_entries te
              ON te.contract_id = co.id
             AND te.trip_date BETWEEN ? AND ?
            LEFT JOIN trip_allocations ta
              ON ta.contract_id = co.id
             AND ta.trip_date BETWEEN ? AND ?
            GROUP BY co.id, cu.title, co.contract_number
            HAVING trip_entries_cnt > 0 OR trip_allocations_cnt > 0
            ORDER BY trip_entries_cnt DESC, trip_allocations_cnt DESC, co.id ASC
            LIMIT ?
            """,
            (str(start_date), str(end_date), str(start_date), str(end_date), int(args.limit)),
        )

        print(f"DB: {db_path}")
        print(f"Month: {str(args.month).strip()[:7]} | Range: {start_date}..{end_date}")
        print("contract_id\tcustomer\tcontract_no\tentries_cnt\tallocations_cnt")
        for cid, cust, cno, ec, ac in cur.fetchall() or []:
            print(f"{int(cid)}\t{cust}\t{cno}\t{int(ec or 0)}\t{int(ac or 0)}")

    finally:
        try:
            con.close()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
