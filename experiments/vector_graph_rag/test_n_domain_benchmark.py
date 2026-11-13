"""Unit tests for N-domain benchmark evaluation."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'n_domain_benchmark', Path(__file__).with_name('11_evaluate_n_domain_benchmark.py'))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class NDomainBenchmarkTests(unittest.TestCase):
    def test_strict_abstains_exploratory_can_generate(self):
        benchmark = {'status': 'provisional_review_required', 'cases': [{
            'id': 'X', 'question': 'Example', 'expected_domains': ['engineeringbom', 'ecad'],
            'category': 'cataloged_candidate',
            'expected_strict_status': 'abstained',
            'expected_exploratory_status': 'ready',
        }]}
        catalog = {'mappings': [{
            'id': 'mapping', 'source_domain': 'engineeringbom',
            'target_domain': 'ecad', 'source_path': ['a', 'b'],
            'target_path': ['c', 'd'], 'status': 'candidate_pending_semantic_approval',
            'comparison': 'string_equality',
        }]}
        def planner(question, index, catalog, domains, allow_candidate, limit, validate):
            if not allow_candidate:
                raise ValueError('Not approved')
            return {'sparql': 'SELECT ...', 'mapping_status': 'candidate_pending_semantic_approval'}
        with patch.object(mod, 'compile_n_domain', side_effect=planner):
            report = mod.evaluate(benchmark, {}, catalog)
        self.assertEqual(report['summary']['strict']['abstained'], 1)
        self.assertEqual(report['summary']['exploratory']['ready'], 1)
        self.assertEqual(report['summary']['exploratory']['provisional_expectation_matches'], 1)
        self.assertFalse(report['results'][0]['modes']['exploratory']['executed'])

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            mod.evaluate({'cases': [{'id': 'x'}, {'id': 'x'}]}, {}, {})


if __name__ == '__main__':
    unittest.main()
