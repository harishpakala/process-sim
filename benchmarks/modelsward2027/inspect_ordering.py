"""Read-only ordering diagnostics; does not approve ordered scoring."""
import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from collections import Counter

HERE=Path(__file__).resolve().parent

def inspect(rows, limit):
    keys=[]
    for row in rows:
        key=row.get("sort")
        if not key or key.get("type") not in ("literal","typed-literal"):
            raise ValueError("Missing or unsupported sort key")
        keys.append(json.dumps(key,sort_keys=True))
    counts=Counter(keys)
    return {"unrestricted_rows":len(rows),"limit":limit,
            "repeated_key_groups":sum(n>1 for n in counts.values()),
            "boundary_tie":0<limit<len(keys) and keys[limit-1]==keys[limit],
            "sort_key_types":sorted({(r["sort"].get("datatype") or "",r["sort"].get("xml:lang") or "") for r in rows}),
            "review_required":True}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--graphdb-url",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    probes=json.loads((HERE/"ordering_probes.json").read_text())["probes"]
    results=[]
    for probe in probes:
        rec={"scenario_id":probe["scenario_id"]}
        try:
            req=Request(a.graphdb_url,data=urlencode({"query":probe["sparql"],"infer":"false"}).encode(),headers={"Accept":"application/sparql-results+json","Content-Type":"application/x-www-form-urlencoded"})
            with urlopen(req,timeout=60) as response:
                data=json.load(response)
            rows=data["results"]["bindings"]
            rec.update(inspect(rows,probe["limit"]))
            rec["bindings"]=rows
            rec["status"]="diagnostic_complete"
        except Exception as e:
            rec.update(status="error",error=str(e))
        results.append(rec)
        print(rec["scenario_id"],rec["status"],rec.get("boundary_tie"))
    with Path(a.output).open("x",encoding="utf-8") as f:
        json.dump({"inference_requested":False,"results":results},f,indent=2)
    return int(any(r["status"]=="error" for r in results))

if __name__=="__main__":
    raise SystemExit(main())
