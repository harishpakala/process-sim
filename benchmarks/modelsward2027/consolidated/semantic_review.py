"""Score explicitly reviewed evidence, without treating positional agreement as semantics."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from result_semantics import compare
from ordered_semantics import compare_ordered
from rejection_semantics import score

REASONS={'N39':'unknown_entity','N40':'unknown_property','N41':'ambiguous_domain','N42':'ambiguous_owner','N43':'unregistered_mapping'}

def evaluate(record, contract, review, reference=None, ordered_reference=None):
    """Reference and actual results use SPARQL JSON format.
    Review must be independently supplied, not inferred from result equality.
    """
    mode=contract['mode']
    if mode=='negative':
        reason=REASONS[record['scenario_id']]
        if record['status']=='negative_compiled_not_executed':
            return score(reason,'accept',harness_intercepted=True)
        if not review:
            return {'outcome':'pending_review'}
        return score(reason,review['decision'],review.get('reason'))
    if record['status']!='executed':
        return {'semantic_correctness':False,'outcome':'execution_or_planning_failure'}
    if not review or review.get('structural_correctness') is None:
        return {'semantic_correctness':None,'outcome':'pending_review'}
    if review['structural_correctness'] is False:
        return {'semantic_correctness':False,'outcome':'structural_failure'}
    if review['structural_correctness'] is not True or not review.get('evidence'):
        raise ValueError('Explicit structural judgment and evidence required')
    if mode=='ordered_pending':
        if ordered_reference is None:
            return {'semantic_correctness':None,'outcome':'pending_order_reference'}
        result=compare_ordered(record['result'],ordered_reference,contract['roles'],
            review['actual_alignment'],review['reference_alignment'],review['limit'],review['descending'])
    else:
        result=compare(record['result'],reference,contract,review['actual_alignment'],review['reference_alignment'])
    return dict(result,semantic_correctness=result['contract_match'],outcome='reviewed')

