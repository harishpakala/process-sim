"""Read-only, fail-closed integration checks for TEP NEXUS.

Uses the real GraphDB for the stale-mapping scenario. The historian retriever
is deliberately replaced with a tripwire: no SQL is executed in these tests.
All snapshots are read-only; a temporary modified coverage file is deleted.
"""
import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from tep_nexus_live_virtual_graph import execute
from tep_nexus_function_registry import load_supported_functions


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id', required=True)
    p.add_argument('--function', default='PI_101')
    p.add_argument('--graphdb-url', default='http://localhost:7200/repositories/AAS')
    p.add_argument('--mapping-discovery', default='reports/tep_nexus_mapping_discovery.json')
    p.add_argument('--old-mapping-discovery', default='reports/tep_nexus_mapping_discovery_before_uri_change.json')
    p.add_argument('--temporal-coverage', default='reports/tep_nexus_temporal_coverage.json')
    p.add_argument('--output', default='reports/tep_nexus_live_negative_checks.json')
    args = p.parse_args()
    run = str(UUID(args.run_id))
    coverage = json.loads(Path(args.temporal_coverage).read_text(encoding='utf-8-sig'))
    if coverage['run_id'] != run:
        p.error('Coverage snapshot does not match --run-id; refusing to run')
    current_registry = load_supported_functions(args.mapping_discovery, args.temporal_coverage, run)
    if args.function not in current_registry:
        p.error('Selected function is not eligible in current registry')

    cases = []
    def case(name, *, run_id=run, mapping_path=None, coverage_path=None, expected_type, expected_message):
        attempts = {'historian': 0}
        def tripwire(*_args, **_kwargs):
            attempts['historian'] += 1
            raise AssertionError('Historian retrieval was reached unexpectedly')
        request = {'engineering_function': args.function, 'run_id': run_id,
                   'start_simulation_seconds': 0, 'end_simulation_seconds': 120, 'limit': 100}
        error_type, error_text = None, None
        try:
            execute(request, dsn='unused: historian tripwire', graphdb_url=args.graphdb_url,
                    mapping_discovery=mapping_path or args.mapping_discovery,
                    temporal_coverage=coverage_path or args.temporal_coverage,
                    observation_retriever=tripwire)
        except Exception as exc:
            error_type, error_text = type(exc).__name__, str(exc)
        passed = (error_type == expected_type and expected_message in (error_text or '')
                  and attempts['historian'] == 0)
        cases.append({'id': name, 'status': 'PASS' if passed else 'FAIL',
                      'expected_exception': expected_type,
                      'expected_message_contains': expected_message,
                      'observed_exception': error_type, 'observed_message': error_text,
                      'historian_retrieval_attempts': attempts['historian']})

    old = Path(args.old_mapping_discovery)
    if not old.is_file():
        p.error('Old mapping snapshot not found; pass --old-mapping-discovery')
    old_registry = load_supported_functions(old, args.temporal_coverage, run)
    if args.function not in old_registry or old_registry[args.function] == current_registry[args.function]:
        p.error('Old snapshot does not differ for selected function; cannot test stale mapping')
    case('stale_mapping_live_graphdb', mapping_path=str(old),
         expected_type='RuntimeError', expected_message='GraphDB mapping changed since discovery')

    unknown = str(uuid4())
    case('unknown_run_id', run_id=unknown,
         expected_type='ValueError', expected_message='Temporal coverage is not scoped to the requested run')

    modified = json.loads(json.dumps(coverage))
    matches = [x for x in modified['functions'] if x['engineering_function'] == args.function]
    if len(matches) != 1:
        p.error('Expected exactly one coverage entry for selected function')
    matches[0]['temporal_coverage_status'] = 'NO_SAMPLES'
    matches[0]['signals'] = []
    with tempfile.TemporaryDirectory(prefix='tep_nexus_negative_') as tmp:
        temp_coverage = Path(tmp) / 'coverage_no_samples.json'
        temp_coverage.write_text(json.dumps(modified), encoding='utf-8')
        # If this is the only eligible function, registry reports no supported functions.
        try:
            load_supported_functions(args.mapping_discovery, temp_coverage, run)
        except ValueError as exc:
            if 'No supported functions' not in str(exc):
                raise
            expected_message = 'No supported functions with mapping and temporal coverage'
        else:
            expected_message = 'Engineering function not in run-scoped registry'
        case('no_temporal_coverage', coverage_path=str(temp_coverage),
             expected_type='ValueError', expected_message=expected_message)

    report = {'scope': 'negative_integration_checks_live_graphdb_only_for_stale_mapping',
              'generated_at_utc': datetime.now(timezone.utc).isoformat(),
              'run_id': run, 'function': args.function,
              'limitations': [
                  'The stale-mapping scenario queries the real GraphDB.',
                  'Unknown-run and no-coverage scenarios are rejected by local registry validation before GraphDB.',
                  'Historian retrieval is replaced with a tripwire; zero attempts demonstrate control-flow prevention, not network-level SQL tracing.',
                  'No-coverage is simulated using a temporary modified snapshot; source databases are not modified.',
                  'An old mapping snapshot must reflect a real previously observed mapping change.'
              ], 'cases': cases,
              'summary': {'total': len(cases), 'passed': sum(c['status']=='PASS' for c in cases),
                          'failed': sum(c['status']!='PASS' for c in cases)}}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'output': str(output), **report['summary']}, indent=2))
    return 0 if report['summary']['failed'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
