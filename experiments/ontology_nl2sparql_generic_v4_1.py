#!/usr/bin/env python3
"""Generic v4.1: normalized variables, grounded filters and fail-closed unsupported handling."""
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
   terms=tokens(d['domain']+' '+str(shape.get('label') or '')+' '+str(shape.get('description') or '')+' '+' '.join(local(x['predicate'])+' '+str(x.get('label') or '')+' '+str(x.get('description') or '') for x in p))
   score=3*len(q&terms)+5*bool(d['domain'] in required)+sum(8 for c in concepts(question) if any(set(c['tokens'])<=tokens(local(x['predicate'])) for x in p))
   if score and (not required or d['domain'] in required):scored.append((score,d['domain'],shape))
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
  result[k]={'domain':d,'shape':shape['uri'],'label':shape.get('label'),'description':shape.get('description'),'properties':[{'predicate':p['predicate'],'label':p.get('label'),'description':p.get('description'),'kind':p.get('kind')} for p in shape['properties']]}
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
SYSTEM="""Return JSON plan for an unseen engineering question using ONLY supplied SHACL properties and their authored semantic descriptions. Choose requested output fields and explicit filters. NEVER write joins or SPARQL: the compiler chooses minimal joins. Output exactly keys fields, filters, unsupported. fields are {name,shape,predicate}; filters are {shape,predicate,contains} for explicitly requested substring matching (including identifiers) or {shape,predicate,equals} for explicitly supplied exact values. Names are safe unique SPARQL variables. Match field semantics exactly: equipment tags use hasEquipmentTag, operational references use hasOperationalReference, identifiers use hasAssetIdentifier, not hasRelatedAssetIdentifier. Do not invent predicates. Account for EVERY requested_outputs phrase in fields or unsupported. If an output is unavailable, mark it unsupported; do not invent a predicate or substitute an unrelated property. Nonempty unsupported means the entire request is rejected. Domain connectivity is handled by compiler. JSON only."""
def minimum_joins(plan,cat,edges,required):
 """Find shortest join tree covering selected shapes and at least one shape per required domain.
 For 10 or fewer shapes, enumerate connected subsets using BFS, favoring fewer joins."""
 from collections import deque
 terminals={f['shape'] for f in plan['fields']+plan['filters']}
 if not terminals:raise ValueError('No selected shapes')
 allnodes=set(cat)
 missing_domains=set(required)-{cat[x]['domain'] for x in terminals}
 # Every required domain needs one representative, chosen by shortest connectivity.
 target_domains=set(required)
 start=frozenset({sorted(terminals)[0]})
 queue=deque([(start,())]);seen={start}
 while queue:
  nodes,path=queue.popleft()
  if terminals<=nodes and target_domains<={cat[x]['domain'] for x in nodes}:
   return list(path),nodes
  for eid,e in sorted(edges.items()):
   a,b=e['left'],e['right']
   if (a in nodes) == (b in nodes):continue
   nxt=frozenset(set(nodes)|{a,b})
   if nxt not in seen:
    seen.add(nxt);queue.append((nxt,path+(eid,)))
 raise ValueError('No ontology-supported equality-join tree connects selected shapes and required domains')

def singular_token(token):
 return token[:-1] if len(token)>3 and token.endswith('s') and not token.endswith('ss') else token

def normalized_words(text):
 text=re.sub(r'\b([A-Z]{2,})s\b',r'\1',text or '')
 text=re.sub(r'([A-Z])([A-Z][a-z])',r'\1 \2',text)
 text=re.sub(r'([a-z0-9])([A-Z])',r'\1 \2',text)
 return [singular_token(x) for x in re.findall(r'[a-z0-9]+',text.lower())]

def substring_requested(question,predicate,value):
 """Explicit contains intent, literal grounding, and predicate phrase in question."""
 words=normalized_words(question)
 if not set(words)&{'contains','contain','containing','include','including','includes','substring'}:
  return False
 if not isinstance(value,str) or not value.strip() or value.lower() not in question.lower():
  return False
 prop=[x for x in normalized_words(local(predicate)) if x!='has']
 if not prop:return False
 return any(words[i:i+len(prop)]==prop for i in range(len(words)-len(prop)+1))

def normalize_output_names(plan):
 """Compiler-owned variable names; never change selected shapes or predicates."""
 if not isinstance(plan,dict) or not isinstance(plan.get('fields'),list):return plan
 seen=set()
 for i,f in enumerate(plan['fields']):
  if not isinstance(f,dict) or not isinstance(f.get('predicate'),str):continue
  stem=local(f['predicate'])
  stem=re.sub(r'[^A-Za-z0-9_]', '_',stem)
  if stem.startswith('has') and len(stem)>3:stem=stem[3:4].lower()+stem[4:]
  if not re.match(r'^[A-Za-z]',stem):stem='field'+str(i+1)
  name=stem;counter=2
  while name in seen:
   name=stem+'_'+str(counter);counter+=1
  f['name']=name;seen.add(name)
 return plan


def requested_outputs(question):
 """Extract coordinated projection phrases independently of the model and SHACL."""
 q=re.sub(r'([a-z])([A-Z])',r'\1 \2',question)
 m=re.search(r'\b(?:list|show|return|display|give|retrieve|select)\b',q,re.I)
 if not m:return []
 q=q[m.end():]
 q=re.split(r'\b(?:where|whose|having|filtered by|such that)\b',q,maxsplit=1,flags=re.I)[0]
 q=re.split(r'[.;?]',q,maxsplit=1)[0]
 chunks=re.split(r'\s*,\s*|\s+and\s+',q,flags=re.I)
 result=[]
 for chunk in chunks:
  chunk=re.sub(r'^\s*(?:and|the|all|their|each|its)\s+','',chunk.strip(),flags=re.I)
  chunk=re.sub(r'^\s*(?:within|for|in)\s+.*?\b(?:show|list)\b\s*','',chunk,flags=re.I)
  if chunk:result.append(chunk)
 return result

def projection_signature(phrase):
 """Normalize only grammatical and domain qualifiers, never semantic field types."""
 words=normalized_words(phrase)
 qualifiers={'opc','ua','connectivity','dexpi','ecad','bom','inventory','catalog',
             'engineeringbom','assetinventory','productcatalog','opcuaconnectivity',
             'server','mapping','their','the','a','an','each','all','of','for','in'}
 # 'engineering' is NOT a qualifier: engineering function ID differs from function reference.
 return [w for w in words if w not in qualifiers]

def projection_covered(phrase,selected):
 """Require every meaningful requested term to occur in a selected predicate."""
 target=set(projection_signature(phrase))
 if not target:return False
 for _,_,predicate in selected:
  actual=set(normalized_words(local(predicate)))-{'has'}
  if target<=actual:return True
 return False

def repair_field_shapes(plan,cat):
 """Repair a model's shape ID only when the selected predicate has one unique owner."""
 if not isinstance(plan,dict) or not isinstance(plan.get('fields'),list):return plan
 for f in plan['fields']:
  if not isinstance(f,dict) or not isinstance(f.get('predicate'),str):continue
  p=f['predicate']
  owners=[sid for sid,shape in cat.items() if any(x['predicate']==p for x in shape['properties'])]
  if len(owners)==1 and f.get('shape')!=owners[0]:f['shape']=owners[0]
 return plan

def validate(plan,cat,required,requested,question):
 errors=[]
 if not isinstance(plan,dict) or set(plan)!={'fields','filters','unsupported'}:return ['Invalid plan keys']
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
  if 'contains' in f and not substring_requested(question,p,v):errors.append('Substring filter not explicitly grounded in question')
  if isinstance(v,str) and v.lower() not in question.lower():errors.append('Filter value not grounded in question')
  used.add(s)
 if not plan['fields']:errors.append('No output fields')
 if any(not isinstance(x,str) for x in plan['unsupported']):errors.append('Invalid unsupported')
 if plan['unsupported']:errors.append('Unsupported requirements: '+', '.join(str(x) for x in plan['unsupported']))
 # Do not validate semantic coverage by lexical overlap between question phrases
 # and predicate local names. The LLM chooses grounded fields; ontology membership
 # and structural constraints are checked here. Semantic correctness is evaluated
 # independently against reference queries/answers.
 for n,s,p in selected:
  kind=next(x.get('kind') for x in cat[s]['properties'] if x['predicate']==p)
  if kind=='object' and tokens(n)&{'tag','tags','identifier','identifiers','reference','references','name','names'}:
   errors.append('Object property used for scalar output: '+n)
  if tokens(n)&{'tag','tags'} and 'tag' not in tokens(local(p)):
   errors.append('Tag output mapped to non-tag predicate: '+local(p))

 return errors
def compile_plan(plan,edges,selected_joins):
 lines=[]
 for j in selected_joins:
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
 ap.add_argument('--output',default='reports/ontology_nl2sparql_generic_v4_1.json')
 args=ap.parse_args();start=time.monotonic()
 path=Path(args.output)
 if not path.is_absolute():path=ROOT/path
 if path.exists():path=path.with_name(path.stem+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+path.suffix)
 path.parent.mkdir(parents=True,exist_ok=True)
 report={'method':'generic_v4_1_ontology_structural_validation','question':args.question,'model':args.model,'completed':False,'plan':None,'raw_model_response':None,'generated_sparql':None,'plan_issues':[],'graphdb_bindings':None,'binding_count':None,'error':None}
 try:
  schema=extract();required=required_domains(schema,args.question);requested=concepts(args.question);cat=catalog(schema,args.question,args.max_shapes,required);edges=joins(cat)
  report['validation_policy']='ontology_structural_without_lexical_projection_coverage'
  report['schema_sources']=[{'domain':d['domain'],'file':d['source_file'],'sha256':d['source_sha256']} for d in schema['domains']]
  report['candidate_shapes']=cat;report['join_candidates']=edges;report['required_domains']=required;report['requested_concepts']=requested;report['requested_outputs']=requested_outputs(args.question)
  if not cat:raise ValueError('No ontology shapes matched question')
  payload=json.dumps({'question':args.question,'required_domains':required,'requested_concepts':requested,'requested_outputs':requested_outputs(args.question),'shapes':cat,'plan_format':{'fields':[{'name':'outputName','shape':'shape ID','predicate':'full IRI'}],'filters':[],'unsupported':[]}},separators=(',',':'))
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
  report['plan']=normalize_output_names(repair_field_shapes(json.loads(report['raw_model_response']),cat))
  report['plan_issues']=validate(report['plan'],cat,required,requested,args.question)
  if report['plan_issues']:print('Plan rejected:',report['plan_issues'],flush=True)
  else:
   selected_joins,joined_shapes=minimum_joins(report['plan'],cat,edges,required)
   report['selected_joins']=selected_joins;report['joined_shapes']=sorted(joined_shapes)
   query=compile_plan(report['plan'],edges,selected_joins);report['generated_sparql']=query
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
