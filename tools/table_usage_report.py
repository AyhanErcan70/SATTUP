import os
import re
from pathlib import Path


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        try:
            return p.read_text(encoding="cp1254", errors="ignore")
        except Exception:
            return ""


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    app_dir = repo / "app"

    table_names = [
        "arac_bakim",
        "bulk_puantaj_manual_rows",
        "constants",
        "contract_links",
        "contract_pricing_model_history",
        "contract_special_items",
        "contracts",
        "customers",
        "driver_documents",
        "employees",
        "hakedis",
        "hakedis_deductions",
        "hakedis_docs",
        "hakedis_items",
        "period_close",
        "route_params",
        "trip_allocations",
        "trip_entries",
        "trip_period_lock",
        "trip_plan",
        "trip_prices",
        "trip_time_blocks",
        "trips",
        "users",
        "vehicles",
    ]

    py_files: list[Path] = []
    for root, _dirs, files in os.walk(app_dir):
        for fn in files:
            if fn.endswith(".py"):
                py_files.append(Path(root) / fn)

    by_table: dict[str, dict[str, int]] = {t: {} for t in table_names}

    for p in py_files:
        txt = _read_text(p)
        rel = str(p.relative_to(repo)).replace("\\", "/")
        for t in table_names:
            # word boundary to avoid matching e.g. 'users_window'
            pat = re.compile(r"(?i)(?<![A-Z0-9_])" + re.escape(t) + r"(?![A-Z0-9_])")
            m = pat.findall(txt)
            if m:
                by_table[t][rel] = len(m)

    # Print report
    print("# TABLE USAGE REPORT")
    print(f"repo={repo}")
    print(f"py_files={len(py_files)}")
    print()

    def _bucket(rel_path: str) -> str:
        if rel_path.startswith("app/core/"):
            return "core"
        if rel_path.startswith("app/modules/"):
            return "modules"
        return "other"

    for t in table_names:
        files = by_table.get(t) or {}
        if not files:
            print(f"{t}: <NO REFERENCES IN app/>")
            continue

        # aggregate
        buckets: dict[str, int] = {"core": 0, "modules": 0, "other": 0}
        for rp, cnt in files.items():
            buckets[_bucket(rp)] += cnt

        print(f"{t}: total_refs={sum(files.values())} files={len(files)} core={buckets['core']} modules={buckets['modules']} other={buckets['other']}")
        for rp, cnt in sorted(files.items(), key=lambda x: (-x[1], x[0])):
            print(f"  {cnt:>3}  {rp}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
