# SAFSL frontend port (phase 1)

Copied from harishpakala/SAFSL_Compiler_Tool_Chain main:
- grammar/process.lark
- safsl_ast/nodes.py -> ast/nodes.py
- safsl_parser/transformer.py -> parser/transformer.py

Upstream is Apache-2.0 licensed. The import in transformer.py was changed
to the process_sim package path. No upstream IEC 61499 XML backend was copied.

Current status: existing grammar/AST port and parser entry point, plus smoke
tests. Contract grammar, template-ID decoding, semantic resolution and SHACL
generation are NOT implemented yet. No tests have been executed in CI by this
change. Install lark==1.3.1 and use PYTHONPATH=src to run tests.

Next: add contract-only Specification support, typed Contract/quantifier AST
nodes, and Ref SubmodelTemplate while preserving existing Process syntax.
