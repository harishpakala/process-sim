import sys, unittest
from pathlib import Path
from unittest.mock import patch
import types
here = Path(__file__).resolve().parent
pkg = types.ModuleType('dtwise')
pkg.__path__ = [str(here), str(here.parent / 'dtwise_B51_patch')]
sys.modules['dtwise'] = pkg
from dtwise import structured_join

class Schema:
    concepts = [{'domain':'dexpi'}, {'domain':'opcuaconnectivity'}]

class Tests(unittest.TestCase):
    question = 'Get opcuaconnectivity SignalNames for dexpi InstrumentationFunction LocalId FI-001 using AssetIdentifier.'
    def setUp(self):
        def candidate(domain, entity, extra):
            def prop(label):
                return {'labels':[label], 'predicate':f'https://example.org/{domain}/has{label}', '_hop':{'evidence_ids':['ev']}}
            return {'id':domain,'domain':domain,'target_labels':[entity], 'root':domain+'Root',
                    'end':domain+'End','predicates':['has'+entity], '_hops':[{'evidence_ids':['path']}],
                    'terminal':[prop('AssetIdentifier'),prop(extra)]}
        self.catalog = [candidate('dexpi','InstrumentationFunction','LocalId'),
                        candidate('opcuaconnectivity','SignalMapping','SignalName')]
        self.intent = {'operation':'identifier_equality','join_key':'AssetIdentifier',
                       'output_domain':'opcuaconnectivity','output_property':'SignalName',
                       'explicit_equality_authorized':True,
                       'entity_constraints':[{'domain':'dexpi','entity':'InstrumentationFunction'},
                                             {'domain':'dexpi','entity':'InstrumentationFunction'}],
                       'filters':[{'domain':'dexpi','property':'LocalId','operator':'eq','value':'FI-001'}]}
    def plan(self, intent):
        with patch.object(structured_join,'validate_hops',return_value=True):
            return structured_join.plan_structured_join(self.question,self.catalog,Schema(),
                host='',model='',timeout=1,interpret_join=lambda q,c:intent)
    def test_repeated_identical_entity_allowed_and_filter_preserved(self):
        plan = self.plan(self.intent)
        self.assertEqual(plan['filters'][0]['value'],'FI-001')
        self.assertEqual(plan['filters'][0]['domain'],'dexpi')
    def test_repeated_equivalent_entity_allowed(self):
        # The second label differs only in case, but denotes the same entity.
        entries = list(self.intent['entity_constraints'])
        entries[1] = dict(entries[1],entity='instrumentationfunction')
        self.assertEqual(self.plan(dict(self.intent,entity_constraints=entries))['join_type'], 'cross_domain_projection')
    def test_conflicting_entity_constraints_rejected(self):
        entries = list(self.intent['entity_constraints'])
        entries[1] = dict(entries[1], entity='DifferentEntity')
        with patch.object(structured_join, '_mentioned', return_value=True):
            with self.assertRaisesRegex(ValueError, 'Conflicting entity constraints'):
                self.plan(dict(self.intent, entity_constraints=entries))
    def test_missing_filter_still_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unrepresented identifier-like literal'):
            self.plan(dict(self.intent,filters=[]))
    def test_invented_value_still_rejected(self):
        bad = [dict(self.intent['filters'][0],value='FI-999')]
        with self.assertRaisesRegex(ValueError,'Filter value not explicitly present'):
            self.plan(dict(self.intent,filters=bad))
    def test_b51_no_filter(self):
        q = 'Get opcuaconnectivity SignalNames associated with dexpi InstrumentationFunctions using AssetIdentifier.'
        with patch.object(structured_join,'validate_hops',return_value=True):
            plan = structured_join.plan_structured_join(q,self.catalog,Schema(),host='',model='',timeout=1,
                interpret_join=lambda q,c:dict(self.intent,filters=[]))
        self.assertEqual(plan['filters'],[])

if __name__=='__main__': unittest.main()
