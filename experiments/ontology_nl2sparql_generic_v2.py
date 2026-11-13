#!/usr/bin/env python3
"""Generic v2: domain-balanced schema retrieval and fail-closed semantic checks."""
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
STOP={'the','and','for','with','from','show','list','return','what','which','all','across','of','in','to','their','represented'}
def required_domains(schema,question):
 q=tokens(question); low=question.lower()
 return [d['domain'] for d in schema['domains'] if d['domain'] in q or
  (d['domain']=='assetinventory' and ('inventory' in q or 'asset inventory' in low)) or
  (d['domain']=='opcuaconnectivity' and ('opc' in q or 'opc ua' in low)) or
  (d['domain']=='engineeringbom' and 'bom' in q) or
  (d['domain']=='productcatalog' and 'catalog' in q)]
def concepts(question):
 q=' '.join(re.findall(r'[a-z0-9]+',re.sub(r'([a-z])([A-Z])',r'\1 \2',question).lower()))
 phrases=('equipment tag','operational reference','asset identifier','local id','signal name','manufacturer part number','manufacturer name','part number')
 return [{'phrase':p,'tokens':sorted(tokens(p))} for p in phrases if re.search(r'\b'+re.escape(p)+r's?\b',q)]
def catalog(schema,question,limit,required):
 if len(required)>limit:raise ValueError('max-shapes less than required domain count')
 q=tokens(question)-STOP
 scored=[]
 for d in schema['domains']:
  for shape in d['node_shapes']:
   p=shape['properties']
   terms=tokens(d['domain']+' '+str(shape.get('label') or '')+' '+' '.join(local(x['predicate'])+' '+str(x.get('label') or '') for x in p))
   score=3*len(q&terms)+5*bool(d['domain'] in required)
   if score:scored.append((score,d['domain'],shape))
 scored.sort(key=lambda x:(-x[0],x[1],x[2]['uri']))
 picked=[];seen=set()
 for d in required:
  hit=next((x for x in scored if x[1]==d),None)
  if not hit:raise ValueError('No candidate shape for required domain '+d)
  picked.append(hit);seen.add((hit[1],hit[2]['uri']))
 for x in scored:
  if len(picked)>=limit:break
  key=(x[1],x[2]['uri'])
  if key not in seen:picked.append(x);seen.add(key)
 result={}
 for _,d,shape in picked:
  k='s'+str(len(result))
  result[k]={'domain':d,'shape':shape['uri'],'properties':[{'predicate':p['predicate'],'label':p.get('label'),'kind':p.get('kind')} for p in shape['properties']]}
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
SYSTEM="""Translate an unseen engineering question into JSON plan ONLY. Use only supplied SHACL properties and shape IDs. Do not write SPARQL, invent predicates, assume data values or expected answers. Fields: objects {name,shape,predicate}, with safe unique variable names. Joins: array of supplied join IDs only; choose only those needed to connect all selected shapes. Filters: objects {shape,predicate,contains} only for explicitly requested lexical text and descriptive predicates (name/label/description/designation/signal); alternatively {shape,predicate,equals} for user-supplied exact identifier. Unsupported: array of unmet requirements. Respect required_domains. Equipment tags must use EquipmentTag, never ConnectionPoints. Do not produce disconnected patterns or fabricate a cross-shape path. Join candidates are unproven identifier-equality hypotheses. Exactly four JSON keys: fields, joins, filters, unsupported. No extra text."""
def validate(plan,cat,edges,required,requested,question):
 errors=[]
 if not isinstance(plan,dict) or set(plan)!={'fields','joins','filters','unsupported'}:return ['Invalid plan keys']
 if any(not isinstance(plan[k],list) for k in plan):return ['Plan values must be arrays']
 used=set();names=set();selected=[]
 for f in plan['fields']:
  if not isinstance(f,dict) or set(f)!={'name','shape','predicate'}:errors.append('Bad field');continue
  n,s,p=f['name'],f['shape'],f['predicate']
  if not isinstance(n,str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_]*',n) or n in names:errors.append('Invalid variable')
  names.add(n)
  if s not in cat or p not in {x['predicate'] for x in cat[s]['properties']}:errors.append('Undeclared field property')
  else:used.add(s);selected.append((n,s,p))
 for f in plan['filters']:
  if not isinstance(f,dict) or set(f) not in ({'shape','predicate','contains'},{'shape','predicate','equals'}):errors.append('Bad filter');continue
  s,p=f['shape'],f['predicate']
  if s not in cat or p not in {x['predicate'] for x in cat[s]['properties']}:errors.append('Undeclared filter property');continue
  v=f.get('contains',f.get('equals'))
  if not isinstance(v,str) or not v.strip() or len(v)>200:errors.append('Bad filter value')
  if 'contains' in f and not tokens(local(p))&{'name','label','description','designation','signal'}:errors.append('Non-descriptive contains filter')
  if isinstance(v,str) and v.lower() not in question.lower():errors.append('Filter value not grounded in question')
  used.add(s)
 if not plan['fields']:errors.append('No output fields')
 if any(not isinstance(x,str) for x in plan['unsupported']):errors.append('Invalid unsupported')
 if len(set(str(x) for x in plan['joins']))!=len(plan['joins']):errors.append('Repeated joins')
 for jid in plan['joins']:
  if not isinstance(jid,str) or jid not in edges:errors.append('Unknown join')
 missing=set(required)-{cat[s]['domain'] for s in used}
 if missing:errors.append('Missing requested domains: '+', '.join(sorted(missing)))
 for c in requested:
  if not any(set(c['tokens'])<=tokens(local(p)) for _,_,p in selected):
   errors.append('Missing semantic output: '+c['phrase'])
 for n,s,p in selected:
  kind=next(x.get('kind') for x in cat[s]['properties'] if x['predicate']==p)
  if kind=='object' and tokens(n)&{'tag','tags','identifier','identifiers','reference','references','name','names'}:
   errors.append('Object property used for scalar output: '+n)
  if tokens(n)&{'tag','tags'} and 'tag' not in tokens(local(p)):
   errors.append('Tag output mapped to non-tag predicate: '+local(p))
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
 ap.add_argument('--output',default='reports/ontology_nl2sparql_generic_v2.json')
 args=ap.parse_args();start=time.monotonic()
 path=Path(args.output)
 if not path.is_absolute():path=ROOT/path
 if path.exists():path=path.with_name(path.stem+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+path.suffix)
 path.parent.mkdir(parents=True,exist_ok=True)
 report={'method':'generic_v2_balanced_semantic_fail_closed','question':args.question,'model':args.model,'completed':False,'plan':None,'raw_model_response':None,'generated_sparql':None,'plan_issues':[],'graphdb_bindings':None,'binding_count':None,'error':None}
 try:
  schema=extract();required=required_domains(schema,args.question);requested=concepts(args.question);cat=catalog(schema,args.question,args.max_shapes,required);edges=joins(cat)
  report['schema_sources']=[{'domain':d['domain'],'file':d['source_file'],'sha256':d['source_sha256']} for d in schema['domains']]
  report['candidate_shapes']=cat;report['join_candidates']=edges;report['required_domains']=required;report['requested_concepts']=requested
  if not cat:raise ValueError('No ontology shapes matched question')
  payload=json.dumps({'question':args.question,'required_domains':required,'requested_concepts':requested,'shapes':cat,'candidate_joins':edges,'plan_format':{'fields':[{'name':'outputName','shape':'shape ID','predicate':'full IRI'}],'joins':['join ID'],'filters':[],'unsupported':[]}},separators=(',',':'))
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
  report['plan_issues']=validate(report['plan'],cat,edges,required,requested,args.question)
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
