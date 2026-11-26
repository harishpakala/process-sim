# SELiRA research artifact (work in progress)

Stage 1 extracts the SAFSL language, compiler and reference semantics from the frozen process-sim baseline. Existing integration is unchanged. Not yet a complete research artifact or verified release.

From this directory: `python -m pip install -e ".[test]"` then `python -m pytest tests -q`.

The extracted tests are copies with adjusted imports. No test execution is claimed. Runtime, policies, datasets and integrated evaluation will follow. Upstream SAFSL provenance is retained in language/PORTING.md and language/__init__.py. Artifact-wide licensing and citation metadata remain to be confirmed.
