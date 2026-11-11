#!/usr/bin/env python3
"""Controlled Phase 4 routing: validated EBOM V2 association path or legacy V4.1."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"experiments"))
from dtwise_phase3_associations import parse_question,compile_query
from dtwise_entity_resolver import resolve_remote
from dtwise_path_selector import load_catalog,select_path
from ebom_v2_nl2sparql import run_query
LEGACY=ROOT/"experiments/ontology_nl2sparql_generic_v4_1.py"
MARKER=re.compile(r"\b(functionally associated|functional associations?)\b",re.I)
OUTPUT=re.compile(r"\b(return|display|retrieve|select|give me)\b",re.I)
def route(question):
    return "ebom_v2_catalog" if MARKER.search(question) else "generic_v4_1"
def handle_ebom(question,endpoint,execute):
    plan=parse_question(question)
    catalog=load_catalog()
    resolved=resolve_remote(plan["equipment_tag"],endpoint,catalog["graph"]) if execute else None
    query=compile_query(plan,catalog,resolved)
    result={"route":"ebom_v2_catalog","status":"compiled","plan":plan,
            "path":[e["id"] for e in select_path(catalog,plan["intent"])],
            "resolution":resolved,"sparql":query,
            "evidence_policy":"functional_association_only_not_physical_membership"}
    if execute:
        bindings=run_query(query,endpoint)["results"]["bindings"]
        result.update(status="executed",binding_count=len(bindings),results=bindings)
        if not bindings:
            result["note"]="No matching records for the requested source classification; not a query failure."
    return result
def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--question",required=True)
    ap.add_argument("--graphdb-url",default="http://localhost:7200/repositories/AAS")
    ap.add_argument("--skip-execution",action="store_true")
    ap.add_argument("--output",type=Path,default=Path("reports/dtwise_phase4_router.json"))
    args,extra=ap.parse_known_args(argv)
    selected=route(args.question)
    if selected=="generic_v4_1":
        cmd=[sys.executable,str(LEGACY),"--question",args.question,
             "--graphdb-url",args.graphdb_url,"--output",str(args.output)]
        if args.skip_execution:cmd.append("--skip-execution")
        cmd.extend(extra)
        print(json.dumps({"route":selected,"delegate":str(LEGACY)}),flush=True)
        return subprocess.call(cmd,cwd=str(ROOT))
    if extra:
        result={"route":selected,"status":"unsupported","reason":"UNSUPPORTED_EBOM_OPTIONS: "+" ".join(extra)}
    elif OUTPUT.search(args.question):
        result={"route":selected,"status":"unsupported",
                "reason":"UNSUPPORTED_OUTPUT_REQUEST: Phase 3 supports engineeringId, description, sourceDomain, sourceGroup only"}
    else:
        try:result=handle_ebom(args.question,args.graphdb_url,not args.skip_execution)
        except ValueError as e:result={"route":selected,"status":"unsupported","reason":str(e)}
        except Exception as e:result={"route":selected,"status":"error","reason":type(e).__name__+": "+str(e)}
    path=args.output if args.output.is_absolute() else ROOT/args.output
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,ensure_ascii=False))
    print("Audit saved:",path)
    return 0 if result["status"] in ("compiled","executed") else 2
if __name__=="__main__":sys.exit(main())
