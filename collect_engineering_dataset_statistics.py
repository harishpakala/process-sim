"""Read-only engineering dataset audit. Run from repository root."""
import argparse, csv, hashlib, json, os, re
from pathlib import Path
from datetime import datetime, timezone
import requests

DOMAINS = ('dexpi','ecad','assetinventory','productcatalog','opcuaconnectivity')
BASE = 'https://example.org/'
SH = 'http://www.w3.org/ns/shacl#'

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--graphdb-url', default=os.getenv('GRAPHDB_URL'))
    p.add_argument('--root', type=Path, default=Path.cwd())
    p.add_argument('--output', type=Path, default=Path('engineering_dataset_audit'))
    p.add_argument('--timeout', type=int, default=120)
    a = p.parse_args()
    url = a.graphdb_url or input('GraphDB repository SPARQL URL: ').strip()
    if not re.match(r'^https?://[^/]+/.+', url) or '@' in url.split('/')[2] or '?' in url:
        p.error('Supply a repository URL without credentials or query parameters')
    folder = a.root / 'semantic/ontology2/dtwise'
    ip, mp = [folder / n for n in ('dtwise-schema-index.json','cross-domain-mappings.json')]
    idx, mappings = [json.loads(x.read_text(encoding='utf-8-sig')) for x in (ip,mp)]
    a.output.mkdir(parents=True, exist_ok=True)
    report = {'collected_at_utc':datetime.now(timezone.utc).isoformat(), 'inference_requested':False, 'source_hashes':{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in (ip,mp)}, 'domains':{},'mappings':[], 'queries':{}, 'notes':['Graph counts are whole named graphs, not necessarily instance-only or domain-exclusive.','Typed subjects and predicate counts are separate measures, not a count of physical assets.','Mapping matches use identical RDF terms, without owner/path qualification; they do not establish physical identity.']}
    session = requests.Session()
    def query(name, q):
        print('Query:',name,flush=True)
        record = {'sparql':q}
        report['queries'][name] = record
        try:
            r = session.post(url,data={'query':q,'infer':'false'},headers={'Accept':'application/sparql-results+json'},timeout=a.timeout)
            r.raise_for_status()
            rows = r.json()['results']['bindings']
            record.update(status='ok',rows=rows)
            return rows
        except (requests.RequestException, ValueError, KeyError) as e:
            record.update(status='error',error_type=type(e).__name__,http_status=getattr(getattr(e,'response',None),'status_code',None))
            return None
    def count(name,q):
        rows=query(name,q)
        return int(rows[0]['n']['value']) if rows else None
    graphs=query('named_graph_inventory','SELECT ?g (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } } GROUP BY ?g ORDER BY ?g')
    report['named_graph_inventory']=graphs
    for d in DOMAINS:
        ns=BASE+d+'/'
        c=[x for x in idx['concepts'] if x.get('domain')==d]
        stats={'indexed_concepts':len(c),'indexed_node_shapes':len({x['uri'] for x in c if SH+'NodeShape' in x.get('types',[])}),'indexed_property_shapes':len({x['uri'] for x in c if SH+'PropertyShape' in x.get('types',[])})}
        for k in ('relationships','shape_paths','ontology_edges'):
            stats['indexed_'+k]=sum(x.get('domain')==d for x in idx[k])
        stats['domain_predicate_quads']=count(d+'_predicate_quads',f'SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH ?g {{ ?s ?p ?o FILTER(STRSTARTS(STR(?p), "{ns}")) }} }}')
        stats['typed_subjects']=count(d+'_typed_subjects',f'SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE {{ GRAPH ?g {{ ?s a ?type FILTER(STRSTARTS(STR(?type), "{ns}")) }} }}')
        stats['class_counts']=query(d+'_classes',f'SELECT ?type (COUNT(DISTINCT ?s) AS ?n) WHERE {{ GRAPH ?g {{ ?s a ?type FILTER(STRSTARTS(STR(?type), "{ns}")) }} }} GROUP BY ?type ORDER BY ?type')
        stats['graph_evidence']=query(d+'_graphs',f'SELECT ?g (COUNT(*) AS ?n) WHERE {{ GRAPH ?g {{ ?s ?p ?o FILTER(STRSTARTS(STR(?p), "{ns}") || (?p = <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> && STRSTARTS(STR(?o), "{ns}"))) }} }} GROUP BY ?g ORDER BY ?g')
        report['domains'][d]=stats
    for m in mappings:
        if not m.get('verified') or not {m['left_domain'],m['right_domain']} <= set(DOMAINS): continue
        l,r=m['left_property'],m['right_property']
        if any(not re.fullmatch(r'https?://[^\s<>"{}|^`\\]+',v) for v in (l,r)): raise ValueError('Invalid mapping IRI')
        pattern=f'GRAPH ?lg {{ ?left <{l}> ?key }} GRAPH ?rg {{ ?right <{r}> ?key }}'
        name=m['id']
        result=dict(m)
        result['matching_distinct_keys']=count(name+'_keys',f'SELECT (COUNT(DISTINCT ?key) AS ?n) WHERE {{ {pattern} }}')
        result['sample_matches']=query(name+'_samples',f'SELECT DISTINCT ?left ?right ?key ?lg ?rg WHERE {{ {pattern} }} ORDER BY ?key ?left ?right ?lg ?rg LIMIT 20')
        report['mappings'].append(result)
    (a.output/'engineering_dataset_statistics.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    rows=[{'domain':d,**{k:v for k,v in s.items() if not isinstance(v,list) and k not in ('class_counts','graph_evidence')}} for d,s in report['domains'].items()]
    with (a.output/'engineering_dataset_statistics.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print('Saved:',a.output.resolve())
    print('Failed queries:',sum(x['status']=='error' for x in report['queries'].values()))

if __name__=='__main__': main()
