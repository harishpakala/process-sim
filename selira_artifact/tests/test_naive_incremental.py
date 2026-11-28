"""Regression tests for the RC02 evaluation-only SC01 comparator."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evaluation"))
from naive_incremental import bounded, compare_naive
from selira.runtime.reassessment.snapshot import Snapshot


def snap(assigned="x", catalog=None, complete=True):
    return Snapshot("R", {"a": assigned} if assigned is not None else {},
                    {"p": "x"} if catalog is None else catalog, complete)


@pytest.mark.parametrize("before,after,count,full,naive", [
    (snap(), snap(), 0, None, None),
    (snap(), snap("y"), 1, None, None),
    (snap(None), snap(), 1, None, None),
    (snap(), snap(None), 1, None, None),
    (snap(), snap(catalog={"p": "y"}), 0, "INVALID", "VALIDATED"),
    (snap(), snap(catalog={"p": "x", "q": "x"}), 0, "INVALID", "VALIDATED"),
    (snap(catalog={}), snap(), 0, "VALIDATED", "INVALID"),
    (snap(), snap(catalog={"p": "x", "q": "y"}), 0, None, None),
])
def test_direct_change(before, after, count, full, naive):
    result = compare_naive(before, after)
    assert result["dsr_equivalent"]
    assert result["nir_evaluations"] == count
    assert result["nir_equivalent"] == (full is None)
    assert result["disagreements"] == (
        [] if full is None else [{"asset": "a", "full": full, "naive": naive}])


@pytest.mark.parametrize("flag", [
    "coverage_attested", "policy_unchanged", "authority_unchanged"])
def test_fallback(flag):
    result = compare_naive(snap(), snap(catalog={}), **{flag: False})
    assert result["nir_equivalent"] and result["dsr_equivalent"]
    assert result["nir_evaluations"] == result["full_evaluations"] == 1


def test_completeness_change():
    result = compare_naive(snap(), snap(complete=False))
    assert result["nir_equivalent"]
    assert result["nir_evaluations"] == result["full_evaluations"] == 1


def test_bounded_regression():
    result = bounded()
    assert result["snapshots"] == 36
    assert result["comparisons"] == result["dsr_equivalent"] == 1296
    assert result["full_evaluations"] == 1215
    assert result["dsr_evaluations"] == 1084
    assert result["nir_equivalent"] < result["comparisons"]
    assert result["nir_evaluations"] <= result["full_evaluations"]
    assert sum(row["count"] for row in result["disagreements"]) == (
        result["comparisons"] - result["nir_equivalent"])
