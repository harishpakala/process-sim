"""Tests for implicit-domain retrieval ablation."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'implicit_ablation', Path(__file__).with_name('13_evaluate_implicit_domain_ablation.py'))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ImplicitAblationTests(unittest.TestCase):
    def test_rank_weighted_selection_and_cap(self):
        hits = [{'domain': d} for d in ('ecad', 'dexpi', 'ecad', 'engineeringbom', 'ecad')]
        selected, scores = mod.select_domains(hits, threshold=0.35, max_domains=2)
        self.assertEqual(selected, ['dexpi', 'ecad'])
        self.assertGreater(scores['ecad'], scores['engineeringbom'])

    def test_no_hits(self):
        self.assertEqual(mod.select_domains([]), ([], {}))

    def test_invalid_threshold(self):
        with self.assertRaises(ValueError):
            mod.select_domains([{'domain': 'ecad'}], threshold=0)

    def test_gold_not_used_for_selection(self):
        records = [
            {'id': 'a', 'domain': 'ecad', 'uri': 'urn:a', 'kind': 'property'},
            {'id': 'b', 'domain': 'dexpi', 'uri': 'urn:b', 'kind': 'property'},
        ]
        index = {'concepts': [{'domain': r['domain'], 'uri': r['uri']} for r in records]}
        benchmark = {'cases': [{
            'id': 'imp', 'question': 'Electrical devices and process equipment?',
            'expected_domains': ['assetinventory', 'engineeringbom'],
            'expected_strict_status': 'abstained',
            'expected_exploratory_status': 'abstained',
        }]}
        class FakeRetriever:
            @staticmethod
            def ranks(*args):
                return ({m: records for m in mod.METHODS}, {})
        with patch.object(mod, 'load_retriever', return_value=FakeRetriever()), \
             patch.object(mod, 'compile_n_domain', side_effect=ValueError('No plan')) as planner:
            report = mod.evaluate(benchmark, index, {}, records, {}, lambda q: [0.1])
        for method in mod.METHODS:
            self.assertEqual(report['results'][0]['methods'][method]['selected_domains'],
                             ['dexpi', 'ecad'])
        self.assertEqual(planner.call_args.args[3], {'ecad', 'dexpi'})
        self.assertEqual(report['summary']['methods']['hybrid']['exact_domain_set_matches'], 0)


if __name__ == '__main__':
    unittest.main()
