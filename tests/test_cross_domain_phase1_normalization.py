"""Regression tests for generic cross-domain Phase-1 plan normalization."""
from copy import deepcopy

from process_sim.dtwise.shacl_planner.cross_domain_phase1 import (
    _normalize_explicit_sort_and_placeholder_filters,
)


CANDIDATES = [
    {'id': 'dexpi:P7', 'domain': 'dexpi', 'kind': 'property',
     'path': 'DEXPI → Equipment → AssetIdentifier',
     'property_name': 'AssetIdentifier'},
    {'id': 'ecad:P1', 'domain': 'ecad', 'kind': 'property',
     'path': 'ECAD → Device → AssetIdentifier',
     'property_name': 'AssetIdentifier'},
    {'id': 'dexpi:P8', 'domain': 'dexpi', 'kind': 'property',
     'path': 'DEXPI → Equipment → LocalId', 'property_name': 'LocalId'},
    {'id': 'ecad:P7', 'domain': 'ecad', 'kind': 'property',
     'path': 'ECAD → Device → LocalId', 'property_name': 'LocalId'},
]


def plan(*, filters=None, direction='ASC', sort='ecad:P7'):
    return {'status': 'selected', 'filters': filters or [],
            'boolean_operator': 'AND' if filters else 'NONE',
            'order_by': [{'property_id': sort, 'direction': direction}]}


def test_unrequested_placeholder_join_filters_removed():
    answer = plan(filters=[
        {'property_id': 'dexpi:P7', 'operator': '=',
         'value': '<question literal>'},
        {'property_id': 'ecad:P1', 'operator': '=',
         'value': '<question literal>'},
    ])
    question = ('Show DEXPI Equipment and ECAD Devices matched on '
                'AssetIdentifier, sorted by DEXPI Equipment LocalId DESC')
    normalized = _normalize_explicit_sort_and_placeholder_filters(
        answer, CANDIDATES, question)
    assert normalized['filters'] == []
    assert normalized['boolean_operator'] == 'NONE'
    assert normalized['order_by'] == [
        {'property_id': 'dexpi:P8', 'direction': 'DESC'}]


def test_explicit_owner_and_natural_language_descending():
    question = ('Find ECAD Devices associated with DEXPI Equipment via '
                'AssetIdentifier, order the results by DEXPI Equipment '
                'LocalId from highest to lowest, limiting output to 10')
    normalized = _normalize_explicit_sort_and_placeholder_filters(
        plan(direction='DESC'), CANDIDATES, question)
    assert normalized['order_by'] == [
        {'property_id': 'dexpi:P8', 'direction': 'DESC'}]


def test_literal_comparison_not_discarded():
    answer = plan(filters=[{'property_id': 'ecad:P1',
                            'operator': '=', 'value': 'A_100'}])
    question = ('Show ECAD Device whose AssetIdentifier is A_100 '
                'ordered by ECAD Device LocalId ascending')
    normalized = _normalize_explicit_sort_and_placeholder_filters(
        answer, CANDIDATES, question)
    assert normalized['filters'] == [
        {'property_id': 'ecad:P1', 'operator': '=', 'value': 'A_100'}]
    assert normalized['order_by'] == [
        {'property_id': 'ecad:P7', 'direction': 'ASC'}]


def test_unqualified_sort_owner_is_not_guessed():
    answer = plan()
    normalized = _normalize_explicit_sort_and_placeholder_filters(
        deepcopy(answer), CANDIDATES, 'Show matching entities sorted by LocalId')
    assert normalized['order_by'][0]['property_id'] == 'ecad:P7'


def test_nonplaceholder_unrequested_filter_still_requires_validation():
    answer = plan(filters=[{'property_id': 'ecad:P1',
                            'operator': '=', 'value': 'invented'}])
    normalized = _normalize_explicit_sort_and_placeholder_filters(
        answer, CANDIDATES, 'Show ECAD Device sorted by LocalId')
    assert normalized['filters'] == answer['filters']
