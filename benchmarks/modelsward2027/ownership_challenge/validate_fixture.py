import json
from pathlib import Path
from collections import Counter
from rdflib import Graph, Literal, XSD

def main():
    here=Path(__file__).resolve().parent
    graph=Graph().parse(here/"fixture.ttl",format="turtle")
    cases=json.loads((here/"cases.json").read_text(encoding="utf-8"))
    seen=set()
    for case in cases:
        values=[row[0] for row in graph.query(case["sparql"])]
        assert all(isinstance(v,Literal) and v.language is None and v.datatype in (None,XSD.string) for v in values),case["id"]
        actual=Counter(map(str,values))
        assert actual==Counter(case["expected"]),case["id"]
        signature=tuple(sorted(actual.items()))
        assert signature not in seen,case["id"]
        seen.add(signature)
        print(case["id"],"PASS")
    print(len(cases),"reference cases passed;",len(graph),"triples")
if __name__=="__main__":
    main()
