import argparse
import os
import sys
import sqlite3
from datetime import datetime
from collections import defaultdict


_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _backup_db_file(db_path: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{db_path}.{ts}.bak"
    with open(db_path, "rb") as rf:
        data = rf.read()
    with open(bak, "wb") as wf:
        wf.write(data)
    return bak


def _month_range(month: str) -> tuple[str, str]:
    m = str(month or "").strip()[:7]
    if len(m) != 7 or m[4] != "-":
        raise ValueError("month must be YYYY-MM")
    return m + "-01", m + "-31"


def _fmt_money(v: object) -> str:
    try:
        x = float(v or 0)
    except Exception:
        x = 0.0
    s = f"{x:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _sum_cols(rows: list[tuple], idxs: list[int]) -> list[float]:
    out = [0.0 for _ in idxs]
    for r in rows or []:
        for i, col in enumerate(idxs):
            try:
                out[i] += float(r[col] or 0.0)
            except Exception:
                pass
    return out


def _check_entries_vs_allocations(db_path: str, contract_id: int, month: str) -> dict:
    start_date, end_date = _month_range(month)

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    split = set()
    for table in ("trip_entries", "trip_allocations"):
        cur.execute(
            f"""
            SELECT contract_id, route_params_id, trip_date, service_type,
                   COALESCE(TRIM(time_block), '') AS time_block
            FROM {table}
            WHERE contract_id = ?
              AND trip_date BETWEEN ? AND ?
            GROUP BY contract_id, route_params_id, trip_date, service_type, COALESCE(TRIM(time_block), '')
            HAVING MAX(COALESCE(line_no,0)) > 0
            """,
            (int(contract_id), str(start_date), str(end_date)),
        )
        for r in cur.fetchall() or []:
            split.add(tuple(r))

    def _k(cid, rid, d, st, tb):
        return (int(cid), int(rid), str(d), str(st), str(tb or ""))

    entries = defaultdict(float)
    allocs = defaultdict(float)

    cur.execute(
        """
        SELECT contract_id, route_params_id, trip_date, service_type,
               COALESCE(TRIM(time_block), '') AS time_block,
               COALESCE(qty,0)
        FROM trip_entries
        WHERE contract_id = ?
          AND trip_date BETWEEN ? AND ?
        """,
        (int(contract_id), str(start_date), str(end_date)),
    )
    for cid, rid, d, st, tb, qty in cur.fetchall() or []:
        key = _k(cid, rid, d, st, tb)
        q = float(qty or 0)
        entries[key] += (q / 2.0) if (cid, rid, d, st, tb) in split else q

    cur.execute(
        """
        SELECT contract_id, route_params_id, trip_date, service_type,
               COALESCE(TRIM(time_block), '') AS time_block,
               COALESCE(qty,0)
        FROM trip_allocations
        WHERE contract_id = ?
          AND trip_date BETWEEN ? AND ?
        """,
        (int(contract_id), str(start_date), str(end_date)),
    )
    for cid, rid, d, st, tb, qty in cur.fetchall() or []:
        key = _k(cid, rid, d, st, tb)
        q = float(qty or 0)
        allocs[key] += (q / 2.0) if (cid, rid, d, st, tb) in split else q

    keys = set(entries.keys()) | set(allocs.keys())
    mismatches = 0
    for k in keys:
        if abs(float(entries.get(k, 0.0)) - float(allocs.get(k, 0.0))) > 1e-9:
            mismatches += 1

    conn.close()
    return {"groups": len(keys), "mismatches": mismatches, "split_groups": len(split)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True, help="YYYY-MM")
    ap.add_argument("--db", default="", help="DB path. If empty, uses config.DB_PATH")
    ap.add_argument("--customer-id", type=int, default=0)
    ap.add_argument("--contract-id", type=int, default=0, help="Optional deep check (entries vs allocations)")
    ap.add_argument(
        "--fix-orphan-plan",
        action="store_true",
        help="Delete trip_plan rows for the selected month that reference missing route_params. Use with care.",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply DB changes (required for any fix mode). Without this flag, fix modes run in dry-run.",
    )
    ap.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a .bak backup before applying DB changes (not recommended).",
    )
    args = ap.parse_args()

    if args.db:
        os.environ["SATTUP_DB_PATH"] = str(args.db)

    import config
    from app.core.db_manager import DatabaseManager

    db_path = str(args.db or config.DB_PATH)
    db = DatabaseManager()

    print(f"DB: {db_path}")
    print(f"Period: {str(args.month).strip()[:7]}")

    month = str(args.month).strip()[:7]

    template_ok = bool(db.month_has_operational_template(month))
    close_state = db.get_period_close(month) or {}
    is_closed = bool(int((close_state or {}).get("closed") or 0))

    print(f"Operational template exists: {template_ok}")
    print(f"Period closed: {is_closed} | note: {str((close_state or {}).get('note') or '')}")

    conn = db.connect()
    if not conn:
        print("ERROR: Cannot connect to DB")
        return 2

    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT COUNT(1)
            FROM trip_period_lock
            WHERE month = ? AND COALESCE(locked,0) = 0
            """,
            (str(month),),
        )
        unlocked_cnt = int((cur.fetchone() or [0])[0] or 0)
        print(f"Unlocked trip_period_lock rows (should be 0 if period completed): {unlocked_cnt}")

        cur.execute(
            """
            SELECT COUNT(1)
            FROM hakedis
            WHERE period = ?
              AND UPPER(COALESCE(status,'')) NOT IN ('ONAYLANDI','FATURALANDI')
            """,
            (str(month),),
        )
        pending_hakedis_cnt = int((cur.fetchone() or [0])[0] or 0)
        print(f"Pending hakedis rows (not approved/invoiced): {pending_hakedis_cnt}")

        cur.execute(
            """
            SELECT COUNT(1)
            FROM trip_plan tp
            LEFT JOIN route_params rp ON rp.id = tp.route_params_id
            WHERE tp.month = ? AND rp.id IS NULL
            """,
            (str(month),),
        )
        orphan_plan = int((cur.fetchone() or [0])[0] or 0)
        print(f"Orphan trip_plan rows for month (missing route_params): {orphan_plan}")

        if orphan_plan > 0:
            cur.execute(
                """
                SELECT tp.contract_id, tp.route_params_id, tp.service_type, tp.time_block
                FROM trip_plan tp
                LEFT JOIN route_params rp ON rp.id = tp.route_params_id
                WHERE tp.month = ? AND rp.id IS NULL
                ORDER BY tp.contract_id, tp.route_params_id, tp.service_type, tp.time_block
                LIMIT 30
                """,
                (str(month),),
            )
            rows = cur.fetchall() or []
            print("Orphan trip_plan sample (up to 30):")
            for r in rows:
                try:
                    cid, rid, st, tb = r
                except Exception:
                    continue
                print(f"  contract_id={cid} route_params_id={rid} service_type='{st}' time_block='{tb}'")

        if bool(args.fix_orphan_plan) and orphan_plan > 0:
            contract_filter_sql = ""
            params = [str(month)]
            if int(args.contract_id or 0) > 0:
                contract_filter_sql = " AND tp.contract_id = ? "
                params.append(int(args.contract_id))

            cur.execute(
                f"""
                SELECT COUNT(1)
                FROM trip_plan tp
                LEFT JOIN route_params rp ON rp.id = tp.route_params_id
                WHERE tp.month = ?
                  AND rp.id IS NULL
                  {contract_filter_sql}
                """,
                tuple(params),
            )
            to_delete = int((cur.fetchone() or [0])[0] or 0)
            if to_delete <= 0:
                print("No orphan trip_plan rows to delete for the given filter.")
            else:
                print(f"Orphan trip_plan rows to delete (filter applied): {to_delete}")

                if not bool(args.apply):
                    print("Dry-run: no DB changes applied. Re-run with --apply to delete.")
                else:
                    if not bool(args.no_backup):
                        try:
                            bak = _backup_db_file(str(db_path))
                            print(f"Backup created: {bak}")
                        except Exception as e:
                            print(f"ERROR: Backup failed: {e}")
                            print("Aborting without changes.")
                            return 3

                    cur.execute(
                        f"""
                        DELETE FROM trip_plan
                        WHERE id IN (
                            SELECT tp.id
                            FROM trip_plan tp
                            LEFT JOIN route_params rp ON rp.id = tp.route_params_id
                            WHERE tp.month = ?
                              AND rp.id IS NULL
                              {contract_filter_sql}
                        )
                        """,
                        tuple(params),
                    )
                    conn.commit()
                    print(f"Deleted orphan trip_plan rows: {int(cur.rowcount or 0)}")

                    cur.execute(
                        f"""
                        SELECT COUNT(1)
                        FROM trip_plan tp
                        LEFT JOIN route_params rp ON rp.id = tp.route_params_id
                        WHERE tp.month = ?
                          AND rp.id IS NULL
                          {contract_filter_sql}
                        """,
                        tuple(params),
                    )
                    orphan_plan = int((cur.fetchone() or [0])[0] or 0)
                    print(f"Orphan trip_plan rows after delete: {orphan_plan}")

        start_date, end_date = _month_range(month)
        cur.execute(
            "SELECT COUNT(1) FROM trip_entries WHERE trip_date BETWEEN ? AND ?",
            (str(start_date), str(end_date)),
        )
        trip_entries_cnt = int((cur.fetchone() or [0])[0] or 0)

        cur.execute(
            "SELECT COUNT(1) FROM trip_allocations WHERE trip_date BETWEEN ? AND ?",
            (str(start_date), str(end_date)),
        )
        trip_alloc_cnt = int((cur.fetchone() or [0])[0] or 0)

        print(f"trip_entries rows in month: {trip_entries_cnt}")
        print(f"trip_allocations rows in month: {trip_alloc_cnt}")

    finally:
        try:
            conn.close()
        except Exception:
            pass

    cust_id = int(args.customer_id) if int(args.customer_id or 0) > 0 else None

    tab1 = db.get_hakedis_tab1_yuklenici_araclari_rows_all(period=month, customer_id=cust_id)
    tab2 = db.get_hakedis_tab2_sirket_araclari_rows_all(period=month, customer_id=cust_id)

    t1_qty, t1_toplam, t1_kdv, t1_ara, t1_tev, t1_genel = _sum_cols(tab1, [4, 6, 7, 8, 9, 10])
    t2_qty, t2_toplam, t2_kdv, t2_ara, t2_tev, t2_genel = _sum_cols(tab2, [5, 7, 8, 9, 10, 11])

    print("\nHAKEDIS VIEW SUMMARY")
    print(f"Tab1 (YUKLENICI) rows: {len(tab1)} | qty: {t1_qty:.2f} | toplam: {_fmt_money(t1_toplam)} | genel: {_fmt_money(t1_genel)}")
    print(f"Tab2 (SIRKET)    rows: {len(tab2)} | qty: {t2_qty:.2f} | toplam: {_fmt_money(t2_toplam)} | genel: {_fmt_money(t2_genel)}")

    if int(args.contract_id or 0) > 0:
        res = _check_entries_vs_allocations(db_path=db_path, contract_id=int(args.contract_id), month=month)
        print("\nDEEP CHECK (entries vs allocations)")
        print(
            f"groups: {int(res.get('groups') or 0)} | mismatches: {int(res.get('mismatches') or 0)} | split_groups: {int(res.get('split_groups') or 0)}"
        )

    failed = False
    if not template_ok:
        failed = True
    if orphan_plan > 0:
        failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
