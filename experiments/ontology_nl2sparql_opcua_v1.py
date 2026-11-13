#!/usr/bin/env python3
"""OPC UA-focused extension of v4.1. Other domain behavior is unchanged.

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
 'Nested Server/SignalMapping collections require explicit traversal; '
 'do not imply a relationship from merely selecting two shapes.')
if __name__=='__main__':
 raise SystemExit(base.main())
