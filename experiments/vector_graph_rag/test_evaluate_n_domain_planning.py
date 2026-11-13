"""Unit tests for 33-question N-domain feasibility audit."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'planning_audit', Path(__file__).with_name('10_evaluate_n_domain_planning.py'))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

Q1 = 'What is an asset identifier?'
Q2 = 'Which engineeringbom records match ecad devices?'
GOLD = [
    {'question': Q1, 'expected_domains': ['assetinventory'],
     'gold_concepts': [{'domain': 'assetinventory', 'uri': 'urn:a'}]},
    {'question': Q2, 'expected_domains': ['engineeringbom', 'ecad'],
     'gold_concepts': [{'domain': 'engineeringbom', 'uri': 'urn:b'},
                       {'domain': 'ecad', 'uri': 'urn:c'}]},
]
INDEX = {'concepts': [{'domain': 'assetinventory', 'uri': 'urn:a'},
                      {'domain': 'engineeringbom', 'uri': 'urn:b'},
                      {'domain': 'ecad', 'uri': 'urn:c'}]}
RETRIEVAL = {'results': [
    {'question': Q1, 'hybrid': {'hits': [{'domain': 'assetinventory', 'uri': 'urn:a'}]}},
    {'question': Q2, 'hybrid': {'hits': [
        {'domain': 'engineeringbom', 'uri': 'urn:b'},
        {'domain': 'ecad', 'uri': 'urn:c'}]}},
]}


class AuditTests(unittest.TestCase):
    def test_single_domain_not_counted_as_n_domain_failure(self):
        with patch.object(audit, 'compile_n_domain', side_effect=ValueError('No plan')) as planner:
            result = audit.evaluate(GOLD, RETRIEVAL, INDEX, {})
        self.assertEqual(result['summary']['single_domain_out_of_scope'], 1)
        self.assertEqual(result['summary']['multi_domain_abstained'], 1)
        self.assertEqual(planner.call_count, 1)

    def test_planner_receives_exact_oracle_domains(self):
        with patch.object(audit, 'compile_n_domain', return_value={
            'sparql': 'SELECT ...', 'mapping_status': 'candidate_pending_semantic_approval'}) as planner:
            result = audit.evaluate(GOLD, RETRIEVAL, INDEX, {}, allow_candidate=True)
        self.assertEqual(result['summary']['multi_domain_ready'], 1)
        self.assertEqual(planner.call_args.args[3], {'engineeringbom', 'ecad'})
        self.assertTrue(planner.call_args.args[4])

    def test_retrieval_missing_domain_abstains_without_planner(self):
        missing = {'results': [RETRIEVAL['results'][0],
                              {'question': Q2, 'hybrid': {'hits': [
                                  {'domain': 'engineeringbom', 'uri': 'urn:b'}]}}]}
        with patch.object(audit, 'compile_n_domain') as planner:
            result = audit.evaluate(GOLD, missing, INDEX, {})
        self.assertFalse(result['results'][1]['domain_coverage'])
        planner.assert_not_called()


if __name__ == '__main__':
    unittest.main()
