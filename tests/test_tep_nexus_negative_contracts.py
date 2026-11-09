"""Offline negative contract tests for TEP NEXUS (refactor/repository-cleanup).

Copy into tests/ and run: python -m unittest tests/test_tep_nexus_negative_contracts.py -v
No live GraphDB, TimescaleDB, or Ollama is needed.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from tep_nexus_function_registry import resolve_supported_mapping, load_supported_functions
from tep_nexus_live_virtual_graph import execute

RUN = '077a3c31-44f4-4f3a-b06d-ad52b148fe10'
FUNCTION = 'TI_101'
SIGNAL = 'XMEAS9'
SNAPSHOT = {'function_reference': 'https://aas.example.com/TI101',
            'operational_signal': SIGNAL, 'asset_uri': 'https://example.org/asset/9'}


def request(run=RUN):
    return {'engineering_function': FUNCTION, 'run_id': run,
            'start_simulation_seconds': 0, 'end_simulation_seconds': 120, 'limit': 2}


def classified_candidate(mapping=SNAPSHOT, status='UNIQUE_PROVISIONAL_CANDIDATE'):
    return {'engineering_function': FUNCTION, 'status': status,
            'mapping_count': 1, 'mappings': [mapping]}


def fake_response():
    response = Mock()
    response.json.return_value = {'results': {'bindings': []}}
    return response


class MappingNegativeContracts(unittest.TestCase):
    def test_missing_live_mapping_rejected(self):
        with patch('tep_nexus_function_registry.requests.post', return_value=fake_response()), \
             patch('tep_nexus_function_registry.classify_bindings', return_value={'candidates': []}):
            with self.assertRaisesRegex(RuntimeError, 'missing or ambiguous'):
                resolve_supported_mapping('http://unused', FUNCTION, {FUNCTION: SNAPSHOT})

    def test_ambiguous_live_mapping_rejected(self):
        candidate = classified_candidate(status='AMBIGUOUS')
        with patch('tep_nexus_function_registry.requests.post', return_value=fake_response()), \
             patch('tep_nexus_function_registry.classify_bindings', return_value={'candidates': [candidate]}):
            with self.assertRaisesRegex(RuntimeError, 'missing or ambiguous'):
                resolve_supported_mapping('http://unused', FUNCTION, {FUNCTION: SNAPSHOT})

    def test_changed_function_reference_rejected(self):
        old_uri_mapping = {**SNAPSHOT, 'function_reference': 'https://aas.example.com/TI_101'}
        with patch('tep_nexus_function_registry.requests.post', return_value=fake_response()), \
             patch('tep_nexus_function_registry.classify_bindings',
                   return_value={'candidates': [classified_candidate(old_uri_mapping)]}):
            with self.assertRaisesRegex(RuntimeError, 'changed since discovery'):
                resolve_supported_mapping('http://unused', FUNCTION, {FUNCTION: SNAPSHOT})

    def test_unregistered_function_rejected_without_graphdb_call(self):
        with patch('tep_nexus_function_registry.requests.post') as post:
            with self.assertRaisesRegex(ValueError, 'not in run-scoped registry'):
                resolve_supported_mapping('http://unused', FUNCTION, {})
            post.assert_not_called()

    def test_mapping_failure_prevents_historian_query(self):
        def reject(*args):
            raise RuntimeError('GraphDB mapping changed since discovery; regenerate reports')
        with self.assertRaisesRegex(RuntimeError, 'changed since discovery'):
            execute(request(), dsn='unused', graphdb_url='unused',
                    registry_loader=lambda *args: {FUNCTION: SNAPSHOT},
                    mapping_resolver=reject,
                    observation_retriever=lambda *args: self.fail('Historian must not be queried'))


class CoverageNegativeContracts(unittest.TestCase):
    def test_unknown_run_rejected_before_mapping_or_sql(self):
        def reject_coverage(*args):
            raise ValueError('Temporal coverage is not scoped to the requested run')
        with self.assertRaisesRegex(ValueError, 'not scoped'):
            execute(request('00000000-0000-4000-8000-000000000001'),
                    dsn='unused', graphdb_url='unused', registry_loader=reject_coverage,
                    mapping_resolver=lambda *args: self.fail('GraphDB must not be queried'),
                    observation_retriever=lambda *args: self.fail('SQL must not be queried'))

    def test_no_coverage_for_function_rejected_before_graphdb_or_sql(self):
        with self.assertRaisesRegex(ValueError, 'not in run-scoped registry'):
            execute(request(), dsn='unused', graphdb_url='unused',
                    registry_loader=lambda *args: {'PI_101': SNAPSHOT},
                    mapping_resolver=lambda url, function, registry: resolve_supported_mapping(url, function, registry),
                    observation_retriever=lambda *args: self.fail('SQL must not be queried'))


if __name__ == '__main__':
    unittest.main()
