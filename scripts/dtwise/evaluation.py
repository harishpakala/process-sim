def evaluate(retrieved_ids, expected_ids, k=None):
    expected = set(expected_ids)
    retrieved = list(dict.fromkeys(retrieved_ids))
    if k is not None: retrieved = retrieved[:k]
    found = len(set(retrieved) & expected)
    precision = found / len(retrieved) if retrieved else 0.0
    recall = found / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {'precision': precision, 'recall': recall, 'f1': f1, 'hits': found, 'expected': len(expected), 'retrieved': len(retrieved)}
