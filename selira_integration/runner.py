"""Experimental, read-only GraphDB SHACL runner. Approval/readiness is external."""
import argparse, hashlib, json
from pathlib import Path
from datetime import datetime, timezone
import requests
from rdflib import Graph

ROOT=Path(__file__).resolve().parent
IDS=tuple(f"SC-{i:02}" for i in range(1,7))

def fetch_graphs(endpoint, named_graphs):
    if not named_graphs: raise ValueError("Named graph IRIs required")
    result=Graph()
    for iri in named_graphs:
        if not iri.startswith(("https://","http://")) or ">" in iri: raise ValueError("Invalid graph IRI")
        query=f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH <{iri}> {{ ?s ?p ?o }} }}"
        response=requests.post(endpoint,data={"query":query},headers={"Accept":"text/turtle"},timeout=30)
        response.raise_for_status()
        part=Graph(); part.parse(data=response.text,format="turtle"); result+=part
    return result

def execute(graph,contract,ready):
    if contract not in IDS: raise ValueError(contract)
    if not ready: return {"contract":contract,"status":"INDETERMINATE","reason":"Evidence completeness/approval not confirmed"}
    from pyshacl import validate
    shapes=Graph(); shapes.parse(ROOT/"contracts"/"shapes"/f"{contract}.ttl",format="turtle")
    conforms,report,_=validate(graph,shacl_graph=shapes,advanced=True,inference="none")
    return {"contract":contract,"status":"VALIDATED" if conforms else "INVALID","report":report.serialize(format="turtle")}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--endpoint",required=True)
    parser.add_argument("--graph",action="append",required=True)
    parser.add_argument("--source-revisions",required=True)
    parser.add_argument("--ready",action="append",choices=IDS,default=[])
    parser.add_argument("--audit",default="out/selira-validation-history.jsonl")
    args=parser.parse_args()
    revisions=json.loads(Path(args.source_revisions).read_text())
    if not revisions: raise ValueError("Source revisions required")
    graph=fetch_graphs(args.endpoint,args.graph)
    audit=Path(args.audit);audit.parent.mkdir(parents=True,exist_ok=True)
    for contract in IDS:
        result=execute(graph,contract,contract in args.ready)
        record={"timestamp":datetime.now(timezone.utc).isoformat(),"contract":contract,"source_revisions":revisions,"status":result["status"],"shape_sha256":hashlib.sha256((ROOT/"contracts"/"shapes"/f"{contract}.ttl").read_bytes()).hexdigest(),"report":result.get("report"),"reason":result.get("reason")}
        with audit.open("a") as f:f.write(json.dumps(record)+"\\n")
        print(contract,result["status"])
if __name__=="__main__":main()
