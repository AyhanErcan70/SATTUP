import argparse
import sqlite3
from collections import defaultdict


def _month_range(month: str) -> tuple[str, str]:
    m = str(month or "").strip()[:7]
    if len(m) != 7 or m[4] != "-":
        raise ValueError("month must be YYYY-MM")
    # good enough for analysis (we only need BETWEEN bounds; rows outside month won't exist)
    return m + "-01", m + "-31"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--contract-id", type=int, required=True)
    ap.add_argument("--month", required=True, help="YYYY-MM")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--route-like", default="", help="Case-insensitive substring filter on route text (route_name | stops) or movement")
    ap.add_argument("--plate-like", default="", help="Case-insensitive substring filter on resolved plate list")
    ap.add_argument("--show-all", action="store_true", help="Show all groups, not only entries vs allocations mismatches")
    args = ap.parse_args()

    start_date, end_date = _month_range(args.month)

    conn = sqlite3.connect(str(args.db))
    cur = conn.cursor()

    # split groups across both sources
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
            (int(args.contract_id), str(start_date), str(end_date)),
        )
        for r in cur.fetchall() or []:
            split.add(tuple(r))

    def _k(cid, rid, d, st, tb):
        return (int(cid), int(rid), str(d), str(st), str(tb or ""))

    # aggregate entries
    entries = defaultdict(lambda: {"qty": 0.0, "adj": 0.0})
    cur.execute(
        """
        SELECT contract_id, route_params_id, trip_date, service_type,
               COALESCE(TRIM(time_block), '') AS time_block,
               COALESCE(qty,0)
        FROM trip_entries
        WHERE contract_id = ?
          AND trip_date BETWEEN ? AND ?
        """,
        (int(args.contract_id), str(start_date), str(end_date)),
    )
    for cid, rid, d, st, tb, qty in cur.fetchall() or []:
        key = _k(cid, rid, d, st, tb)
        q = float(qty or 0)
        entries[key]["qty"] += q
        entries[key]["adj"] += (q / 2.0) if key in split else q

    # aggregate allocations
    allocs = defaultdict(lambda: {"qty": 0.0, "adj": 0.0, "veh": set(), "drv": set()})
    cur.execute(
        """
        SELECT contract_id, route_params_id, trip_date, service_type,
               COALESCE(TRIM(time_block), '') AS time_block,
               COALESCE(qty,0),
               COALESCE(vehicle_id,''),
               COALESCE(driver_id,'')
        FROM trip_allocations
        WHERE contract_id = ?
          AND trip_date BETWEEN ? AND ?
        """,
        (int(args.contract_id), str(start_date), str(end_date)),
    )
    for cid, rid, d, st, tb, qty, veh, drv in cur.fetchall() or []:
        key = _k(cid, rid, d, st, tb)
        q = float(qty or 0)
        allocs[key]["qty"] += q
        allocs[key]["adj"] += (q / 2.0) if key in split else q
        v = str(veh or "").strip()
        dr = str(drv or "").strip()
        if v:
            allocs[key]["veh"].add(v)
        if dr:
            allocs[key]["drv"].add(dr)

    # helper maps
    cur.execute(
        "SELECT id, COALESCE(route_name,''), COALESCE(stops,''), COALESCE(movement_type,'') FROM route_params"
    )
    route_map = {int(r[0]): (str(r[1] or ""), str(r[2] or ""), str(r[3] or "")) for r in (cur.fetchall() or []) if r and r[0] is not None}

    cur.execute(
        "SELECT id, COALESCE(vehicle_code,''), COALESCE(plate_number,''), COALESCE(arac_sahibi,''), COALESCE(arac_turu,'') FROM vehicles"
    )
    veh_map = {}
    for vid, vcode, plate, owner, vt in cur.fetchall() or []:
        try:
            if vid is not None:
                veh_map[str(int(vid))] = (str(vcode or ""), str(plate or ""), str(owner or ""), str(vt or ""))
        except Exception:
            pass
        if vcode:
            veh_map[str(vcode)] = (str(vcode or ""), str(plate or ""), str(owner or ""), str(vt or ""))

    keys = set(entries.keys()) | set(allocs.keys())
    out = []
    for key in keys:
        e = entries.get(key, {"qty": 0.0, "adj": 0.0})
        a = allocs.get(key, {"qty": 0.0, "adj": 0.0, "veh": set(), "drv": set()})
        if (not args.show_all) and abs(float(e["qty"]) - float(a["qty"])) < 1e-9 and abs(float(e["adj"]) - float(a["adj"])) < 1e-9:
            continue

        _cid, rid, d, st, tb = key
        rn, stops, mt = route_map.get(int(rid or 0), ("", "", ""))
        route_text = rn + (" | " + stops if stops else "")

        vehs = sorted(a.get("veh") or [])
        plates = []
        for v in vehs[:3]:
            vcode, plate, owner, vt = veh_map.get(v, ("", "", "", ""))
            if plate:
                owner_s = str(owner or "").strip()
                vt_s = str(vt or "").strip()
                vcode_s = str(vcode or "").strip()
                meta = str(plate)
                if vcode_s or owner_s or vt_s:
                    meta += f" [{vcode_s} | {owner_s} | {vt_s}]"
                plates.append(meta)
        if len(vehs) > 3:
            plates.append("...")
        out.append(
            (
                d,
                int(rid or 0),
                mt,
                tb,
                st,
                float(e["qty"]),
                float(e["adj"]),
                float(a["qty"]),
                float(a["adj"]),
                "YES" if key in split else "",
                route_text,
                ",".join(plates),
            )
        )

    out.sort(key=lambda r: (r[0], r[1], r[3], r[4]))

    route_like = str(args.route_like or "").strip().lower()
    plate_like = str(args.plate_like or "").strip().lower()
    if route_like or plate_like:
        filtered = []
        for r in out:
            # r: (date, route_id, movement, time_block, service, ..., route_text, plates)
            movement = str(r[2] or "")
            route_text = str(r[10] or "")
            plates = str(r[11] or "")
            if route_like:
                hay = (route_text + " " + movement).lower()
                if route_like not in hay:
                    continue
            if plate_like:
                if plate_like not in plates.lower():
                    continue
            filtered.append(r)
        out = filtered

    sums = defaultdict(lambda: {"entries_adj": 0.0, "alloc_adj": 0.0, "groups": 0})
    for r in out:
        mt = str(r[2] or "")
        sums[mt]["entries_adj"] += float(r[6] or 0.0)
        sums[mt]["alloc_adj"] += float(r[8] or 0.0)
        sums[mt]["groups"] += 1

    print(f"DB: {args.db}")
    print(f"contract_id (contracts.id): {int(args.contract_id)} | month: {args.month}")
    print(f"Split groups detected (entries or allocations): {len(split)}")
    if route_like or plate_like:
        print(f"Filters: route_like='{args.route_like}' plate_like='{args.plate_like}' show_all={bool(args.show_all)}")

    if sums:
        print("\nSUMMARY (sum of *_adj by movement):")
        print("movement\tgroups\tentries_adj_sum\talloc_adj_sum\tdelta(alloc-entries)")
        for mt in sorted(sums.keys()):
            rec = sums[mt]
            ea = float(rec["entries_adj"])
            aa = float(rec["alloc_adj"])
            print(f"{mt}\t{int(rec['groups'])}\t{ea:.3f}\t{aa:.3f}\t{(aa-ea):.3f}")

    print(
        "trip_date\troute_id\tmovement\ttime_block\tservice\tentries_qty\tentries_adj\talloc_qty\talloc_adj\tsplit\troute\tplates(vehicle_code|owner|type)"
    )
    for r in out[: int(args.limit)]:
        print("\t".join(str(x) for x in r))
    print(f"Total diff groups: {len(out)}")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
