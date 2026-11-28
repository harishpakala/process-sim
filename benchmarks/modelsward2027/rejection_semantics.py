"""Post-decision scoring only. Never use expected labels for system routing."""
from collections import Counter

REASONS={"unknown_entity","unknown_property","ambiguous_domain","ambiguous_owner","unregistered_mapping","write_operation"}
AMBIGUOUS={"ambiguous_domain","ambiguous_owner"}

def score(expected_reason, decision, reason=None, harness_intercepted=False):
    if expected_reason is not None and expected_reason not in REASONS:
        raise ValueError("Unknown expected reason")
    if decision not in {"accept","reject","clarify","technical_failure"}:
        raise ValueError("Unknown observed decision")
    if harness_intercepted and decision!="accept":
        raise ValueError("Interception requires an accepted request")
    negative=expected_reason is not None
    if decision=="technical_failure":
        outcome="technical_failure"
    elif decision=="accept":
        outcome="false_acceptance" if negative else "supported_acceptance"
    elif not negative:
        outcome="false_rejection"
    elif reason==expected_reason and (decision=="reject" or expected_reason in AMBIGUOUS):
        outcome="correct_rejection"
    else:
        outcome="incorrect_rejection_reason_or_action"
    return {"negative":negative,"outcome":outcome,"harness_intercepted":harness_intercepted,
            "reason_match":negative and reason==expected_reason and decision in {"reject","clarify"}}

def summarize(records):
    counts=Counter(r["outcome"] for r in records)
    negatives=sum(r["negative"] for r in records)
    positives=len(records)-negatives
    def rate(n,d):
        return n/d if d else None
    return {"counts":dict(counts),"negative_runs":negatives,"supported_runs":positives,
            "correct_rejection_rate":rate(counts["correct_rejection"],negatives),
            "false_acceptance_rate":rate(counts["false_acceptance"],negatives),
            "false_rejection_rate":rate(counts["false_rejection"],positives),
            "negative_harness_interception_rate":rate(sum(r["negative"] and r["harness_intercepted"] for r in records),negatives)}
