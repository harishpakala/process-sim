"""Full-method ownership pilot; local fixture, production planner and compiler."""
import argparse, hashlib, json, time
from pathlib import Path
from collections import Counter
from rdflib import Graph, Literal, XSD
from process_sim.dtwise.shacl_planner.grounding.subgraph import load_index
from process_sim.dtwise.shacl_planner.standalone_shacl_query_planner import run_one
from process_sim.dtwise.shacl_planner.sparql_compiler import compile_single_domain

HERE=Path(__file__).resolve().parent
SCHEMA=HERE.parents[2]/"semantic/ontology2/dtwise/dtwise-schema-index.json"
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model",default="qwen2.5-coder:7b")
    p.add_argument("--ollama-url",default="http://127.0.0.1:11434")
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--full",action="store_true")
    a=p.parse_args()
    schema=json.loads(SCHEMA.read_text(encoding="utf-8-sig"))
    index=load_index(SCHEMA,domain="ecad")
    graph=Graph().parse(HERE/"fixture.ttl",format="turtle")
    cases=json.loads((HERE/"cases.json").read_text(encoding="utf-8"))
    hashes={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in [SCHEMA,HERE/"fixture.ttl",HERE/"cases.json"]}
    counts=Counter()
    with a.output.open("x",encoding="utf-8") as f:
        for case in cases:
            for i,q in enumerate(case["questions"] if a.full else case["questions"][:1],1):
                r=dict(case_id=case["id"],variant=i,question=q,model=a.model,method="expanded",hashes=hashes,structural_review_required=True)
                start=time.perf_counter()
                stage="planning"
                try:
                    plan=run_one(index,q,method="expanded",model=a.model,endpoint=a.ollama_url)
                    r["planner_record"]=plan
                    if plan.get("status")!="valid_response" or plan.get("validation_errors"):
                        r["status"]="planning_not_valid"
                    else:
                        stage="compilation"
                        query=compile_single_domain(plan,index,schema)
                        r["sparql"]=query
                        stage="execution"
                        result=graph.query(query)
                        rows=list(result)
                        expected=Counter(case["expected"])
                        valid=len(result.vars)==1 and all(len(row)==1 and isinstance(row[0],Literal) and row[0].language is None and row[0].datatype in (None,XSD.string) for row in rows)
                        r["bindings"]=[[v.n3() if v is not None else None for v in row] for row in rows]
                        r["binding_match"]=valid and Counter(str(row[0]) for row in rows)==expected
                        r["status"]="binding_match" if r["binding_match"] else "binding_mismatch"
                except Exception as e:
                    r.update(status=stage+"_error",error=f"{type(e).__name__}: {e}")
                r["elapsed_seconds"]=time.perf_counter()-start
                counts[r["status"]]+=1
                f.write(json.dumps(r,default=str,ensure_ascii=False)+"\n"); f.flush()
                print(case["id"],i,r["status"],flush=True)
    print(json.dumps(dict(counts),indent=2))
if __name__=="__main__":
    main()
