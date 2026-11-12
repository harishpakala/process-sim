"""Pure unit tests for the constrained planner (no Ollama or AAS dependencies)."""
import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).with_name('08_constrained_query_planner.py')
spec = importlib.util.spec_from_file_location('dtwise_constrained_planner', MODULE)
planner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(planner)

DOMAIN = 'productcatalog'
URI = 'https://example.org/productcatalog/hasManufacturerPartNumber'
EDGE = 'urn:edge:1'
INDEX = {
    'concepts': [{'domain': DOMAIN, 'uri': URI, 'kind': 'property'}],
    'shape_paths': [{'domain': DOMAIN, 'node_shape': 'urn:node', 'property_shape': 'urn:prop',
                     'path': URI, 'evidence': [EDGE]}],
    'relationships': [{'domain': DOMAIN, 'id': EDGE,
                       'subject': 'urn:prop', 'predicate': 'http://www.w3.org/ns/shacl#path',
                       'object': URI}],
}
HITS = [{'domain': DOMAIN, 'uri': URI}]

class PlannerTests(unittest.TestCase):
    def test_single_property_generates_minimal_select(self):
        result = planner.plan(INDEX, 'What is the manufacturer part number?', HITS)
        # The third positional argument is selected, not hits; test explicit selection below.
        self.assertEqual(result['status'], 'abstained')

    def test_validated_property(self):
        result = planner.plan(INDEX, 'What is the manufacturer part number?',
                              [{'domain': DOMAIN, 'uri': URI}], HITS)
        self.assertEqual(result['status'], 'ready')
        self.assertIn('?subject <' + URI + '> ?value', result['sparql'])
        self.assertNotIn('rdf:type', result['sparql'])
        self.assertFalse(result['safety']['query_executed'])

    def test_no_retrieval_support(self):
        result = planner.plan(INDEX, 'Question', [{'domain': DOMAIN, 'uri': URI}], [])
        self.assertEqual(result['status'], 'abstained')

    def test_no_cross_domain_join(self):
        result = planner.plan(INDEX, 'Cross-domain question',
                              [{'domain': DOMAIN, 'uri': URI},
                               {'domain': 'ecad', 'uri': 'https://example.org/ecad/hasDevice'}], HITS)
        self.assertEqual(result['status'], 'abstained')
        self.assertIsNone(result['sparql'])

    def test_missing_shacl_evidence(self):
        altered = dict(INDEX, relationships=[])
        result = planner.plan(altered, 'Question', [{'domain': DOMAIN, 'uri': URI}], HITS)
        self.assertEqual(result['status'], 'abstained')

    def test_iri_injection_rejected(self):
        result = planner.plan(INDEX, 'Question',
                              [{'domain': DOMAIN, 'uri': URI + '> ?s ?p ?o'}], HITS)
        self.assertEqual(result['status'], 'abstained')

if __name__ == '__main__':
    unittest.main()
