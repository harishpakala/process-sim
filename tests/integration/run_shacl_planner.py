"""Live SHACL planner integration baseline; runs real CLI/Ollama, never executes SPARQL.

From repository root:
    python tests/integration/run_shacl_planner.py
    python tests/integration/run_shacl_planner.py --report shacl-baseline.json
"""
import argparse
import os
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
COMMON = ("--semantic-paths", "--llm", "--json")
ENDPOINT = "https://example.org/ecad/hasEndPoint"
PLC = "https://example.org/ecad/hasPLCEndPoint"
LOCAL = "https://example.org/ecad/hasLocalId"
DEVICE_TYPE = "https://example.org/ecad/hasDeviceType"
BOTH = "Show EndPoint Address and PLCEndPoint Address belonging to the same Device"
FILTERED = BOTH + " where Device LocalId = FI_101"
TWOFILTER = FILTERED + " and Device DeviceType = Sensor in ECAD."
ALT = "Find the addresses of EndPoint and PLCEndPoint for devices with LocalId FI_101 and DeviceType Sensor"


def case(name, mode, question, paths=(), predicates=(), values=(), filters=0,
         expected="selected", queries=None):
    return dict(name=name, mode=mode, question=question, paths=list(paths),
                predicates=list(predicates), values=list(values),
                filters=filters, expected=expected, queries=queries)


CASES = [
    case("retrieve", "--phase1-plan",
         "Show Address of EndPoint belonging to Device in ECAD",
         paths=("ECAD → Device → EndPoint → Address",),
         predicates=(ENDPOINT,), queries=1),
    case("one-filter", "--phase2-filter",
         "Show Address of EndPoint belonging to Device where Device LocalId = FI_101 in ECAD",
         paths=("ECAD → Device → EndPoint → Address",),
         predicates=(ENDPOINT, LOCAL), values=("FI_101",), filters=1, queries=1),
    case("two-and-filters", "--phase3-and",
         "Show Address of EndPoint belonging to Device where Device LocalId = FI_101 and Device DeviceType = Sensor in ECAD",
         paths=("ECAD → Device → EndPoint → Address",),
         predicates=(ENDPOINT, LOCAL, DEVICE_TYPE),
         values=("FI_101", "Sensor"), filters=2, queries=1),
    case("sibling-join", "--phase4-join", BOTH + " in ECAD",
         paths=("ECAD → Device → EndPoint → Address",
                "ECAD → Device → PLCEndPoint → Address"),
         predicates=(ENDPOINT, PLC), filters=0, queries=1),
    case("join-one-filter", "--phase4-filtered-join", FILTERED + " in ECAD",
         paths=("ECAD → Device → EndPoint → Address",
                "ECAD → Device → PLCEndPoint → Address"),
         predicates=(ENDPOINT, PLC, LOCAL), values=("FI_101",),
         filters=1, queries=1),
    case("join-two-filters", "--phase4-and-join", TWOFILTER,
         paths=("ECAD → Device → EndPoint → Address",
                "ECAD → Device → PLCEndPoint → Address"),
         predicates=(ENDPOINT, PLC, LOCAL, DEVICE_TYPE),
         values=("FI_101", "Sensor"), filters=2, queries=1),
    case("alternative-wording", "--direct-intent", ALT,
         paths=("ECAD → Device → EndPoint → Address",
                "ECAD → Device → PLCEndPoint → Address"),
         predicates=(ENDPOINT, PLC, LOCAL, DEVICE_TYPE),
         values=("FI_101", "Sensor"), filters=2, queries=1),
    case("or-two-filters", "--phase4-and-join",
         BOTH + " where Device LocalId = FI_101 or Device DeviceType = Sensor in ECAD",
         paths=("ECAD → Device → EndPoint → Address",
                "ECAD → Device → PLCEndPoint → Address"),
         predicates=(ENDPOINT, PLC, LOCAL, DEVICE_TYPE),
         values=("FI_101", "Sensor"), filters=1, queries=1),
    case("unsupported-abstains", "--phase4-and-join",
         BOTH + " where Device LocalId = FI_101 or Device DeviceType = Sensor and Device Status = Active in ECAD",
         expected="unresolved", queries=0),
    case("auto-join-broad-address", "--phase1-plan", "Show Address in ECAD",
         paths=("ECAD → Device → EndPoint → Address",
                "ECAD → Device → PLCEndPoint → Address",
                "ECAD → Symbol → EndPoint → Address",
                "ECAD → Symbol → PLCEndPoint → Address"),
         predicates=(ENDPOINT, PLC), queries=2),
]


def extract_queries(result):
    if "queries" in result:
        items = result["queries"]
        if isinstance(items, list):
            return [x["sparql"] for x in items]
        if isinstance(items, dict):
            return list(items.values())
        raise AssertionError("Unexpected queries representation")
    if "sparql" in result:
        item = result["sparql"]
        if item is None:
            return []
        if isinstance(item, str):
            return [item]
        if isinstance(item, dict):
            return list(item.values())
    return []


def check(test, result):
    plan = result.get("plan") or result.get("selection") or {}
    status = ("selected" if result.get("intent") is not None else "unresolved") if test["mode"] == "--direct-intent" else plan.get("status")
    if status != test["expected"]:
        raise AssertionError(f"Expected {test['expected']}, got {status}: {result.get('reason') or plan.get('reason')}")
    if test["mode"] in ("--phase2-filter", "--phase3-and",
                        "--phase4-join", "--phase4-filtered-join"):
        expected_trace = (
            ["start", "qualified", "model_selected", "validated", "compiled"]
            if test["expected"] == "selected"
            else ["start", "qualified", "model_selected", "validated", "abstained"]
        )
        if result.get("state_trace") != expected_trace:
            raise AssertionError(
                f"Single-domain state machine not exercised: {result.get('state_trace')}"
            )
        if result.get("state") != expected_trace[-1]:
            raise AssertionError("Single-domain terminal state mismatch")
    if test["mode"] == "--phase1-plan":
        expected_trace = (
            ["start", "qualified", "model_selected", "validated", "compiled"]
            if test["expected"] == "selected"
            else ["start", "qualified", "model_selected", "validated", "abstained"]
        )
        if result.get("state_trace") != expected_trace:
            raise AssertionError(
                f"RETRIEVE state machine not exercised: {result.get('state_trace')}"
            )
        if result.get("state") != expected_trace[-1]:
            raise AssertionError("RETRIEVE terminal state mismatch")
    if test["mode"] == "--phase4-and-join":
        expected_trace = (
            ["start", "qualified", "abstained"]
            if test["expected"] != "selected"
            else ["start", "qualified", "model_selected", "validated", "compiled"]
        )
        if result.get("state_trace") != expected_trace:
            raise AssertionError(
                f"State machine not exercised as expected: {result.get('state_trace')}"
            )
        if result.get("state") != expected_trace[-1]:
            raise AssertionError("State machine terminal state mismatch")
    queries = extract_queries(result)
    if len(queries) != test["queries"]:
        qualified = result.get("qualified", {})
        labels = {c["id"]: c["path"] for c in qualified.get("prompt", {}).get("candidates", [])
                  if c.get("kind") == "property"}
        selected_ids = (result.get("intent") or {}).get("result_property_ids")
        if selected_ids is None:
            selected_ids = (result.get("plan") or {}).get("result_ids")
        if selected_ids is None:
            selected_ids = (result.get("plan") or {}).get("selected_candidate_ids", [])
        if not selected_ids and (result.get("plan") or {}).get("result_id"):
            selected_ids = [result["plan"]["result_id"]]
        selected_paths = [labels.get(cid, cid) for cid in selected_ids]
        raise AssertionError(
            f"Expected {test['queries']} SPARQL queries, got {len(queries)}; "
            f"selected paths: {selected_paths}; "
            f"compiled SPARQL: {queries}"
        )
    if test["expected"] != "selected":
        if result.get("intent") is not None:
            raise AssertionError("Non-selected case has intent")
        return
    qualified = result.get("qualified", {})
    candidates = {c["id"]: c["path"] for c in qualified.get("prompt", {}).get("candidates", [])
                  if c["kind"] == "property"}
    if test["mode"] == "--direct-intent":
        selected = result["intent"]["result_property_ids"]
    elif test["mode"] == "--phase1-plan":
        selected = plan["selected_candidate_ids"]
    elif test["mode"] == "--phase2-filter":
        selected = plan["result_ids"]
    elif test["mode"] == "--phase3-and":
        selected = plan.get("result_ids", [plan.get("result_id")])
    else:
        selected = plan["result_ids"]
    paths = {candidates.get(cid) for cid in selected}
    if paths != set(test["paths"]):
        raise AssertionError(f"Wrong result paths: {sorted(str(p) for p in paths)}")
    for query in queries:
        if not query.lstrip().startswith("SELECT DISTINCT") or any(
            token in query.upper() for token in ("INSERT ", "DELETE ", "UPDATE ", "SERVICE ")
        ):
            raise AssertionError("Not a read-only SELECT DISTINCT")
        if query.count("FILTER(") != test["filters"]:
            raise AssertionError("Incorrect filter count")
        for predicate in test["predicates"]:
            if f"<{predicate}>" not in query:
                raise AssertionError(f"Missing verified predicate: {predicate}")
        for value in test["values"]:
            if json.dumps(value) not in query:
                raise AssertionError(f"Missing literal: {value}")


def run(test, args):
    flags = ["--phase1-sparql"] if test["mode"] == "--phase1-plan" else []
    command = [sys.executable, "-m", "process_sim.dtwise.try_dexpi", *COMMON,
               test["mode"], *flags, "--model", args.model,
               "--embed-model", args.embed_model, "--ollama-url", args.ollama_url,
               test["question"]]
    start = perf_counter()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        process = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace",
                                 timeout=args.timeout)
        if process.returncode:
            raise AssertionError(f"CLI exit {process.returncode}: {(process.stderr or process.stdout)[-1500:]}")
        try:
            result = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"Non-JSON CLI output: {process.stdout[-1000:]}") from exc
        check(test, result)
        return dict(name=test["name"], status="PASS", seconds=round(perf_counter()-start, 3))
    except Exception as exc:
        return dict(name=test["name"], status="FAIL", seconds=round(perf_counter()-start, 3),
                    reason=str(exc))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=Path("shacl-integration-report.json"))
    parser.add_argument("--case", action="append", choices=[c["name"] for c in CASES],
                        help="Run only this named query (repeat to select multiple); default: all")
    parser.add_argument("--list-cases", action="store_true",
                        help="Print all registered integration queries without running Ollama")
    parser.add_argument("--model", default="qwen2.5-coder:7b")
    parser.add_argument("--embed-model", default="nomic-embed-text:latest")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=float, default=240, help="Per-query timeout (seconds)")
    args = parser.parse_args()
    if args.list_cases:
        for test in CASES:
            print(f"{test['name']}: [{test['mode']}] {test['question']}")
        return 0
    selected_cases = [test for test in CASES if not args.case or test["name"] in args.case]
    started = perf_counter()
    results = []
    print("SHACL planner live integration baseline (SPARQL compilation only)", flush=True)
    for test in selected_cases:
        print(f"\nQUERY [{test['name']}]: {test['question']}", flush=True)
        outcome = run(test, args)
        outcome["query"] = test["question"]
        results.append(outcome)
        print(f"{outcome['status']:<4}  {outcome['name']:<25} {outcome['seconds']:>8.3f} s", flush=True)
        if "reason" in outcome:
            print("      " + outcome["reason"].replace("\n", "\n      "), flush=True)
    total = round(perf_counter()-started, 3)
    passed = sum(r["status"] == "PASS" for r in results)
    print(f"TOTAL {passed} PASS / {len(results)-passed} FAIL / {total:.3f} s")
    report = dict(model=args.model, cases=results, passed=passed,
                  failed=len(results)-passed, total_seconds=total,
                  note="Live model output can vary; SPARQL was compiled but never executed")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report: {args.report}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
