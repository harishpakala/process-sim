"""Oracle-selected paths: isolate compiler correctness, not retrieval accuracy."""
import json
from pathlib import Path
from collections import Counter
from rdflib import Graph
from process_sim.dtwise.shacl_planner.grounding.subgraph import load_index
from process_sim.dtwise.shacl_planner.sparql_compiler import compile_single_domain

HERE=Path(__file__).resolve().parent
SCHEMA=HERE.parents[2]/"semantic/ontology2/dtwise/dtwise-schema-index.json"
E="https://example.org/ecad/"
ROOT_CLASS="http://org.example.com/aHR0cHM6Ly9leGFtcGxlLm9yZy9zbS9lY2Fk/"
PATHS=[
 ("hasDevice","hasLocalId"),("hasSymbol","hasLocalId"),("hasElectricalNet","hasLocalId"),
 ("hasDevice","hasEndPoint","hasLocalId"),("hasSymbol","hasEndPoint","hasLocalId"),
 ("hasDevice","hasPLCEndPoint","hasLocalId"),("hasSymbol","hasPLCEndPoint","hasLocalId"),
 ("hasDevice","hasEndPoint","hasAddress"),("hasSymbol","hasEndPoint","hasAddress"),
 ("hasDevice","hasPLCEndPoint","hasAddress"),("hasSymbol","hasPLCEndPoint","hasAddress")]

def unique(items):
    if len(items)!=1:
        raise ValueError(f"Expected one schema match, got {len(items)}: {items}")
    return items[0]

def main():
    schema=json.loads(SCHEMA.read_text(encoding="utf-8-sig"))
    index=load_index(SCHEMA,domain="ecad")
    root=unique([r["subject"] for r in schema["relationships"] if r.get("domain")=="ecad" and r["predicate"]=="http://www.w3.org/ns/shacl#targetClass" and r["object"]==ROOT_CLASS])
    graph=Graph().parse(HERE/"fixture.ttl",format="turtle")
    cases=json.loads((HERE/"cases.json").read_text(encoding="utf-8"))
    assert len(cases)==len(PATHS)
    for case,path in zip(cases,PATHS):
        nodes=[root]; edges=[]
        for predicate in path[:-1]:
            edge=unique([e for e in index.edges if e["from"]==nodes[-1] and e["predicate"]==E+predicate])
            edges.append(edge); nodes.append(edge["to"])
        prop=unique([p for p in index.properties[nodes[-1]] if p["predicate"]==E+path[-1]])
        record={"status":"valid_response","validation_errors":[],"domain":"ecad",
                "candidate_paths":[{"id":"P1","kind":"property"}],
                "candidate_registry":{"P1":{"domain":"ecad","kind":"property","node_uris":nodes,"edges":edges,"property":prop}},
                "answer":{"status":"selected","projection_ids":["P1"],"existence_ids":[],"filters":[],"boolean_operator":"NONE","join":False,"join_owner_id":None,"count_target_id":None,"order_by":[],"limit":None}}
        query=compile_single_domain(record,index,schema)
        actual=Counter(row[0] for row in graph.query(query))
        reference=Counter(row[0] for row in graph.query(case["sparql"]))
        assert actual==reference,(case["id"],query,actual,reference)
        print(case["id"],"PASS")
    print(len(cases),"oracle-selected compiler cases passed")
if __name__=="__main__":
    main()
