import argparse
import os
import shutil
import sys
from datetime import datetime

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.core.db_manager import DatabaseManager
from config import DB_PATH


def _norm(s: str) -> str:
    t = (s or "").strip().lower()
    t = "".join(t.split())
    out = []
    for ch in t:
        # keep alnum + basic TR letters; drop punctuation
        if ch.isalnum() or ch in ("ç", "ğ", "ı", "i", "ö", "ş", "ü"):
            out.append(ch)
    return "".join(out)


def _norm_variants(s: str) -> list[str]:
    base = _norm(s)
    if not base:
        return []
    out = [base]
    # Common legacy suffix/prefix variants in route naming
    if base.endswith("v") and len(base) > 1:
        out.append(base[:-1])
    else:
        out.append(base + "v")
    # De-dup
    uniq: list[str] = []
    seen = set()
    for x in out:
        if x and x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def _is_cift_text(s: str) -> bool:
    t = (s or "").strip().lower()
    return ("cift" in t) or ("çift" in t)


def _pick_expected_full_price(db: DatabaseManager, contract_id: int, service_type: str, route_name: str) -> float | None:
    """Resolve expected FULL unit price for a route from contract price matrix.

    Strategy:
    - Prefer an explicit 'ÇİFT' row if present (many contracts store 2250 directly).
    - Otherwise fall back to 'TEK' row * 2.
    - If neither can be reliably identified, fall back to minimum positive matching price.
    """
    # NOTE: In real data, price_matrix rows may have missing/inconsistent service_type.
    # To avoid filtering everything out, load without service_type filter and match by route_name.
    rows = []
    try:
        rows = db.get_contract_price_matrix_rows(int(contract_id), service_type=None)
    except Exception:
        rows = []

    def _extract_route_text(rec: dict) -> str:
        # Contract price matrix has many legacy schemas; try multiple keys.
        # Keep this tolerant: return first non-empty string-like value.
        keys = (
            "guzergah",
            "güzergah",
            "guz",
            "route",
            "route_name",
            "hat",
            "hat_adi",
            "is_kalemi",
            "iş_kalemi",
            "kalem",
            "kalem_adi",
            "is",
            "isim",
            "name",
        )
        for k in keys:
            try:
                v = rec.get(k)
            except Exception:
                v = None
            if v is None:
                continue
            vs = str(v).strip()
            if vs:
                return vs
        # last resort: scan values
        try:
            for v in (rec or {}).values():
                if v is None:
                    continue
                vs = str(v).strip()
                if vs and len(vs) <= 80:
                    return vs
        except Exception:
            pass
        return ""

    rn_variants = _norm_variants(route_name)
    if not rn_variants:
        return None

    def _rec_mov_text(r: dict) -> str:
        try:
            return str(
                # Prefer raw/original fields; normalized field can erase 'çift' (it is mapped to 'tek servis').
                r.get("gidis_gelis")
                or r.get("movement_type")
                or r.get("hareket_turu")
                or r.get("hareket")
                or r.get("tip")
                or r.get("movement_type_norm")
                or ""
            ).strip().lower()
        except Exception:
            return ""

    # Build candidate prices for matching guzergah values.
    # Matching strategy:
    # - exact match on normalized variants
    # - substring match (to tolerate small naming differences)
    prices_any: list[float] = []
    prices_cift: list[float] = []
    prices_tek: list[float] = []

    for rec in rows or []:
        try:
            guz = _extract_route_text(rec) or ""
        except Exception:
            guz = ""
        guz_norm = _norm(str(guz))
        if not guz_norm:
            continue
        is_match = False
        for rv in rn_variants:
            if guz_norm == rv:
                is_match = True
                break
            # substring match in either direction to tolerate extra tokens
            if rv in guz_norm or guz_norm in rv:
                is_match = True
                break
        if not is_match:
            continue

        try:
            pr = float(rec.get("fiyat") or rec.get("price") or 0.0)
        except Exception:
            pr = 0.0
        if pr > 0:
            prices_any.append(pr)
            mv = _rec_mov_text(rec)
            if _is_cift_text(mv):
                prices_cift.append(pr)
            elif "tek" in mv:
                prices_tek.append(pr)

    # Prefer explicit ÇİFT if we can detect it.
    if prices_cift:
        return float(min(prices_cift))
    # Otherwise, TEK*2 if we can detect TEK rows.
    if prices_tek:
        return float(min(prices_tek)) * 2.0

    if not prices_any:
        return None

    # Last resort: treat the MAX matching price as FULL.
    # Many contracts store both TEK and ÇİFT; max tends to represent ÇİFT full.
    return float(max(prices_any))


def _looks_like_pow2_ratio(a: float, b: float, tol: float = 0.02) -> bool:
    """Return True if a/b is close to 2^k (k>=1) within tolerance."""
    if a <= 0 or b <= 0:
        return False

    r = float(a) / float(b)
    k = 1
    while k <= 10:
        target = 2.0**k
        if abs(r - target) <= tol * target:
            return True
        k += 1
    return False


def _month7(s: str) -> str:
    t = str(s or "").strip()
    return t[:7] if len(t) >= 7 else t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="YYYY-MM", default="")
    ap.add_argument("--service-type", help="service_type filter (exact)", default="")
    ap.add_argument("--contract-id", help="contract_id filter", default="")
    ap.add_argument("--apply", action="store_true", help="apply updates (otherwise dry-run)")
    ap.add_argument("--debug", action="store_true", help="print debug info")
    args = ap.parse_args()

    db_path = DB_PATH
    if not os.path.exists(db_path):
        raise SystemExit(f"DB not found: {db_path}")

    # Backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path + f".bak_{ts}"
    shutil.copy2(db_path, backup_path)
    print(f"Backup created: {backup_path}")

    db = DatabaseManager()
    conn = db.connect()
    if not conn:
        raise SystemExit("DB connect failed")

    month_filter = (args.month or "").strip()
    st_filter = (args.service_type or "").strip()
    cid_filter = (args.contract_id or "").strip()

    where_month = ""
    params: list[object] = []

    # Determine split groups from trip_entries + trip_allocations.
    base_sql = """
    WITH split_groups AS (
        SELECT contract_id, service_type, substr(trip_date,1,7) AS month,
               route_params_id, time_block
        FROM trip_entries
        WHERE COALESCE(line_no,0) > 0
        UNION
        SELECT contract_id, service_type, substr(trip_date,1,7) AS month,
               route_params_id, time_block
        FROM trip_allocations
        WHERE COALESCE(line_no,0) > 0
    )
    SELECT sg.contract_id, sg.service_type, sg.month, sg.route_params_id, sg.time_block,
           COALESCE(rp.route_name,''), COALESCE(rp.movement_type,'')
    FROM split_groups sg
    LEFT JOIN route_params rp ON rp.id = sg.route_params_id
    WHERE 1=1
    """

    if month_filter:
        base_sql += " AND sg.month = ?\n"
        params.append(month_filter)
    if st_filter:
        base_sql += " AND sg.service_type = ?\n"
        params.append(st_filter)
    if cid_filter:
        base_sql += " AND sg.contract_id = ?\n"
        params.append(int(cid_filter))

    base_sql += " ORDER BY sg.contract_id, sg.service_type, sg.month, sg.route_params_id, sg.time_block\n"

    cur = conn.cursor()
    cur.execute(base_sql, params)
    groups = cur.fetchall() or []

    # Fetch current trip_prices into map for quick lookup.
    cur.execute("SELECT contract_id, month, service_type, route_params_id, time_block, price FROM trip_prices")
    # key uses YYYY-MM for month to be resilient to legacy month formats.
    price_map: dict[tuple[int, str, str, int, str], tuple[float, str]] = {}
    for c_id, mo, st, rid, tb, pr in cur.fetchall() or []:
        try:
            mo_raw = str(mo or "")
            price_map[(int(c_id), _month7(mo_raw), str(st), int(rid), str(tb))] = (float(pr or 0.0), mo_raw)
        except Exception:
            mo_raw = str(mo or "")
            price_map[(int(c_id), _month7(mo_raw), str(st), int(rid), str(tb))] = (0.0, mo_raw)

    planned: list[tuple[float, float, tuple[int, str, str, int, str, str]]] = []
    dbg_total = 0
    dbg_has_price = 0
    dbg_has_expected = 0
    dbg_pow2 = 0
    dbg_less_or_equal = 0
    dbg_no_price = 0
    dbg_no_expected = 0
    dbg_samples: list[str] = []
    for c_id, st, mo, rid, tb, rname, mt in groups:
        dbg_total += 1
        try:
            c_id_i = int(c_id)
            rid_i = int(rid)
        except Exception:
            continue
        st_s = str(st or "")
        mo_s = str(mo or "")
        tb_s = str(tb or "")

        # Split-groups are already filtered by line_no>0; do not require route_params.movement_type to contain ÇİFT.

        k0 = (c_id_i, _month7(mo_s), st_s, rid_i, tb_s)
        pr_rec = price_map.get(k0)
        current = float(pr_rec[0]) if pr_rec else 0.0
        month_raw = str(pr_rec[1]) if pr_rec else str(mo_s)
        if current <= 0:
            dbg_no_price += 1
            if args.debug and len(dbg_samples) < 10:
                dbg_samples.append(f"skip(no_price): cid={c_id_i} mo={mo_s} st={st_s} rid={rid_i} tb={tb_s}")
            continue
        dbg_has_price += 1

        expected = _pick_expected_full_price(db, c_id_i, st_s, str(rname or ""))
        if expected is None or expected <= 0:
            dbg_no_expected += 1
            if args.debug and len(dbg_samples) < 10:
                dbg_samples.append(f"skip(no_expected): cid={c_id_i} mo={mo_s} st={st_s} rid={rid_i} name={str(rname or '')[:40]}")
            continue
        dbg_has_expected += 1

        # Only reduce when it looks like it was multiplied by 2^k.
        if current <= expected * 1.01:
            dbg_less_or_equal += 1
            continue
        if not _looks_like_pow2_ratio(current, expected):
            dbg_pow2 += 1
            continue

        planned.append((current, float(expected), (c_id_i, month_raw, st_s, rid_i, tb_s, str(rname or ""))))

    if not planned:
        print("No candidate trip_prices rows found for repair.")
        if args.debug:
            print("Debug summary:")
            print(f"  split_groups_total={dbg_total}")
            print(f"  has_trip_price={dbg_has_price}")
            print(f"  no_trip_price={dbg_no_price}")
            print(f"  has_expected={dbg_has_expected}")
            print(f"  no_expected={dbg_no_expected}")
            print(f"  skipped_current_le_expected={dbg_less_or_equal}")
            print(f"  skipped_not_pow2_ratio={dbg_pow2}")
            for s in dbg_samples:
                print(f"  {s}")
        conn.close()
        return

    print("Planned updates (current -> expected):")
    for current, expected, k in planned:
        c_id_i, mo_raw, st_s, rid_i, tb_s, _rn = k
        print(f"  contract_id={c_id_i} month={mo_raw} st={st_s} route_id={rid_i} tb={tb_s}: {current:.2f} -> {expected:.2f}")

    if not args.apply:
        print("Dry-run mode: no updates were applied. Re-run with --apply to write changes.")
        conn.close()
        return

    # Apply updates
    cur.execute("BEGIN")
    try:
        for _current, expected, k in planned:
            c_id_i, mo_raw, st_s, rid_i, tb_s, _rn = k
            cur.execute(
                """
                UPDATE trip_prices
                SET price = ?
                WHERE contract_id=? AND month=? AND service_type=? AND route_params_id=? AND time_block=?
                """,
                (float(expected), int(c_id_i), str(mo_raw), str(st_s), int(rid_i), str(tb_s)),
            )
        conn.commit()
        print(f"Applied {len(planned)} updates.")
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
