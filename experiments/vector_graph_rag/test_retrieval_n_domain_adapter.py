"""Adapter unit tests. Run from repository root with unittest discovery."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'dtwise_adapter', Path(__file__).with_name('09_retrieval_n_domain_adapter.py'))
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

Q = 'Which engineering components have inventory representations?'
INDEX = {'concepts': [
    {'domain': 'engineeringbom', 'uri': 'urn:bom'},
    {'domain': 'assetinventory', 'uri': 'urn:asset'},
    {'domain': 'ecad', 'uri': 'urn:ecad'},
]}
RETRIEVAL = {'results': [{'question': Q, 'hybrid': {'hits': [
    {'domain': 'engineeringbom', 'uri': 'urn:bom'},
    {'domain': 'assetinventory', 'uri': 'urn:asset'},
    {'domain': 'ecad', 'uri': 'urn:ecad'},
]}}]}
DOMAINS = ['engineeringbom', 'assetinventory']


class AdapterTests(unittest.TestCase):
    def test_passes_exact_domain_set_to_existing_planner(self):
        with patch.object(adapter, 'compile_n_domain', return_value={'sparql': 'SELECT ...'}) as compiled:
            out = adapter.adapt(Q, RETRIEVAL, INDEX, {}, DOMAINS)
        self.assertEqual(out['status'], 'ready')
        self.assertEqual(compiled.call_args.args[3], set(DOMAINS))
        self.assertFalse(compiled.call_args.args[4])  # no candidate opt-in
        self.assertEqual(out['retrieved_domains'], ['assetinventory', 'ecad', 'engineeringbom'])

    def test_no_automatic_join_from_retrieved_domains(self):
        with patch.object(adapter, 'compile_n_domain', side_effect=ValueError('No verified mapping')):
            out = adapter.adapt(Q, RETRIEVAL, INDEX, {}, DOMAINS)
        self.assertEqual(out['status'], 'abstained')
        self.assertIsNone(out['plan'])

    def test_rejects_domain_without_retrieval_evidence(self):
        limited = {'results': [{'question': Q, 'hybrid': {'hits': [
            {'domain': 'engineeringbom', 'uri': 'urn:bom'}]}}]}
        with patch.object(adapter, 'compile_n_domain') as compiled:
            out = adapter.adapt(Q, limited, INDEX, {}, DOMAINS)
        self.assertEqual(out['status'], 'abstained')
        compiled.assert_not_called()

    def test_rejects_ambiguous_question(self):
        with patch.object(adapter, 'compile_n_domain') as compiled:
            out = adapter.adapt(Q, {'results': []}, INDEX, {}, DOMAINS)
        self.assertEqual(out['status'], 'abstained')
        compiled.assert_not_called()

    def test_requires_explicit_multi_domain_intent(self):
        out = adapter.adapt(Q, RETRIEVAL, INDEX, {}, ['engineeringbom'])
        self.assertEqual(out['status'], 'abstained')

    def test_candidate_flag_is_explicit(self):
        with patch.object(adapter, 'compile_n_domain', return_value={'cross_domain_join': 'candidate'}) as compiled:
            out = adapter.adapt(Q, RETRIEVAL, INDEX, {}, DOMAINS, allow_candidate=True)
        self.assertEqual(out['status'], 'ready')
        self.assertTrue(compiled.call_args.args[4])
        self.assertFalse(out['safety']['join_approval_required_by_default'])


if __name__ == '__main__':
    unittest.main()
