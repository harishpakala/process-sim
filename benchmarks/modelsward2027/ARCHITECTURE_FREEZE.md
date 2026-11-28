# Architecture freeze for comparative evaluation

Frozen implementation revision: a33b6540f51103f388e58b99b5c14f0ad0a66e8c.

Development evidence (user-executed): ECAD fixture 55/55 positional literal-bag matches; original Qwen regression 199/200 positional agreement before mapping-intent change; 15/15 architecture unit tests; final targeted mapping regression 20/20 supported positional matches and 5/5 N43 blocked with no LLM calls. Targeted raw records were inspected; full final-revision regression remains pending. These are development results, not independent test evidence.

Freeze production planner and compiler for the next comparative experiments. New evaluation scripts, fixtures and baselines may be added separately. Any subsequent production change requires a new revision and explicit reporting of development exposure. Do not combine results across revisions as one final run.

Next: independently reviewed multi-domain nested challenge, schema-informed direct SPARQL baseline, owner-qualification ablation with residual cues documented, then paired multi-model evaluation. Preserve historical benchmark and reference files. N44 write requests are outside revised paper scope. Positional agreement is not structural equivalence; snapshot identity and independent semantic review remain pending.
