"""Ordered agreement for single-valued string sort keys, using full reference rows."""
from collections import Counter
from itertools import groupby
from result_semantics import rows, term

def compare_ordered(actual, reference, roles, actual_alignment, reference_alignment, limit, descending=False):
    if not isinstance(limit,int) or limit<1:
        raise ValueError("Positive LIMIT required")
    a=rows(actual,actual_alignment,roles)
    ref=reference["results"]["bindings"]
    projected={"head":{"vars":[v for v in reference["head"]["vars"] if v!="sort"]},
               "results":{"bindings":ref}}
    e=rows(projected,reference_alignment,roles)
    keys=[]
    for r in ref:
        k=term(r.get("sort"))
        if len(k)!=4 or k[0]!="literal" or k[2]!="http://www.w3.org/2001/XMLSchema#string" or k[3]:
            raise ValueError("Only string sort keys supported")
        keys.append(k[1])
    if len(set(e))!=len(e) or any(t[0]!="uri" for row in e for t in row):
        raise ValueError("Unique projected entity tuples required")
    if keys!=sorted(keys,reverse=descending):
        raise ValueError("Reference ordering inconsistent")
    match=len(a)==min(limit,len(e))
    offset=0
    for _, group in groupby(zip(keys,e),key=lambda x:x[0]):
        pool=[r for _,r in group]
        take=min(len(pool),max(0,limit-offset))
        if not take:
            break
        segment=a[offset:offset+take]
        match=match and len(segment)==take and not (Counter(segment)-Counter(pool))
        offset+=take
    return {"contract_match":bool(match),"strict_sequence_match":a==e[:limit],
            "structural_review_required":True}
