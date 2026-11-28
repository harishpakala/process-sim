"""RC02 reproduction entry point; preserves the complete RC01 procedure."""
import contextlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import reproduce_all as rc01
from naive_incremental import bounded
from compare_integrated_lifecycle import run as integrated

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluation/results/reproduced"
FIELDS = ("comparisons", "full_evaluations", "nir_evaluations",
          "dsr_evaluations", "nir_equivalent", "dsr_equivalent")


def verify(row, expected, differences):
    assert tuple(row[k] for k in FIELDS) == expected, row
    actual = {(d["full"], d["naive"]): d["count"]
              for d in row["disagreements"]}
    assert actual == differences, actual


def main():
    if not __debug__:
        raise RuntimeError("Assertions must be enabled")
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "rc02_comparative_verification.json"
    # Never leave an earlier successful RC02 report after a failed invocation.
    target.unlink(missing_ok=True)
    rc01.main()
    sys.path.insert(0, str(ROOT / "tests"))
    from test_rc02_identifier_comparison import run_identifier, D, E
    from test_rc02_qualified_comparison import test_rc02_qualified_comparison

    reference = bounded()
    verify(reference, (1296, 1215, 972, 1084, 1216, 1296),
           {("INVALID", "VALIDATED"): 40, ("VALIDATED", "INVALID"): 40})
    identifiers = [run_identifier("02", D), run_identifier("03", E)]
    for row in identifiers:
        verify(row, (256, 496, 228, 228, 256, 256), {})
        assert row["fallback_checks"] == 3
    qualified = []
    for coverage in (True, False):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            test_rc02_qualified_comparison(coverage)
        row = json.loads(buffer.getvalue())
        qualified.append(row)
    verify(qualified[0], (256, 1024, 792, 840, 250, 256),
           {("F", "V"): 6, ("V", "F"): 6})
    verify(qualified[1], (256, 1024, 1024, 1024, 256, 256), {})
    assert [r["fallback_comparisons"] for r in qualified] == [192, 256]
    lifecycle = integrated()
    verify(lifecycle, (13, 2444, 197, 203, 12, 13), {("F", "V"): 6})
    failed = [r for r in lifecycle["events"] if not r["nir_equivalent"]]
    assert len(failed) == 1
    assert failed[0]["event"] == "shared_duplicate_product_identifier"
    report = dict(status="passed", execution_utc=datetime.now(timezone.utc).isoformat(),
                  rc01_verification="verification_report.json",
                  scope="Logical evaluation counts, not runtime; qualified counts are contract-level",
                  reference=reference, identifiers=identifiers,
                  qualified=qualified, integrated=lifecycle)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("RC02 comparative verification passed:", target)


if __name__ == "__main__":
    main()
