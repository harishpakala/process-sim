"""Read-only fingerprint of visible named graphs and default query view."""
import argparse, hashlib, json, datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from rdflib import Graph, URIRef, Literal, BNode
from rdflib.compare import to_canonical_graph

ROOT=Path(__file__).resolve().parents[3]
def select(endpoint, query):
    req=Request(endpoint,data=urlencode({'query':query,'infer':'false'}).encode(),headers={'Accept':'application/sparql-results+json','Content-Type':'application/x-www-form-urlencoded'})
    with urlopen(req,timeout=120) as response:
        return json.load(response)['results']['bindings']

def term(t):
    if t['type']=='uri': return URIRef(t['value'])
    if t['type']=='bnode': return BNode(t['value'])
    if t['type'] in ('literal','typed-literal'):
        return Literal(t['value'],lang=t.get('xml:lang'),datatype=URIRef(t['datatype']) if t.get('datatype') else None,normalize=False)
    raise ValueError('Unsupported RDF term: '+str(t))

def fingerprint(rows):
    g=Graph()
    for row in rows:
        g.add(tuple(term(row[k]) for k in ('s','p','o')))
    canonical=to_canonical_graph(g)
    lines=sorted(' '.join(t.n3() for t in triple)+' .' for triple in canonical)
    return {'triple_count':len(g),'sha256':hashlib.sha256(('\n'.join(lines)+'\n').encode()).hexdigest()}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--graphdb-url',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--compare',type=Path)
    a=p.parse_args()
    if a.output.exists(): p.error('Output already exists')
    registry=json.loads((ROOT/'benchmarks/shacl_phase1/aast_instance_graphs.json').read_text(encoding='utf-8-sig'))
    names=sorted({r['g']['value'] for r in select(a.graphdb_url,'SELECT DISTINCT ?g WHERE { GRAPH ?g { ?s ?p ?o } }')})
    if set(registry.values())-set(names): raise ValueError('Registered instance graph missing or empty')
    graphs={}
    for name in names:
        graphs[name]=fingerprint(select(a.graphdb_url,'SELECT ?s ?p ?o WHERE { GRAPH '+URIRef(name).n3()+' { ?s ?p ?o } }'))
        print(name,graphs[name]['triple_count'],flush=True)
    default=fingerprint(select(a.graphdb_url,'SELECT ?s ?p ?o WHERE { ?s ?p ?o }'))
    content={'named_graphs':graphs,'default_query_view':default}
    report={'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'endpoint':a.graphdb_url,'inference_requested':False,'registered_graphs':registry,'content':content,'content_sha256':hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'limitations':'Separate SELECT requests, not an atomic snapshot. Empty named graphs are not enumerated. Blank nodes canonicalized per graph; cross-graph blank-node identity not captured. Default query view may be a union. Keep repository unchanged during capture.'}
    if a.compare:
        old=json.loads(a.compare.read_text(encoding='utf-8-sig'))
        report['matches_previous']=all(report[k]==old[k] for k in ('endpoint','inference_requested','registered_graphs','content_sha256'))
    with a.output.open('x',encoding='utf-8') as f:
        json.dump(report,f,indent=2); f.write('\n')
    print('Content SHA-256:',report['content_sha256'])
    print('Saved',a.output)
    if a.compare and not report['matches_previous']: raise SystemExit('Dataset fingerprint changed')

if __name__=='__main__': main()
