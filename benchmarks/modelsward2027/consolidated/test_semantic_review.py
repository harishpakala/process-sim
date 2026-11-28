from semantic_review import evaluate

def test_intercept_is_false_acceptance():
    assert evaluate({'scenario_id':'N43','status':'negative_compiled_not_executed'},{'mode':'negative'},None)['outcome']=='false_acceptance'

def test_missing_review_is_pending():
    assert evaluate({'status':'executed'},{'mode':'set'},None)['semantic_correctness'] is None

def test_structural_failure_overrides_bindings():
    assert evaluate({'status':'executed'},{'mode':'bag'},{'structural_correctness':False})['semantic_correctness'] is False

def test_reason_specific():
    assert evaluate({'scenario_id':'N43','status':'planning_not_valid'},{'mode':'negative'},{'decision':'reject','reason':'unregistered_mapping'})['outcome']=='correct_rejection'
