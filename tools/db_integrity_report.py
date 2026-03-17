import argparse
import os
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass
class Finding:
    title: str
    severity: str  # HIGH/MED/LOW/INFO
    details: List[str]


def _connect_ro(db_path: str) -> sqlite3.Connection:
    ap = os.path.abspath(db_path)
    uri = f"file:{ap}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _table_exists(cur: sqlite3.Cursor, name: str) -> bool:
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    )
    return cur.fetchone() is not None


def _colnames(cur: sqlite3.Cursor, table: str) -> List[str]:
    cur.execute(f"PRAGMA table_info('{table}')")
    return [r[1] for r in cur.fetchall()]


def _q(cur: sqlite3.Cursor, sql: str, params: Tuple = ()) -> List[Tuple]:
    cur.execute(sql, params)
    return cur.fetchall() or []


def _scalar(cur: sqlite3.Cursor, sql: str, params: Tuple = ()) -> int:
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row:
        return 0
    try:
        return int(row[0] or 0)
    except Exception:
        return 0


def _topn(rows: List[Tuple], n: int = 20) -> List[Tuple]:
    return rows[:n]


def _markdown(findings: List[Finding], db_path: str) -> str:
    lines: List[str] = []
    lines.append(f"# DB Integrity Report\n")
    lines.append(f"- **DB**: `{os.path.abspath(db_path)}`")
    lines.append("")
    if not findings:
        lines.append("No findings.")
        return "\n".join(lines) + "\n"

    order = {"HIGH": 0, "MED": 1, "LOW": 2, "INFO": 3}
    findings2 = sorted(findings, key=lambda f: (order.get(f.severity, 9), f.title))

    for f in findings2:
        lines.append(f"## [{f.severity}] {f.title}")
        lines.append("")
        for d in f.details:
            lines.append(f"- {d}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", default="db_integrity_report.md")
    args = ap.parse_args()

    findings: List[Finding] = []

    conn = _connect_ro(args.db)
    try:
        cur = conn.cursor()

        # --- Orphan checks (logical, even if FK not declared) ---
        if _table_exists(cur, "trip_allocations") and _table_exists(cur, "contracts"):
            c = _scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM trip_allocations ta
                LEFT JOIN contracts c ON c.id = ta.contract_id
                WHERE c.id IS NULL
                """,
            )
            if c > 0:
                samples = _topn(
                    _q(
                        cur,
                        """
                        SELECT ta.contract_id, ta.trip_date, ta.service_type
                        FROM trip_allocations ta
                        LEFT JOIN contracts c ON c.id = ta.contract_id
                        WHERE c.id IS NULL
                        ORDER BY ta.trip_date DESC
                        LIMIT 20
                        """,
                    )
                )
                details = [f"Orphan count: **{c}** (trip_allocations.contract_id not in contracts.id)"]
                for r in samples:
                    details.append(f"sample contract_id={r[0]} trip_date={r[1]} service_type={r[2]}")
                findings.append(Finding("Orphan allocations (missing contract)", "HIGH", details))

        if (
            _table_exists(cur, "trip_allocations")
            and _table_exists(cur, "route_params")
            and "route_params_id" in _colnames(cur, "trip_allocations")
        ):
            c = _scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM trip_allocations ta
                LEFT JOIN route_params rp ON rp.id = ta.route_params_id
                WHERE rp.id IS NULL
                """,
            )
            if c > 0:
                samples = _topn(
                    _q(
                        cur,
                        """
                        SELECT ta.route_params_id, ta.contract_id, ta.trip_date, ta.service_type
                        FROM trip_allocations ta
                        LEFT JOIN route_params rp ON rp.id = ta.route_params_id
                        WHERE rp.id IS NULL
                        ORDER BY ta.trip_date DESC
                        LIMIT 20
                        """,
                    )
                )
                details = [f"Orphan count: **{c}** (trip_allocations.route_params_id not in route_params.id)"]
                for r in samples:
                    details.append(
                        f"sample route_params_id={r[0]} contract_id={r[1]} trip_date={r[2]} service_type={r[3]}"
                    )
                findings.append(Finding("Orphan allocations (missing route)", "HIGH", details))

        if _table_exists(cur, "trip_plan") and _table_exists(cur, "contracts"):
            c = _scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM trip_plan tp
                LEFT JOIN contracts c ON c.id = tp.contract_id
                WHERE c.id IS NULL
                """,
            )
            if c > 0:
                findings.append(
                    Finding(
                        "Orphan plan rows (missing contract)",
                        "MED",
                        [f"Orphan count: **{c}** (trip_plan.contract_id not in contracts.id)"],
                    )
                )

        if _table_exists(cur, "trip_plan") and _table_exists(cur, "route_params"):
            c = _scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM trip_plan tp
                LEFT JOIN route_params rp ON rp.id = tp.route_params_id
                WHERE rp.id IS NULL
                """,
            )
            if c > 0:
                findings.append(
                    Finding(
                        "Orphan plan rows (missing route)",
                        "MED",
                        [f"Orphan count: **{c}** (trip_plan.route_params_id not in route_params.id)"],
                    )
                )

        if _table_exists(cur, "hakedis") and _table_exists(cur, "contracts"):
            c = _scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM hakedis h
                LEFT JOIN contracts c ON c.id = h.contract_id
                WHERE c.id IS NULL
                """,
            )
            if c > 0:
                findings.append(
                    Finding(
                        "Orphan hakedis (missing contract)",
                        "HIGH",
                        [f"Orphan count: **{c}** (hakedis.contract_id not in contracts.id)"],
                    )
                )

        # --- Duplicate risk checks (even if unique exists, we ensure none bypassed) ---
        if _table_exists(cur, "trip_allocations"):
            # Unique key exists, but check duplicates anyway
            dup = _q(
                cur,
                """
                SELECT contract_id, route_params_id, trip_date, service_type, time_block, line_no, COUNT(*) as cnt
                FROM trip_allocations
                GROUP BY contract_id, route_params_id, trip_date, service_type, time_block, line_no
                HAVING cnt > 1
                ORDER BY cnt DESC
                LIMIT 20
                """,
            )
            if dup:
                details = [f"Duplicate groups found: **{len(dup)}** (showing up to 20)"]
                for r in dup:
                    details.append(
                        f"contract_id={r[0]} route_params_id={r[1]} date={r[2]} st={r[3]} tb={r[4]} line_no={r[5]} cnt={r[6]}"
                    )
                findings.append(Finding("Duplicate trip_allocations key", "HIGH", details))

        if _table_exists(cur, "trip_entries"):
            dup = _q(
                cur,
                """
                SELECT contract_id, route_params_id, trip_date, service_type, time_block, line_no, COUNT(*) as cnt
                FROM trip_entries
                GROUP BY contract_id, route_params_id, trip_date, service_type, time_block, line_no
                HAVING cnt > 1
                ORDER BY cnt DESC
                LIMIT 20
                """,
            )
            if dup:
                details = [f"Duplicate groups found: **{len(dup)}** (showing up to 20)"]
                for r in dup:
                    details.append(
                        f"contract_id={r[0]} route_params_id={r[1]} date={r[2]} st={r[3]} tb={r[4]} line_no={r[5]} cnt={r[6]}"
                    )
                findings.append(Finding("Duplicate trip_entries key", "HIGH", details))

        # --- service_type normalization report ---
        def _service_type_variants(table: str, col: str = "service_type") -> Optional[Finding]:
            if not _table_exists(cur, table):
                return None
            cols = _colnames(cur, table)
            if col not in cols:
                return None
            rows = _q(
                cur,
                f"SELECT COALESCE({col},''), COUNT(*) FROM {table} GROUP BY COALESCE({col},'') ORDER BY COUNT(*) DESC",
            )
            if not rows:
                return None
            # Highlight suspicious variants
            details = [f"Distinct values: **{len(rows)}**"]
            for v, cnt in _topn(rows, 25):
                details.append(f"{table}.{col}='{v}' -> {cnt}")
            sev = "INFO"
            if len(rows) >= 8:
                sev = "MED"
            return Finding(f"service_type variants in {table}", sev, details)

        for t in ("trip_allocations", "trip_plan", "trip_entries", "trip_prices"):
            f = _service_type_variants(t)
            if f:
                findings.append(f)

        # --- Code existence checks (vehicle_code/personel_kodu) ---
        # In this project, trip_plan / trip_allocations store codes like ARC0015 / PER0003.
        has_emp = _table_exists(cur, "employees")
        has_veh = _table_exists(cur, "vehicles")
        emp_cols = set(_colnames(cur, "employees")) if has_emp else set()
        veh_cols = set(_colnames(cur, "vehicles")) if has_veh else set()

        def _missing_code(table: str, col: str, ref_table: str, ref_col: str, title: str, severity: str):
            if not _table_exists(cur, table) or not _table_exists(cur, ref_table):
                return
            cols = set(_colnames(cur, table))
            if col not in cols:
                return
            # Only check non-empty values.
            cnt = _scalar(
                cur,
                f"""
                SELECT COUNT(*)
                FROM {table} t
                LEFT JOIN {ref_table} r ON r.{ref_col} = t.{col}
                WHERE COALESCE(TRIM(t.{col}), '') <> ''
                  AND r.{ref_col} IS NULL
                """,
            )
            if cnt <= 0:
                return
            samples = _topn(
                _q(
                    cur,
                    f"""
                    SELECT t.{col}, COUNT(*)
                    FROM {table} t
                    LEFT JOIN {ref_table} r ON r.{ref_col} = t.{col}
                    WHERE COALESCE(TRIM(t.{col}), '') <> ''
                      AND r.{ref_col} IS NULL
                    GROUP BY t.{col}
                    ORDER BY COUNT(*) DESC
                    LIMIT 20
                    """,
                )
            )
            details = [f"Missing reference count: **{cnt}** ({table}.{col} not in {ref_table}.{ref_col})"]
            for code, c2 in samples:
                details.append(f"sample {col}='{code}' -> {c2} rows")
            findings.append(Finding(title, severity, details))

        if has_emp and "personel_kodu" in emp_cols:
            _missing_code(
                table="trip_plan",
                col="driver_id",
                ref_table="employees",
                ref_col="personel_kodu",
                title="trip_plan.driver_id codes missing in employees",
                severity="HIGH",
            )
            _missing_code(
                table="trip_allocations",
                col="driver_id",
                ref_table="employees",
                ref_col="personel_kodu",
                title="trip_allocations.driver_id codes missing in employees",
                severity="HIGH",
            )

        if has_veh and "vehicle_code" in veh_cols:
            _missing_code(
                table="trip_plan",
                col="vehicle_id",
                ref_table="vehicles",
                ref_col="vehicle_code",
                title="trip_plan.vehicle_id codes missing in vehicles",
                severity="HIGH",
            )
            _missing_code(
                table="trip_allocations",
                col="vehicle_id",
                ref_table="vehicles",
                ref_col="vehicle_code",
                title="trip_allocations.vehicle_id codes missing in vehicles",
                severity="HIGH",
            )

        # allocations driver/vehicle should be integers; check for unexpected NULLs?
        if _table_exists(cur, "trip_allocations"):
            cnull = _scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM trip_allocations
                WHERE (vehicle_id IS NULL OR vehicle_id = '')
                  AND (driver_id IS NULL OR driver_id = '')
                """,
            )
            if cnull > 0:
                findings.append(
                    Finding(
                        "Allocations with both vehicle_id and driver_id empty",
                        "LOW",
                        [f"Count: **{cnull}** (may be ok for some rows, but review)"],
                    )
                )

        # --- Summary stats ---
        findings.append(
            Finding(
                "Row counts (high level)",
                "INFO",
                [
                    f"trip_plan: {_scalar(cur, 'SELECT COUNT(*) FROM trip_plan') if _table_exists(cur,'trip_plan') else 0}",
                    f"trip_allocations: {_scalar(cur, 'SELECT COUNT(*) FROM trip_allocations') if _table_exists(cur,'trip_allocations') else 0}",
                    f"trip_entries: {_scalar(cur, 'SELECT COUNT(*) FROM trip_entries') if _table_exists(cur,'trip_entries') else 0}",
                    f"hakedis: {_scalar(cur, 'SELECT COUNT(*) FROM hakedis') if _table_exists(cur,'hakedis') else 0}",
                    f"hakedis_items: {_scalar(cur, 'SELECT COUNT(*) FROM hakedis_items') if _table_exists(cur,'hakedis_items') else 0}",
                ],
            )
        )

        md = _markdown(findings, args.db)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(md)

        print(f"Wrote: {os.path.abspath(args.out)}")
        print(f"Findings: {len(findings)}")
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
