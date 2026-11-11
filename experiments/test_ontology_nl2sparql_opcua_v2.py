#!/usr/bin/env python3
"""Offline regression tests for ontology-derived OPC UA traversal."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import ontology_nl2sparql_opcua_v2 as opc
from q13_extract_focused_schema import extract

NS='https://example.org/opcuaconnectivity/'
def field(shape,property_name):
 return {'name':property_name[3:4].lower()+property_name[4:],
         'shape':shape,'predicate':NS+property_name}

class OpcuaTraversal(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  schema=extract()
  cls.cat=opc.catalog(schema,'Show OPC UA server and signal mapping information',10,['opcuaconnectivity'])
  cls.edges=opc.joins(cls.cat)
  cls.by_property={opc.base.local(p['predicate']):sid
                   for sid,s in cls.cat.items() for p in s['properties']}
 def test_all_five_shapes_available(self):
  self.assertEqual(len(self.cat),5)
 def test_four_ontology_object_edges(self):
  self.assertEqual({opc.base.local(e['predicate']) for e in self.edges.values()},
                   {'hasServers','hasServer','hasSignalMappings','hasSignalMapping'})
  self.assertTrue(all(e['kind']=='shacl_object_path' for e in self.edges.values()))
 def test_server_and_signal_mapping_traverse_shared_root(self):
  a=self.by_property['hasEndpointUrl']
  b=self.by_property['hasSignalName']
  plan={'fields':[field(a,'hasEndpointUrl'),field(b,'hasSignalName')],
        'filters':[],'unsupported':[]}
  selected,nodes=opc.base.minimum_joins(plan,self.cat,self.edges,['opcuaconnectivity'])
  self.assertEqual(len(selected),4)
  query=opc.compile_plan(plan,self.edges,selected)
  for name in ('hasServers','hasServer','hasSignalMappings','hasSignalMapping'):
   self.assertIn('<'+NS+name+'>',query)
  self.assertIn('<'+NS+'hasEndpointUrl>',query)
  self.assertIn('<'+NS+'hasSignalName>',query)
 def test_single_shape_needs_no_traversal(self):
  sid=self.by_property['hasSignalName']
  plan={'fields':[field(sid,'hasSignalName'),field(sid,'hasOPCUANodeId')],
        'filters':[],'unsupported':[]}
  selected,_=opc.base.minimum_joins(plan,self.cat,self.edges,['opcuaconnectivity'])
  self.assertEqual(selected,[])
  query=opc.compile_plan(plan,self.edges,selected)
  self.assertNotIn('<'+NS+'hasSignalMappings>',query)
 def test_server_shape_properties_same_subject(self):
  sid=self.by_property['hasEndpointUrl']
  plan={'fields':[field(sid,'hasEndpointUrl'),field(sid,'hasEndpointStatus')],
        'filters':[],'unsupported':[]}
  selected,_=opc.base.minimum_joins(plan,self.cat,self.edges,['opcuaconnectivity'])
  self.assertEqual(selected,[])
  self.assertIn('SELECT DISTINCT',opc.compile_plan(plan,self.edges,selected))

if __name__=='__main__':unittest.main()
