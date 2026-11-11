#!/usr/bin/env python3
"""OPC UA v2: SHACL-derived nested object traversal, extending v4.1.

Uses only extracted OWL/SHACL shapes; no instance data or reference queries.
For OPC UA-only questions, retrieve all OPC UA shapes (within max-shapes) and
require that model outputs remain inside OPC UA.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import ontology_nl2sparql_generic_v4_1 as base

ORIGINAL_CATALOG=base.catalog
ORIGINAL_VALIDATE=base.validate
ORIGINAL_SYSTEM=base.SYSTEM

def opc_only(question,required):
 return bool(required) and set(required)=={'opcuaconnectivity'}

def catalog(schema,question,limit,required):
 if not opc_only(question,required):
  return ORIGINAL_CATALOG(schema,question,limit,required)
 domain=next(d for d in schema['domains'] if d['domain']=='opcuaconnectivity')
 shapes=domain['node_shapes']
 if len(shapes)>limit:
  raise ValueError('OPC UA schema has '+str(len(shapes))+
                   ' shapes; increase --max-shapes to avoid silently losing ontology context')
 # Stable order, not model or instance-dependent. All OPC UA property paths available.
 result={}
 for shape in sorted(shapes,key=lambda s:s['uri']):
  k='s'+str(len(result))
  result[k]={'domain':'opcuaconnectivity','shape':shape['uri'],
             'properties':[{'predicate':p['predicate'],'label':p.get('label'),
                            'kind':p.get('kind')} for p in shape['properties']]}
 return result

def validate(plan,cat,required,requested,question):
 issues=ORIGINAL_VALIDATE(plan,cat,required,requested,question)
 if opc_only(question,required):
  # Fail closed if the plan somehow references a non-OPC UA shape.
  for f in plan.get('fields',[])+plan.get('filters',[]):
   if isinstance(f,dict) and f.get('shape') in cat and cat[f['shape']]['domain']!='opcuaconnectivity':
    issues.append('OPC UA-only request uses non-OPC UA property')
 return issues

base.catalog=catalog
base.validate=validate
base.SYSTEM=ORIGINAL_SYSTEM+(
 ' For OPC UA Connectivity questions, distinguish Server properties '
 '(endpoint URL, endpoint status, namespace URI, ECAD connection-point reference status) '
 'from SignalMapping properties (OPC UA node ID, browse path, signal name, '
 'signal direction, mapping status, engineering function, asset identifier, '
 'related inventory asset identifier). Select only the exact SHACL property '
 'for each requested concept. Never confuse a NodeId with a live node value, '
 'a configured endpoint with a live connection, or mapping status with '
 'real-time telemetry. Do not invent live OPC UA readings or availability. '
 'Nested Server/SignalMapping collections use SHACL-derived object traversal; '
 'do not imply a relationship from merely selecting two shapes.')

# Derive object-property traversal exclusively from SHACL sh:node declarations.
# These are actual directed RDF links, not identifier-value equality guesses.
from rdflib import Graph, URIRef
from rdflib.namespace import RDF, SH
from q13_extract_focused_schema import BASE, FILES
import json

ORIGINAL_JOINS=base.joins
ORIGINAL_COMPILE=base.compile_plan

def joins(cat):
 if not cat or set(s['domain'] for s in cat.values())!={'opcuaconnectivity'}:
  return ORIGINAL_JOINS(cat)
 graph=Graph()
 graph.parse(str(BASE/FILES['opcuaconnectivity']),format='turtle')
 by_uri={s['shape']:sid for sid,s in cat.items()}
 edges={}
 for sid,s in sorted(cat.items()):
  shape=URIRef(s['shape'])
  for prop in graph.objects(shape,SH.property):
   target=graph.value(prop,SH.node)
   predicate=graph.value(prop,SH.path)
   if not isinstance(target,URIRef) or not isinstance(predicate,URIRef):
    continue
   if str(target) not in by_uri:
    continue
   if str(predicate) not in {p['predicate'] for p in s['properties']}:
    continue
   eid='j'+str(len(edges))
   edges[eid]={'left':sid,'right':by_uri[str(target)],
               'predicate':str(predicate),'kind':'shacl_object_path',
               'evidence':'sh:property / sh:path / sh:node'}
 return edges

def compile_plan(plan,edges,selected_joins):
 if not any(e.get('kind')=='shacl_object_path' for e in edges.values()):
  return ORIGINAL_COMPILE(plan,edges,selected_joins)
 lines=[]
 for eid in selected_joins:
  edge=edges[eid]
  if edge.get('kind')!='shacl_object_path':
   raise ValueError('Mixed traversal and identifier joins are unsupported')
  lines.append('?node_'+edge['left']+' <'+edge['predicate']+'> ?node_'+edge['right']+' .')
 for f in plan['fields']:
  lines.append('?node_'+f['shape']+' <'+f['predicate']+'> ?'+f['name']+' .')
 for i,f in enumerate(plan['filters']):
  variable='?filter_'+str(i)
  lines.append('?node_'+f['shape']+' <'+f['predicate']+'> '+variable+' .')
  if 'contains' in f:
   lines.append('FILTER(CONTAINS(LCASE(STR('+variable+')),LCASE('+json.dumps(f['contains'])+')))')
  else:
   lines.append('FILTER(STR('+variable+') = '+json.dumps(f['equals'])+')')
 query='SELECT DISTINCT '+' '.join('?'+f['name'] for f in plan['fields'])+' WHERE {\n  '+'\n  '.join(lines)+'\n}'
 base.parseQuery(query)
 return query

base.joins=joins
base.compile_plan=compile_plan

if __name__=='__main__':
 raise SystemExit(base.main())
