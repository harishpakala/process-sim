"""Offline tests: structured filter preservation and fail-closed behavior."""
import sys, unittest
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'dtwise_B51_patch'))
# The production package name is dtwise; use local package overlay for tests.
import types
pkg = types.ModuleType('dtwise'); pkg.__path__ = [str(ROOT / 'dtwise_B51_patch'), str(ROOT)]
sys.modules['dtwise'] = pkg
import structured_join

class FakeSchema:
    concepts = [{'domain':'dexpi'}, {'domain':'opcuaconnectivity'}]

class TestB52(unittest.TestCase):
    question = 'Get opcuaconnectivity SignalNames for dexpi InstrumentationFunction LocalId FI-001 using AssetIdentifier.'
    def setUp(self):
        def candidate(domain, entity, output):
            def prop(label):
                return {'id':label,'labels':[label], 'predicate':'https://example.org/'+domain+'/has'+label,
                        '_hop':{'evidence_ids':['ev'+label]}}
            return {'id':domain,'domain':domain,'target_labels':[entity],
                    'root':domain+'Root','end':domain+'End', 'predicates':['has'+entity],
                    '_hops':[{'evidence_ids':['path']}],
                    'terminal':[prop('AssetIdentifier'), prop(output)]}
        self.catalog=[candidate('dexpi','InstrumentationFunction','LocalId'),
                      candidate('opcuaconnectivity','SignalMapping','SignalName')]
        self.intent={'operation':'identifier_equality','join_key':'AssetIdentifier',
                     'output_domain':'opcuaconnectivity','output_property':'SignalName',
                     'entity_constraints':[{'domain':'dexpi','entity':'InstrumentationFunction'}],
                     'explicit_equality_authorized':True,
                     'filters':[{'domain':'dexpi','property':'LocalId','operator':'eq','value':'FI-001'}]}
    def plan(self,intent):
        with patch.object(structured_join,'validate_hops',return_value=True):
            return structured_join.plan_structured_join(self.question,self.catalog,FakeSchema(),
                     host='',model='',timeout=1,interpret_join=lambda q,c:intent)
    def test_b52_preserves_filter(self):
        plan=self.plan(self.intent)
        self.assertEqual(plan['filters'][0]['value'],'FI-001')
        self.assertEqual(plan['filters'][0]['domain'],'dexpi')
        self.assertTrue(plan['filters'][0]['predicate'].endswith('/hasLocalId'))
    def test_omitted_filter_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unrepresented identifier-like literal'):
            self.plan(dict(self.intent,filters=[]))
    def test_invented_filter_value_rejected(self):
        with self.assertRaisesRegex(ValueError,'not explicitly present'):
            self.plan(dict(self.intent,filters=[dict(self.intent['filters'][0],value='FI-999')]))
    def test_b51_without_filter(self):
        q='Get opcuaconnectivity SignalNames associated with dexpi InstrumentationFunctions using AssetIdentifier.'
        with patch.object(structured_join,'validate_hops',return_value=True):
            plan=structured_join.plan_structured_join(q,self.catalog,FakeSchema(),host='',model='',timeout=1,
                    interpret_join=lambda q,c:dict(self.intent,filters=[]))
        self.assertEqual(plan['filters'],[])

if __name__=='__main__': unittest.main()

class TestCompiler(unittest.TestCase):
    def test_filter_is_compiled_on_source(self):
        import cross_domain_projection as compiler
        class Schema:
            def shacl_paths(self, shape, max_depth, domain):
                if max_depth == 1 and shape.endswith('End'):
                    return [[{'to_shape':None,'property':f'https://example.org/{domain}/has{label}',
                              'evidence_ids':['ev'+label]}] for label in ('AssetIdentifier','LocalId','SignalName')]
                return [[{'to_shape':shape.replace('Root','End'),
                          'property':'hasInstrumentationFunction' if domain=='dexpi' else 'hasSignalMapping',
                          'evidence_ids':['path']}]]
        plan={'query_type':'SELECT','intent':'list','join_type':'cross_domain_projection',
              'source':{'domain':'dexpi','root':'dexpiRoot','end_shape':'dexpiEnd',
                        'predicates':['hasInstrumentationFunction'],'evidence_ids':['path'],
                        'key_predicate':'https://example.org/dexpi/hasAssetIdentifier',
                        'key_evidence_ids':['evAssetIdentifier']},
              'target':{'domain':'opcuaconnectivity','root':'opcuaconnectivityRoot','end_shape':'opcuaconnectivityEnd',
                        'predicates':['hasSignalMapping'],'evidence_ids':['path'],
                        'key_predicate':'https://example.org/opcuaconnectivity/hasAssetIdentifier',
                        'key_evidence_ids':['evAssetIdentifier']},
              'projection':{'predicate':'https://example.org/opcuaconnectivity/hasSignalName','evidence_ids':['evSignalName']},
              'filters':[{'domain':'dexpi','predicate':'https://example.org/dexpi/hasLocalId',
                          'evidence_ids':['evLocalId'],'operator':'eq','value':'FI-001'}]}
        with patch.object(compiler,'validate_hops',return_value=True):
            query=compiler.compile_cross_domain_projection(plan,Schema(),200,'all_named',None,False,False,
                                                               lambda uri:'<'+uri+'>')
        self.assertIn('?entity0 <https://example.org/dexpi/hasLocalId> ?filterValue0 .',query)
        self.assertIn('FILTER(STR(?filterValue0) = "FI-001")',query)
        self.assertIn('GRAPH ?graph1',query)
        self.assertIn(' ?joinKey .',query)
