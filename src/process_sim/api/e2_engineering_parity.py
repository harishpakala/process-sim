"""E2 live engineering parity check: legacy DTWise vs unified planner.

Example:
 python -m process_sim.api.e2_engineering_parity \
   --question "Show DEXPI instrumentation AssetIdentifier" \
   --field AssetIdentifier \
   --property-uri https://example.org/dexpi/hasAssetIdentifier \
   --output reports/e2_engineering_parity.json

Both planners independently interpret the same question and execute read-only
GraphDB SELECTs. Only comparable terminal-property values are compared; this
does not establish full plan, entity identity, or aggregate parity.
"""
import argparse
import json
from pathlib import Path

from process_sim.api.dtwise_query import SCHEMA_PATH, run_question
from process_sim.api.unified_cli import run_unified_cli
from process_sim.dtwise.schema import Schema


def _legacy_values(answer, property_uri):
    if not isinstance(answer, dict):
        raise ValueError("Legacy answer is not a structured object")
    if answer.get("truncated_possible"):
        raise ValueError("Legacy result may be truncated; parity is inconclusive")
    if answer.get("intent") not in (None, "list"):
        raise ValueError("Legacy answer is not a list of property values")
    declared = answer.get("property")
    if declared is not None and declared != property_uri:
        raise ValueError("Legacy projection differs from requested property")
    if "values" not in answer or not isinstance(answer["values"], list):
        raise ValueError("Legacy answer has no comparable values array")
    values = []
    for row in answer["values"]:
        if isinstance(row, str):
            values.append(row)
        elif isinstance(row, dict) and "value" in row and row["value"] is not None:
            values.append(str(row["value"]))
        elif isinstance(row, dict) and isinstance(row.get("properties"), dict):
            if property_uri not in row["properties"] or row["properties"][property_uri] is None:
                raise ValueError("Legacy multi-property row omits requested property")
            values.append(str(row["properties"][property_uri]))
        else:
            raise ValueError("Unsupported legacy result shape; cannot compare safely")
    return sorted(set(values))


def _unified_values(report, field, property_uri):
    if report["plan"]["sources"] != ("graphdb",) and report["plan"]["sources"] != ["graphdb"]:
        raise ValueError("Unified interpretation was not engineering-only")
    projections = report["plan"]["projections"]
    match = [p for p in projections if p["name"] == field]
    if len(match) != 1 or match[0]["path"] is None:
        raise ValueError("Unified result does not project requested field")
    if match[0]["path"]["predicates"][-1] != property_uri:
        raise ValueError("Unified projection has the wrong terminal SHACL predicate")
    graph = report.get("graph", {})
    if graph.get("truncated_possible"):
        raise ValueError("Unified result may be truncated; parity is inconclusive")
    rows = graph.get("rows")
    if not isinstance(rows, list):
        raise ValueError("Unified GraphDB rows missing")
    if any(not isinstance(row, dict) or field not in row or row[field] is None for row in rows):
        raise ValueError("Unified result has incomplete projected values")
    return sorted({str(row[field]) for row in rows})


def compare_engineering_question(question, *, field, property_uri,
                                 legacy_runner=run_question,
                                 unified_runner=run_unified_cli,
                                 schema=None):
    """Run two independent read-only planners and compare one terminal property.

    Errors are returned as inconclusive, never counted as parity success.
    """
    if not all(isinstance(x, str) and x.strip()
               for x in (question, field, property_uri)):
        raise ValueError("Question, field and property URI are required")
    report = {"question": question, "field": field,
              "property_uri": property_uri, "status": "INCONCLUSIVE",
              "legacy": {}, "unified": {}}
    try:
        old = legacy_runner(question)
        report["legacy"] = {
            "mode": old.get("mode"), "sparql": old.get("sparql"),
            "count": old.get("answer", {}).get("count"),
            "executed": old.get("executed")}
        old_values = _legacy_values(old["answer"], property_uri)
        report["legacy"]["values"] = old_values
    except Exception as exc:
        report["legacy"]["error"] = type(exc).__name__ + ": " + str(exc)
        return report
    try:
        if schema is None:
            schema = Schema(str(SCHEMA_PATH))
        new = unified_runner(question, schema=schema)
        report["unified"] = {
            "sparql": new.get("sparql"), "executed": new.get("executed"),
            "count": new.get("graph", {}).get("count")}
        new_values = _unified_values(new, field, property_uri)
        report["unified"]["values"] = new_values
    except Exception as exc:
        report["unified"]["error"] = type(exc).__name__ + ": " + str(exc)
        return report
    report["status"] = "MATCH" if old_values == new_values else "MISMATCH"
    report["only_legacy"] = sorted(set(old_values) - set(new_values))
    report["only_unified"] = sorted(set(new_values) - set(old_values))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", required=True)
    parser.add_argument("--field", required=True,
                        help="Unified GraphDB projection column, e.g. AssetIdentifier")
    parser.add_argument("--property-uri", required=True,
                        help="Expected SHACL terminal predicate URI on both sides")
    parser.add_argument("--output", default="reports/e2_engineering_parity.json")
    args = parser.parse_args(argv)
    result = compare_engineering_question(
        args.question, field=args.field, property_uri=args.property_uri)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["status"] == "MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
