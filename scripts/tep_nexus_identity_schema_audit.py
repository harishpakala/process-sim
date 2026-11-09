"""Read-only TimescaleDB observation identity and provenance schema audit.

Inspects PostgreSQL catalogs; never alters schema or reads historian values.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg

SCHEMA = "public"
TABLE = "signal_samples"

COLUMNS_SQL = """
SELECT a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull
FROM pg_attribute a
WHERE a.attrelid = %s::regclass
  AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY a.attnum
"""

CONSTRAINTS_SQL = """
SELECT c.conname, c.contype,
       array_agg(a.attname ORDER BY k.ordinality) AS columns,
       pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint c
JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ordinality)
  ON TRUE
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
WHERE c.conrelid = %s::regclass AND c.contype IN ('p', 'u')
GROUP BY c.oid, c.conname, c.contype
ORDER BY c.contype, c.conname
"""

INDEXES_SQL = """
SELECT i.relname, x.indisunique, x.indisprimary,
       x.indisvalid, x.indisready,
       x.indpred IS NOT NULL AS is_partial,
       x.indexprs IS NOT NULL AS has_expressions,
       pg_get_indexdef(x.indexrelid)
FROM pg_index x
JOIN pg_class i ON i.oid = x.indexrelid
WHERE x.indrelid = %s::regclass
ORDER BY i.relname
"""

def assess(columns, constraints, indexes):
    """Conservative assessment: only declared PK/UNIQUE constraints count as keys."""
    names = {c["name"] for c in columns}
    not_null = {c["name"] for c in columns if c["notNull"]}
    keys = []
    for constraint in constraints:
        if constraint["type"] not in ("PRIMARY KEY", "UNIQUE"):
            continue
        fields = constraint["columns"]
        if not fields or any(f not in names for f in fields):
            continue
        # Nullable UNIQUE columns do not guarantee row identity in PostgreSQL.
        if constraint["type"] == "PRIMARY KEY" or all(f in not_null for f in fields):
            keys.append({"constraint": constraint["name"], "columns": fields,
                         "type": constraint["type"]})
    primary = [k for k in keys if k["type"] == "PRIMARY KEY"]
    return {
        "stableDeclaredRowKey": bool(keys),
        "primaryKeyPresent": bool(primary),
        "candidateKeys": keys,
        "recommendedAction": (
            "REVIEW_SOURCE_BACKED_IDENTITY_DESIGN" if keys else
            "RETAIN_CONTENT_FINGERPRINT_AND_INVESTIGATE_ROW_IDENTITY"
        ),
        "warnings": [
            "Catalog constraints do not establish that row IDs are exported in the current VTKG retrieval.",
            "UNIQUE indexes without constraints and partial/expression indexes are listed but not treated as proven row keys.",
            "Source-row uniqueness does not verify GraphDB physical sensor mapping or shared-run provenance.",
            "No historian row values or duplicate counts were inspected.",
        ],
    }


def inspect(dsn, *, connect=psycopg.connect):
    qualified = f"{SCHEMA}.{TABLE}"
    with connect(dsn) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass(%s)", (qualified,))
                found = cur.fetchone()[0]
                if found is None:
                    raise ValueError(f"Historian table not found: {qualified}")
                cur.execute(COLUMNS_SQL, (qualified,))
                columns = [{"name": name, "dataType": dtype, "notNull": bool(required)}
                           for name, dtype, required in cur.fetchall()]
                cur.execute(CONSTRAINTS_SQL, (qualified,))
                constraints = [
                    {"name": name, "type": "PRIMARY KEY" if kind == "p" else "UNIQUE",
                     "columns": list(fields), "definition": definition}
                    for name, kind, fields, definition in cur.fetchall()
                ]
                cur.execute(INDEXES_SQL, (qualified,))
                indexes = [
                    {"name": name, "unique": bool(unique), "primary": bool(primary),
                     "valid": bool(valid), "ready": bool(ready),
                     "partial": bool(partial), "expressions": bool(expressions),
                     "definition": definition}
                    for name, unique, primary, valid, ready, partial, expressions, definition
                    in cur.fetchall()
                ]
    return {
        "interface": "TEP NEXUS historian identity schema audit v1",
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "source": "PostgreSQL system catalogs",
        "table": qualified,
        "columns": columns, "constraints": constraints, "indexes": indexes,
        "assessment": assess(columns, constraints, indexes),
        "readOnly": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="reports/tep_nexus_identity_schema_audit.json")
    args = parser.parse_args()
    dsn = os.getenv("TEP_TIMESCALE_DSN")
    if not dsn:
        parser.error("TEP_TIMESCALE_DSN is not set")
    result = inspect(dsn)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(path), "table": result["table"],
                      "columns": [x["name"] for x in result["columns"]],
                      "primaryKeyPresent": result["assessment"]["primaryKeyPresent"],
                      "stableDeclaredRowKey": result["assessment"]["stableDeclaredRowKey"],
                      "candidateKeys": result["assessment"]["candidateKeys"],
                      "recommendedAction": result["assessment"]["recommendedAction"]},
                     indent=2))


if __name__ == "__main__":
    main()
