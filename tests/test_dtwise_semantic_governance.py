"""Approval evidence must be explicit; passing GraphDB counts never grants it."""
import unittest

from semantic.dtwise_semantic_governance import require_approval


PLAN = {"mapping_ids": ["test_mapping"], "domains": ["engineeringbom", "ecad"],
        "comparison": "string_equality"}
APPROVAL = {"mapping_id": "test_mapping", "decision": "approved",
            "reviewer": "semantic-domain-owner", "approved_at": "2026-11-12",
            "rationale": "Both predicates identify the same governed asset.",
            "evidence_reference": "review/asset-identity-001",
            "domains": ["engineeringbom", "ecad"],
            "comparison": "string_equality"}


class SemanticGovernanceTests(unittest.TestCase):
    def test_missing_approval_rejected(self):
        with self.assertRaisesRegex(ValueError, "lacks a unique"):
            require_approval(PLAN, {"semantic_approvals": []})

    def test_approved_record_accepted(self):
        require_approval(PLAN, {"semantic_approvals": [APPROVAL]})

    def test_rejected_decision_rejected(self):
        with self.assertRaisesRegex(ValueError, "not approved"):
            require_approval(PLAN, {"semantic_approvals": [{**APPROVAL, "decision": "rejected"}]})

    def test_missing_reviewer_rejected(self):
        with self.assertRaisesRegex(ValueError, "reviewer"):
            require_approval(PLAN, {"semantic_approvals": [{**APPROVAL, "reviewer": ""}]})

    def test_scope_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "domains differ"):
            require_approval(PLAN, {"semantic_approvals": [
                {**APPROVAL, "domains": ["engineeringbom", "dexpi"]}]})

    def test_duplicate_approval_rejected(self):
        with self.assertRaisesRegex(ValueError, "lacks a unique"):
            require_approval(PLAN, {"semantic_approvals": [APPROVAL, APPROVAL]})


if __name__ == "__main__":
    unittest.main()
