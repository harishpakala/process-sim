"""Regression smoke tests for the copied SAFSL grammar and AST."""
import unittest
from process_sim.safsl.parser.frontend import parse_safsl


class TestSAFSLFrontend(unittest.TestCase):
    def test_existing_process_syntax_parses(self):
        source = """Specification Example {
            StartTerminal=[q0];
            Ref Submodel DEXPI="REVYUEkyNQ==";
            Process q0 {
                Interface {
                    Terminal Input START;
                    Terminal Output DONE;
                }
                Body { }
            }
        }"""
        ast = parse_safsl(source)
        spec = ast.children[0]
        self.assertEqual(spec.name, "Example")
        self.assertEqual(len(spec.processes), 1)
        self.assertEqual(spec.processes[0].name, "q0")

    def test_invalid_syntax_rejected(self):
        from lark.exceptions import LarkError
        with self.assertRaises(LarkError):
            parse_safsl("Specification Broken { }")


if __name__ == "__main__":
    unittest.main()
