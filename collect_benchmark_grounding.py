"""Read-only GraphDB benchmark grounding audit; run from process-sim root."""
import argparse, json, hashlib, os, re
from pathlib import Path
from datetime import datetime, timezone
import requests

DOMAINS = ('dexpi','ecad','assetinventory','productcatalog','opcuaconnectivity')
def iri(v):
    if not re.fullmatch(r'https?://[^\s<>"{}|^`\\]+',v):
        raise ValueError('Invalid IRI: '+str(v))
    return '<'+v+'>'
def val(row,k): return row[k]['value']
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--graphdb-url',default=os.getenv('GRAPHDB_URL'))
    p.add_argument('--audit',type=Path,default=Path('engineering_dataset_audit/engineering_dataset_statistics.json'))
    p.add_argument('--root',type=Path,default=Path.cwd())
    p.add_argument('--output',type=Path,default=Path('benchmark_grounding_audit'))
    p.add_argument('--timeout',type=int,default=120)
    a=p.parse_args()
    url=a.graphdb_url or input('GraphDB repository SPARQL URL: ').strip()
    if not re.fullmatch(r'https?://[^/@?#]+/[^?#]+',url): p.error('Use repository URL without credentials or query parameters')
    old=json.loads(a.audit.read_text(encoding='utf-8-sig'))
    folder=a.root/'semantic/ontology2/dtwise'
    paths=[folder/n for n in ('dtwise-schema-index.json','cross-domain-mappings.json')]
    hashes={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in paths}
    idx,registry=[json.loads(x.read_text(encoding='utf-8-sig')) for x in paths]
    a.output.mkdir(parents=True,exist_ok=True)
    out={'collected_at_utc':datetime.now(timezone.utc).isoformat(),'source_hashes':hashes,'same_schema_as_previous_audit':hashes==old['source_hashes'],'inference_requested':False,'queries':{},'domains':{},'mappings':[], 'notes':['Class-qualified direct predicate joins are instance evidence, not proof of SHACL path qualification or physical identity.','Reference result rows are complete for the explicit SELECT queries; they are not yet gold labels for natural-language benchmark questions.']}
    dest=a.output/'benchmark_grounding.json'
    def save(): dest.write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
    session=requests.Session()
    def query(name,q):
        print(name,flush=True)
        rec={'sparql':q};out['queries'][name]=rec
        try:
            r=session.post(url,data={'query':q,'infer':'false'},headers={'Accept':'application/sparql-results+json'},timeout=a.timeout);r.raise_for_status()
            data=r.json(); rows=data['results']['bindings'];rec.update(status='ok',variables=data['head']['vars'],rows=rows);return rows
        except (requests.RequestException,ValueError,KeyError) as e:
            rec.update(status='error',error_type=type(e).__name__,http_status=getattr(getattr(e,'response',None),'status_code',None));return None
        finally: save()
    def count(name,pattern):
        rows=query(name,'SELECT (COUNT(*) AS ?n) WHERE { '+pattern+' }')
        return int(val(rows[0],'n')) if rows else None
    graphs={}
    for d in DOMAINS:
        ns='https://example.org/'+d+'/'
        gs=[val(r,'g') for r in old['domains'][d]['graph_evidence']]
        if not gs: raise ValueError('No prior graph evidence for '+d)
        graphs[d]='VALUES ?g { '+' '.join(map(iri,gs))+' }'
        g=graphs[d];f=f'FILTER(STRSTARTS(STR(?p), "{ns}") || (?p = <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> && STRSTARTS(STR(?o), "{ns}")))'
        stats={'graphs':gs,'whole_graph_quads':count(d+'_whole',g+' GRAPH ?g { ?s ?p ?o }'),'domain_predicate_or_type_quads':count(d+'_scoped',g+' GRAPH ?g { ?s ?p ?o '+f+' }')}
        out['domains'][d]=stats
        # Full typed-subject direct property inventory, including RDF term types.
        pattern=g+f' GRAPH ?g {{ ?s a ?class ; ?p ?o . FILTER(STRSTARTS(STR(?class), "{ns}")) FILTER(STRSTARTS(STR(?p), "{ns}")) }}'
        query(d+'_property_values','SELECT DISTINCT ?g ?class ?s ?p ?o WHERE { '+pattern+' } ORDER BY ?class ?s ?p ?o ?g')
        classes=query(d+'_classes','SELECT DISTINCT ?class WHERE { '+g+f' GRAPH ?g {{ ?s a ?class FILTER(STRSTARTS(STR(?class), "{ns}")) }} }} ORDER BY ?class')
        for i,row in enumerate(classes or []):
            c=iri(val(row,'class'));query(f'{d}_entity_reference_{i}','SELECT DISTINCT ?s WHERE { '+g+' GRAPH ?g { ?s a '+c+' } } ORDER BY ?s')
        # Preserve index path records for subsequent owner/path review.
        stats['indexed_shape_paths']=[x for x in idx['shape_paths'] if x.get('domain')==d]
        save()
    for m in registry:
        l,r=m['left_domain'],m['right_domain']
        if not m.get('verified') or l not in graphs or r not in graphs: continue
        name=m['id'];lp,rp=iri(m['left_property']),iri(m['right_property'])
        pattern=graphs[l].replace('?g','?lg')+' '+graphs[r].replace('?g','?rg')+f' GRAPH ?lg {{ ?left a ?lc ; {lp} ?key }} GRAPH ?rg {{ ?right a ?rc ; {rp} ?key }} FILTER(STRSTARTS(STR(?lc), "https://example.org/{l}/") && STRSTARTS(STR(?rc), "https://example.org/{r}/"))'
        rows=query(name+'_owner_pairs','SELECT ?lc ?rc (COUNT(DISTINCT ?key) AS ?keys) (COUNT(*) AS ?bindings) WHERE { '+pattern+' } GROUP BY ?lc ?rc ORDER BY ?lc ?rc')
        matches=query(name+'_reference','SELECT DISTINCT ?lc ?rc ?left ?right ?key WHERE { '+pattern+' } ORDER BY ?lc ?rc ?key ?left ?right')
        out['mappings'].append({'id':name,'owner_pairs':rows,'distinct_reference_rows':len(matches) if matches is not None else None})
        save()
    out['failed_queries']=[k for k,v in out['queries'].items() if v['status']!='ok'];save()
    print('Saved:',dest.resolve(),'Failed queries:',len(out['failed_queries']))
if __name__=='__main__': main()
