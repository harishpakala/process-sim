"""Apply minimal additive DTwise dispatch changes. Run from project root."""
from pathlib import Path


def replace_once(path, old, new):
    source = path.read_text(encoding='utf-8')
    if new in source:
        print('ALREADY PATCHED:', path)
        return
    if source.count(old) != 1:
        raise RuntimeError(f'Expected exactly one insertion point in {path}, found {source.count(old)}')
    path.write_text(source.replace(old, new, 1), encoding='utf-8')
    print('PATCHED:', path)


cross = Path('dtwise/cross_domain_join.py')
replace_once(cross,
    "    if ('productcatalog' in domains and 'assetinventory' in domains and len(domains) >= 3",
    "    from dtwise.schema_join_graph import plan_schema_join_graph\n"
    "    graph_plan = plan_schema_join_graph(question, catalog, schema, domains)\n"
    "    if graph_plan is not None:\n"
    "        return graph_plan\n"
    "    if ('productcatalog' in domains and 'assetinventory' in domains and len(domains) >= 3")

sparql = Path('dtwise/sparql_generator.py')
replace_once(sparql,
    '    if plan.get("join_type") == "schema_bridge_join":',
    '    if plan.get("join_type") == "schema_join_graph":\n'
    '        from dtwise.schema_join_graph import compile_schema_join_graph\n'
    '        return compile_schema_join_graph(plan, schema, limit, graph_mode, graph_iri,\n'
    '                                         include_graph, count_per_graph, iri)\n'
    '    if plan.get("join_type") == "schema_bridge_join":')

executor = Path('dtwise/rdf_executor.py')
replace_once(executor,
    '"identifier_equality", "multi_key_bridge_join", "schema_bridge_join"',
    '"identifier_equality", "multi_key_bridge_join", "schema_bridge_join", "schema_join_graph"')
replace_once(executor,
    "        if plan['join_type'] == 'schema_bridge_join':",
    "        if plan['join_type'] in ('schema_bridge_join', 'schema_join_graph'):")
replace_once(executor,
    "            key_values = [value(binding, f'joinKey{i}') for i in range(2)]",
    "            key_values = [value(binding, f'joinKey{i}') for i in range(len(keys))]")
replace_once(executor,
    '           if plan["join_type"] == "schema_bridge_join" else {}),',
    '           if plan["join_type"] == "schema_bridge_join" else {}),\n'
    '        **({"join_keys": plan["join_keys"], "bridge_domains": plan["bridge_domains"]}\n'
    '           if plan["join_type"] == "schema_join_graph" else {}),')
print('Integration complete. Run regression tests before deploying.')
