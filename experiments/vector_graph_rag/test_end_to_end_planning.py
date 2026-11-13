"""Tests for the non-oracle domain selector and retrieval-gated planner."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'e2e', Path(__file__).with_name('12_evaluate_end_to_end_planning.py'))
e2e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e2e)


class EndToEndTests(unittest.TestCase):
    def test_explicit_domain_selection(self):
        self.assertEqual(e2e.select_explicit_domains(
            'Which ECAD devices match EngineeringBOM records?'),
            ['ecad', 'engineeringbom'])
        self.assertEqual(e2e.select_explicit_domains(
            'Which devices match equipment?'), [])

    def test_retrieval_gate_blocks_planning(self):
        benchmark = {'cases': [{
            'id': 'test', 'question': 'ECAD and DEXPI?',
            'expected_domains': ['ecad', 'dexpi'],
            'expected_strict_status': 'abstained',
            'expected_exploratory_status': 'abstained',
        }]}
        records = [{'id': 'a', 'domain': 'ecad', 'uri': 'urn:a', 'kind': 'property'}]
        index = {'concepts': [{'domain': 'ecad', 'uri': 'urn:a'}]}
        class FakeRetriever:
            @staticmethod
            def ranks(*args):
                return ({'hybrid': records, 'vector': records, 'lexical': records}, {})
        with patch.object(e2e, 'load_retriever', return_value=FakeRetriever()), \
             patch.object(e2e, 'compile_n_domain') as planner:
            result = e2e.evaluate(benchmark, index, {}, records, {}, lambda q: [0.1])
        self.assertFalse(result['results'][0]['selected_domains_supported_by_retrieval'])
        planner.assert_not_called()
        self.assertEqual(result['summary']['strict']['abstained'], 1)

    def test_gold_labels_never_passed_to_planner(self):
        benchmark = {'cases': [{
            'id': 'test', 'question': 'ECAD and DEXPI?',
            'expected_domains': ['ecad', 'engineeringbom'],
            'expected_strict_status': 'abstained',
            'expected_exploratory_status': 'ready',
        }]}
        records = [
            {'id': 'a', 'domain': 'ecad', 'uri': 'urn:a', 'kind': 'property'},
            {'id': 'b', 'domain': 'dexpi', 'uri': 'urn:b', 'kind': 'property'},
        ]
        index = {'concepts': [{'domain': r['domain'], 'uri': r['uri']} for r in records]}
        class FakeRetriever:
            @staticmethod
            def ranks(*args):
                return ({'hybrid': records, 'vector': records, 'lexical': records}, {})
        with patch.object(e2e, 'load_retriever', return_value=FakeRetriever()), \
             patch.object(e2e, 'compile_n_domain', side_effect=ValueError('No plan')) as planner:
            result = e2e.evaluate(benchmark, index, {}, records, {}, lambda q: [0.1])
        self.assertEqual(planner.call_args.args[3], {'ecad', 'dexpi'})
        self.assertFalse(result['results'][0]['exact_domain_set_match'])


if __name__ == '__main__':
    unittest.main()
