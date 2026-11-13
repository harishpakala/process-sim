#!/usr/bin/env python3
"""Generic ontology-only NL-to-SPARQL experiment. One-shot, no instance hints or Q13 templates."""
import argparse,json,re,time,sys
from pathlib import Path
from datetime import datetime,timezone
import requests
from rdflib.plugins.sparql.parser import parseQuery
from q13_extract_focused_schema import ROOT,extract

def tokens(s):
 s=re.sub(r'([a-z])([A-Z])',r'\1 \2',s or '')
 return set(re.findall(r'[a-z0-9]+',s.lower()))
def local(u):return u.rsplit('#',1)[-1].rsplit('/',1)[-1]
def catalog(schema,question,limit):
 q=tokens(question)-{'the','and','for','with','from','show','list','return','what','which','all','across','of','in','to'}
 scored=[]
 for d in schema['domains']:
  for shape in d['node_shapes']:
   p=shape['properties']
   terms=tokens(d['domain']+' '+str(shape.get('label') or '')+' '+' '.join(local(x['predicate'])+' '+str(x.get('label') or '') for x in p))
   score=len(q&terms)+4*bool(q&tokens(d['domain']))
   if score:scored.append((score,d['domain'],shape))
 scored.sort(key=lambda x:(-x[0],x[1],x[2]['uri']))
 result={}
 for _,d,s in scored[:limit]:
  key='s'+str(len(result))
  result[key]={'domain':d,'shape':s['uri'],'properties':[{'predicate':p['predicate'],'label':p.get('label'),'kind':p.get('kind')} for p in s['properties']]}
 return result
def joins(cat):
 result={}
 for a,sa in cat.items():
  for b,sb in cat.items():
   if a>=b or sa['domain']==sb['domain']:continue
   for name in ('hasAssetIdentifier','hasProductIdentifier'):
    pa=[p['predicate'] for p in sa['properties'] if local(p['predicate'])==name]
    pb=[p['predicate'] for p in sb['properties'] if local(p['predicate'])==name]
    if pa and pb:
     result['j'+str(len(result))]={'left':a,'right':b,'left_predicate':pa[0],'right_predicate':pb[0],'identifier':name,'evidence':'same identifier local name; RDF-term equality is a hypothesis'}
 return result
SYSTEM="""Translate an unseen engineering question into JSON plan ONLY. Use only supplied SHACL properties and shape IDs. Do not write SPARQL, invent predicates, assume data values or expected answers. Fields: objects {name,shape,predicate}, with safe unique variable names. Joins: array of supplied join IDs only; choose only those needed to connect all selected shapes. Filters: objects {shape,predicate,contains} only for explicitly requested lexical text and descriptive predicates (name/label/description/designation/signal); alternatively {shape,predicate,equals} for user-supplied exact identifier. Unsupported: array of unmet requirements. Do not produce disconnected patterns or fabricate a cross-shape path. Join candidates are unproven identifier-equality hypotheses. Exactly four JSON keys: fields, joins, filters, unsupported. No extra text."""
def validate(plan,cat,edges):
 errors=[]
 if not isinstance(plan,dict) or set(plan)!={'fields','joins','filters','unsupported'}:return ['Invalid plan keys']
 if any(not isinstance(plan[k],list) for k in plan):return ['Plan values must be arrays']
 used=set();names=set()
 for f in plan['fields']:
  if not isinstance(f,dict) or set(f)!={'name','shape','predicate'}:errors.append('Bad field');continue
  n,s,p=f['name'],f['shape'],f['predicate']
  if not isinstance(n,str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_]*',n) or n in names:errors.append('Invalid variable')
  names.add(n)
  if s not in cat or p not in {x['predicate'] for x in cat[s]['properties']}:errors.append('Undeclared field property')
  else:used.add(s)
 for f in plan['filters']:
  if not isinstance(f,dict) or set(f) not in ({'shape','predicate','contains'},{'shape','predicate','equals'}):errors.append('Bad filter');continue
  s,p=f['shape'],f['predicate']
  if s not in cat or p not in {x['predicate'] for x in cat[s]['properties']}:errors.append('Undeclared filter property');continue
  v=f.get('contains',f.get('equals'))
  if not isinstance(v,str) or not v.strip() or len(v)>200:errors.append('Bad filter value')
  if 'contains' in f and not tokens(local(p))&{'name','label','description','designation','signal'}:errors.append('Non-descriptive contains filter')
  used.add(s)
 if not plan['fields']:errors.append('No output fields')
 if any(not isinstance(x,str) for x in plan['unsupported']):errors.append('Invalid unsupported')
 if len(set(str(x) for x in plan['joins']))!=len(plan['joins']):errors.append('Repeated joins')
 for jid in plan['joins']:
  if not isinstance(jid,str) or jid not in edges:errors.append('Unknown join')
 if not errors and used:
  reached={next(iter(used))}
  while True:
   old=len(reached)
   for jid in plan['joins']:
    e=edges[jid]
    if e['left'] in reached:reached.add(e['right'])
    if e['right'] in reached:reached.add(e['left'])
   if len(reached)==old:break
  if not used<=reached:errors.append('Disconnected selected shapes')
  if any(edges[j]['left'] not in reached for j in plan['joins']):errors.append('Disconnected extraneous joins')
 return errors
def compile_plan(plan,edges):
 lines=[]
 for j in plan['joins']:
  e=edges[j];v='?key_'+j
  for side in ('left','right'):lines.append('?node_'+e[side]+' <'+e[side+'_predicate']+'> '+v+' .')
 for f in plan['fields']:lines.append('?node_'+f['shape']+' <'+f['predicate']+'> ?'+f['name']+' .')
 for i,f in enumerate(plan['filters']):
  v='?filter_'+str(i)
  lines.append('?node_'+f['shape']+' <'+f['predicate']+'> '+v+' .')
  if 'contains' in f:lines.append('FILTER(CONTAINS(LCASE(STR('+v+')),LCASE('+json.dumps(f['contains'])+')))')
  else:lines.append('FILTER(STR('+v+') = '+json.dumps(f['equals'])+')')
 query='SELECT DISTINCT '+' '.join('?'+f['name'] for f in plan['fields'])+' WHERE {\n  '+'\n  '.join(lines)+'\n}'
 parseQuery(query)
 return query
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--question',required=True);ap.add_argument('--model',default='qwen2.5-coder:3b')
 ap.add_argument('--ollama-url',default='http://localhost:11434');ap.add_argument('--graphdb-url',default='http://localhost:7200/repositories/AAS')
 ap.add_argument('--num-ctx',type=int,default=8192);ap.add_argument('--num-predict',type=int,default=1000)
 ap.add_argument('--max-prompt-estimate',type=int,default=5000);ap.add_argument('--max-shapes',type=int,default=10)
 ap.add_argument('--ollama-timeout',type=int,default=300);ap.add_argument('--skip-execution',action='store_true')
 ap.add_argument('--output',default='reports/ontology_nl2sparql_generic.json')
 args=ap.parse_args();start=time.monotonic()
 path=Path(args.output)
 if not path.is_absolute():path=ROOT/path
 if path.exists():path=path.with_name(path.stem+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+path.suffix)
 path.parent.mkdir(parents=True,exist_ok=True)
 report={'method':'generic_ontology_only_first_attempt','question':args.question,'model':args.model,'completed':False,'plan':None,'raw_model_response':None,'generated_sparql':None,'plan_issues':[],'graphdb_bindings':None,'binding_count':None,'error':None}
 try:
  schema=extract();cat=catalog(schema,args.question,args.max_shapes);edges=joins(cat)
  report['schema_sources']=[{'domain':d['domain'],'file':d['source_file'],'sha256':d['source_sha256']} for d in schema['domains']]
  report['candidate_shapes']=cat;report['join_candidates']=edges
  if not cat:raise ValueError('No ontology shapes matched question')
  payload=json.dumps({'question':args.question,'shapes':cat,'candidate_joins':edges,'plan_format':{'fields':[{'name':'outputName','shape':'shape ID','predicate':'full IRI'}],'joins':['join ID'],'filters':[],'unsupported':[]}},separators=(',',':'))
  estimate=(len(payload)+len(SYSTEM))//4;budget=min(args.max_prompt_estimate,args.num_ctx-args.num_predict-512)
  report['estimated_prompt_tokens']=estimate
  print('Shapes:',len(cat),'join candidates:',len(edges),'estimated tokens:',estimate,'budget:',budget,flush=True)
  if estimate>budget:raise ValueError('Prompt over budget; reduce --max-shapes')
  parts=[];last={}
  with requests.post(args.ollama_url.rstrip('/')+'/api/chat',json={'model':args.model,'stream':True,'format':'json','options':{'temperature':0,'num_ctx':args.num_ctx,'num_predict':args.num_predict},'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':payload}]},timeout=(10,args.ollama_timeout),stream=True) as response:
   response.raise_for_status()
   for line in response.iter_lines():
    if not line:continue
    e=json.loads(line)
    if e.get('error'):raise RuntimeError(e['error'])
    parts.append(e.get('message',{}).get('content',''))
    if e.get('done'):report['completed']=True;last=e;break
  report['raw_model_response']=''.join(parts)
  report['ollama_stats']={k:last.get(k) for k in ('prompt_eval_count','eval_count','total_duration')}
  if not report['completed']:raise ValueError('Ollama stream incomplete')
  report['plan']=json.loads(report['raw_model_response'])
  report['plan_issues']=validate(report['plan'],cat,edges)
  if report['plan_issues']:print('Plan rejected:',report['plan_issues'],flush=True)
  else:
   query=compile_plan(report['plan'],edges);report['generated_sparql']=query
   print('Compiled query:\n'+query,flush=True)
   if not args.skip_execution:
    r=requests.post(args.graphdb_url,data={'query':query},headers={'Accept':'application/sparql-results+json'},timeout=60);r.raise_for_status()
    report['graphdb_bindings']=r.json()['results']['bindings'];report['binding_count']=len(report['graphdb_bindings'])
    print('GraphDB rows:',report['binding_count'],flush=True)
 except Exception as exc:
  report['error']=type(exc).__name__+': '+str(exc);print('ERROR:',report['error'],file=sys.stderr,flush=True)
 finally:
  report['elapsed_seconds']=round(time.monotonic()-start,2)
  path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
  print('Audit saved:',path,flush=True)
 return int(bool(report['error'] or report['plan_issues'] or not report['completed']))
if __name__=='__main__':sys.exit(main())
