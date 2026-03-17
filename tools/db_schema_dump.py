import argparse
import json
import os
import sqlite3
from typing import Any, Dict, List


def _connect_ro(db_path: str) -> sqlite3.Connection:
    # Read-only connection (uri mode). Use absolute path to avoid surprises.
    ap = os.path.abspath(db_path)
    uri = f"file:{ap}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _fetch_tables(cur: sqlite3.Cursor) -> List[str]:
    cur.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    )
    return [r[0] for r in cur.fetchall()]


def _table_info(cur: sqlite3.Cursor, table: str) -> Dict[str, Any]:
    cur.execute(f"PRAGMA table_info('{table}')")
    cols = cur.fetchall()

    cur.execute(f"PRAGMA foreign_key_list('{table}')")
    fks = cur.fetchall()

    cur.execute(f"PRAGMA index_list('{table}')")
    idxs = cur.fetchall()

    idx_out = []
    for (seq, iname, unique, origin, partial) in idxs:
        cur.execute(f"PRAGMA index_info('{iname}')")
        icols = [r[2] for r in cur.fetchall()]
        idx_out.append(
            {
                "name": iname,
                "unique": bool(unique),
                "origin": origin,
                "columns": icols,
                "partial": bool(partial),
            }
        )

    return {
        "columns": [
            {
                "name": c[1],
                "type": c[2],
                "notnull": bool(c[3]),
                "default": c[4],
                "pk": bool(c[5]),
            }
            for c in cols
        ],
        "foreign_keys": [
            {
                "from": fk[3],
                "to_table": fk[2],
                "to_column": fk[4],
                "on_update": fk[5],
                "on_delete": fk[6],
            }
            for fk in fks
        ],
        "indexes": idx_out,
    }


def _to_markdown(schema: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# DB Schema: `{schema.get('db')}`")
    lines.append("")

    tables = schema.get("tables") or {}
    for tname in sorted(tables.keys()):
        t = tables[tname] or {}
        lines.append(f"## TABLE: `{tname}`")
        lines.append("")
        lines.append("### Columns")
        lines.append("")
        cols = t.get("columns") or []
        for c in cols:
            nn = " NOT NULL" if c.get("notnull") else ""
            pk = " PK" if c.get("pk") else ""
            dflt = c.get("default")
            dflt_s = f" DEFAULT {dflt}" if dflt is not None else ""
            lines.append(f"- `{c.get('name')}` {c.get('type')}{nn}{dflt_s}{pk}")
        lines.append("")

        fks = t.get("foreign_keys") or []
        if fks:
            lines.append("### Foreign Keys")
            lines.append("")
            for fk in fks:
                lines.append(
                    f"- `{fk.get('from')}` -> `{fk.get('to_table')}`.`{fk.get('to_column')}` "
                    f"(on_update={fk.get('on_update')}, on_delete={fk.get('on_delete')})"
                )
            lines.append("")

        idxs = t.get("indexes") or []
        if idxs:
            lines.append("### Indexes")
            lines.append("")
            for idx in idxs:
                cols_s = ", ".join([f"`{x}`" for x in (idx.get("columns") or [])])
                uq = " UNIQUE" if idx.get("unique") else ""
                lines.append(f"- `{idx.get('name')}` ({cols_s}){uq} origin={idx.get('origin')}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out-json", default="db_schema.json")
    ap.add_argument("--out-md", default="db_schema.md")
    args = ap.parse_args()

    conn = _connect_ro(args.db)
    try:
        cur = conn.cursor()
        schema: Dict[str, Any] = {"db": os.path.abspath(args.db), "tables": {}}
        for t in _fetch_tables(cur):
            schema["tables"][t] = _table_info(cur, t)

        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump(schema, f, ensure_ascii=False, indent=2)

        with open(args.out_md, "w", encoding="utf-8") as f:
            f.write(_to_markdown(schema))

        print(f"Wrote: {args.out_json}")
        print(f"Wrote: {args.out_md}")
        print(f"Tables: {len(schema['tables'])}")
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
