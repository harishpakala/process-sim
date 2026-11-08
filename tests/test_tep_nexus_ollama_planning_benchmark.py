"""Offline tests for planning benchmark scoring and rejection boundaries."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tep_nexus_ollama_planning_benchmark import evaluate, make_cases

RUN = "077a3c31-44f4-4f3a-b06d-ad52b148fe10"
FUNCTIONS = {"TI_101": {}, "PI_102": {}}


def correct_planner(url, model, question, supported):
    import re
    match = re.search(r"\b(?:TI_101|PI_102)\b", question)
    return {"engineering_function": match.group(0) if match else "TI_101",
            "operations": ["get_observations"]}


class PlanningBenchmarkTests(unittest.TestCase):
    def test_deterministic_case_generation(self):
        cases = make_cases(FUNCTIONS, RUN)
        self.assertEqual(len(cases), 15)
        self.assertEqual(len({c["id"] for c in cases}), len(cases))
        self.assertEqual(sum(c["expected"] == "REJECT" for c in cases), 3)

    def test_valid_and_invalid_contract_decisions(self):
        cases = make_cases(FUNCTIONS, RUN)
        report = evaluate(cases, run_id=RUN, supported_functions=FUNCTIONS,
                          url="unused", model="fake", planner=correct_planner,
                          clock=lambda: 1.0)
        self.assertEqual(report["summary"]["status"], "PASS")
        self.assertEqual(report["summary"]["rejectedInvalidCases"], 3)

    def test_repetitions_expand_trials_without_changing_question_set(self):
        cases = make_cases({"TI_101": {}}, RUN)
        report = evaluate(cases, run_id=RUN, supported_functions={"TI_101": {}},
                          url="unused", model="fake", planner=correct_planner,
                          clock=lambda: 1.0, repetitions=3)
        self.assertEqual(report["summary"]["caseCount"], len(cases) * 3)
        self.assertEqual(report["summary"]["uniqueQuestionCount"], len(cases))
        self.assertEqual(report["summary"]["adversarialAttemptCount"], 18)
        self.assertEqual(report["summary"]["status"], "PASS")

    def test_invalid_repetitions_rejected(self):
        with self.assertRaisesRegex(ValueError, "repetitions"):
            evaluate([], run_id=RUN, supported_functions=FUNCTIONS,
                     url="unused", model="fake", repetitions=0)

    def test_wrong_function_is_detected(self):
        cases = make_cases({"TI_101": {}}, RUN)
        report = evaluate(cases[:1], run_id=RUN, supported_functions={"TI_101": {}},
                          url="unused", model="fake",
                          planner=lambda *args: {"engineering_function": "PI_102",
                                                 "operations": ["get_observations"]},
                          clock=lambda: 1.0)
        self.assertEqual(report["summary"]["status"], "FAIL")

    def test_planner_errors_are_recorded(self):
        def fail(*args):
            raise RuntimeError("model offline")
        report = evaluate(make_cases({"TI_101": {}}, RUN)[:1],
                          run_id=RUN, supported_functions={"TI_101": {}},
                          url="unused", model="fake", planner=fail, clock=lambda: 1.0)
        self.assertIn("model offline", report["cases"][0]["error"])
        self.assertEqual(report["summary"]["correctDecisions"], 0)


if __name__ == "__main__":
    unittest.main()
