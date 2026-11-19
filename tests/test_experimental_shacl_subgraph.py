"""Regression tests for the experimental DEXPI subgraph extractor."""
from pathlib import Path

from process_sim.dtwise.experimental_shacl_subgraph import load_index, extract_question

INDEX = Path(__file__).resolve().parents[1] / "semantic" / "ontology2" / "dtwise" / "dtwise-schema-index.json"


def _index():
    # Resolve from repository root without depending on current working directory.
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "semantic/ontology2/dtwise/dtwise-schema-index.json"
        if candidate.exists():
            return load_index(candidate)
    raise FileNotFoundError("DEXPI schema index fixture not found")


def test_instrumentation_property_without_root():
    result = extract_question(_index(), "Show MeasuredVariable from InstrumentationFunction")
    assert any(n["name"] == "InstrumentationFunction" for n in result["nodes"])
    assert any(p["predicate"].endswith("/hasMeasuredVariable") for p in result["properties"])
    assert not result["edges"]


def test_actuating_property_without_root():
    result = extract_question(_index(), "Show ActuatedVariable from ActuatingFunction")
    assert any(n["name"] == "ActuatingFunction" for n in result["nodes"])
    assert any(p["predicate"].endswith("/hasActuatedVariable") for p in result["properties"])


def test_independent_functions_remain_disconnected():
    result = extract_question(
        _index(),
        "Show MeasuredVariable of InstrumentationFunction and ActuatedVariable of ActuatingFunction",
    )
    assert len(result["nodes"]) == 2
    assert result["edges"] == []
    assert {p["predicate"].rsplit("/", 1)[-1] for p in result["properties"]} == {
        "hasMeasuredVariable", "hasActuatedVariable"
    }


def test_root_to_instrumentation_evidence():
    index = _index()
    root = next(uri for uri, c in index.shapes.items() if "DEXPI" in c.get("labels", []))
    instrument = next(uri for uri, c in index.shapes.items() if "InstrumentationFunction" in c.get("labels", []))
    result = index.extract([root, instrument], connect=True)
    assert any(e["predicate"].endswith("/hasInstrumentationFunction") for e in result["edges"])
    assert all(e["evidence"] for e in result["edges"])


def _domain_index(domain):
    return load_index(INDEX, domain=domain)


def _assert_nested_path(domain, question, node_names, predicates, property_name):
    result = extract_question(_domain_index(domain), question, connect=True)
    assert {n["name"] for n in result["nodes"]} == set(node_names)
    assert {e["predicate"].rsplit("/", 1)[-1] for e in result["edges"]} == set(predicates)
    assert len(result["properties"]) == 1
    assert result["properties"][0]["name"] == property_name
    assert result["unresolved_connections"] == []
    assert all(edge["evidence"] for edge in result["edges"])


def test_opcua_nested_signal_mapping():
    _assert_nested_path(
        "opcuaconnectivity",
        "Show OPCUANodeId of SignalMapping in TEP_OPCUAConnectivity",
        {"TEP_OPCUAConnectivity", "SignalMapping"},
        {"hasSignalMapping"},
        "OPCUANodeId",
    )


def test_assetinventory_nested_asset():
    _assert_nested_path(
        "assetinventory",
        "Show EquipmentTag of Asset in AssetInventory",
        {"AssetInventory", "Asset"},
        {"hasAsset"},
        "EquipmentTag",
    )


def test_ecad_device_endpoint_not_symbol_or_plc():
    result = extract_question(
        _domain_index("ecad"),
        "Show Address of EndPoint belonging to Device in ECAD",
        connect=True,
    )
    assert {n["name"] for n in result["nodes"]} == {"ECAD", "Device", "EndPoint"}
    assert len(result["nodes"]) == 3
    assert len(result["edges"]) == 2
    assert len(result["properties"]) == 1
    assert result["properties"][0]["name"] == "Address"
    assert result["unresolved_connections"] == []
    assert "ambiguous_paths" not in result
    assert all(e["evidence"] for e in result["edges"])


def test_ecad_leaf_only_address_preserves_four_alternatives():
    """An underspecified leaf must not silently choose Device/Symbol or PLC."""
    result = extract_question(
        _domain_index("ecad"), "Show Address in ECAD", connect=True
    )
    assert len(result["nodes"]) == 7
    assert len(result["edges"]) == 6
    assert len(result["properties"]) == 4
    assert len(result["ambiguous_paths"]) == 4
    assert len({p["target"] for p in result["ambiguous_paths"]}) == 4
    assert result["unresolved_connections"] == []
    assert all(edge["evidence"] for edge in result["edges"])
    assert all(prop["evidence"] for prop in result["properties"])


def test_dexpi_independent_branches_with_explicit_root_remain_disconnected():
    """A shared domain name alone is not an instruction to join siblings."""
    result = extract_question(
        _domain_index("dexpi"),
        "In DEXPI show MeasuredVariable of InstrumentationFunction "
        "and ActuatedVariable of ActuatingFunction",
        connect=False,
    )
    assert {p["name"] for p in result["properties"]} == {
        "MeasuredVariable", "ActuatedVariable"
    }
    assert result["edges"] == []
    assert result["unresolved_connections"] == []



def test_ecad_cross_branch_address_candidates_remain_disconnected():
    """Mentioning both branches does not imply a join when connect=False."""
    result = extract_question(
        _domain_index("ecad"),
        "Show Address of EndPoint in Device and Symbol in ECAD",
        connect=False,
    )
    assert result["edges"] == []
    assert len(result["properties"]) == 4
    assert len({p["owner"] for p in result["properties"]}) == 4
    assert result["unresolved_connections"] == []


def test_dexpi_explicit_same_root_connects_both_branches():
    result = extract_question(
        _domain_index("dexpi"),
        "Show MeasuredVariable of InstrumentationFunction and "
        "ActuatedVariable of ActuatingFunction belonging to the same DEXPI",
        connect=True,
    )
    assert {n["name"] for n in result["nodes"]} == {
        "DEXPI", "InstrumentationFunction", "ActuatingFunction"
    }
    assert {e["predicate"].rsplit("/", 1)[-1] for e in result["edges"]} == {
        "hasInstrumentationFunction", "hasActuatingFunction"
    }
    assert {p["name"] for p in result["properties"]} == {
        "MeasuredVariable", "ActuatedVariable"
    }
    assert len(result["edges"]) == 2
    assert len(result["properties"]) == 2
    assert result["unresolved_connections"] == []
    assert "shared_context" in result
    assert all(e["from"] == result["shared_context"] for e in result["edges"])
    assert all(e["evidence"] for e in result["edges"])


def test_dexpi_domain_mention_alone_does_not_assert_shared_context():
    result = extract_question(
        _domain_index("dexpi"),
        "In DEXPI show MeasuredVariable of InstrumentationFunction and "
        "ActuatedVariable of ActuatingFunction",
        connect=True,
    )
    assert "shared_context" not in result


def test_dexpi_same_root_does_not_force_join_when_connect_disabled():
    result = extract_question(
        _domain_index("dexpi"),
        "Show MeasuredVariable of InstrumentationFunction and "
        "ActuatedVariable of ActuatingFunction belonging to the same DEXPI",
        connect=False,
    )
    assert result["edges"] == []
    assert "shared_context" not in result


def test_compact_ecad_ambiguity_shows_four_readable_paths():
    from try_dexpi import format_compact

    result = extract_question(
        _domain_index("ecad"), "Show Address in ECAD", connect=True
    )
    output = format_compact(result)
    assert "Status: AMBIGUOUS" in output
    for branch in ("Device", "Symbol"):
        for leaf in ("EndPoint", "PLCEndPoint"):
            assert f"ECAD → {branch} → {leaf} → Address" in output
    assert "Alternatives: 4" in output
    assert "Unresolved: 0" in output
    assert "http://" not in output


def test_compact_dexpi_shared_context_shows_both_branches():
    from try_dexpi import format_compact

    result = extract_question(
        _domain_index("dexpi"),
        "Show MeasuredVariable of InstrumentationFunction and "
        "ActuatedVariable of ActuatingFunction belonging to the same DEXPI",
        connect=True,
    )
    output = format_compact(result)
    assert "Status: SHARED CONTEXT" in output
    assert "DEXPI → InstrumentationFunction → MeasuredVariable" in output
    assert "DEXPI → ActuatingFunction → ActuatedVariable" in output
    assert "Edges: 2" in output


def test_compact_disconnected_fragments_do_not_invent_paths():
    from try_dexpi import format_compact

    result = extract_question(
        _domain_index("dexpi"),
        "Show MeasuredVariable of InstrumentationFunction and "
        "ActuatedVariable of ActuatingFunction",
        connect=False,
    )
    output = format_compact(result)
    assert "InstrumentationFunction → MeasuredVariable" in output
    assert "ActuatingFunction → ActuatedVariable" in output
    assert "Edges: 0" in output


def test_llm_candidates_ecad_preserve_all_four_ambiguous_paths():
    from process_sim.dtwise.experimental_shacl_candidates import prepare_candidates

    result = extract_question(_domain_index("ecad"), "Show Address in ECAD", connect=True)
    prepared = prepare_candidates(result)
    candidates = prepared["prompt"]["candidates"]
    assert prepared["prompt"]["domain"] == "ecad"
    assert [c["id"] for c in candidates] == ["C1", "C2", "C3", "C4"]
    assert {c["path"] for c in candidates} == {
        f"ECAD → {branch} → {leaf} → Address"
        for branch in ("Device", "Symbol")
        for leaf in ("EndPoint", "PLCEndPoint")
    }
    assert set(prepared["registry"]) == {c["id"] for c in candidates}
    assert all(len(v["edges"]) == 2 for v in prepared["registry"].values())
    assert all(all(e["evidence"] for e in v["edges"]) for v in prepared["registry"].values())
    assert all(v["property"]["evidence"] for v in prepared["registry"].values())
    assert "http" not in str(prepared["prompt"])


def test_llm_candidates_dexpi_shared_context_keeps_two_paths():
    from process_sim.dtwise.experimental_shacl_candidates import prepare_candidates

    result = extract_question(
        _domain_index("dexpi"),
        "Show MeasuredVariable of InstrumentationFunction and "
        "ActuatedVariable of ActuatingFunction belonging to the same DEXPI",
        connect=True,
    )
    prepared = prepare_candidates(result)
    assert {c["path"] for c in prepared["prompt"]["candidates"]} == {
        "DEXPI → InstrumentationFunction → MeasuredVariable",
        "DEXPI → ActuatingFunction → ActuatedVariable",
    }


def test_llm_candidates_disconnected_branches_stay_separate():
    from process_sim.dtwise.experimental_shacl_candidates import prepare_candidates

    result = extract_question(
        _domain_index("dexpi"),
        "Show MeasuredVariable of InstrumentationFunction and "
        "ActuatedVariable of ActuatingFunction",
        connect=False,
    )
    prepared = prepare_candidates(result)
    assert {c["path"] for c in prepared["prompt"]["candidates"]} == {
        "InstrumentationFunction → MeasuredVariable",
        "ActuatingFunction → ActuatedVariable",
    }
    assert all(not v["edges"] for v in prepared["registry"].values())


def test_llm_candidates_budget_rejects_excess():
    import pytest
    from process_sim.dtwise.experimental_shacl_candidates import prepare_candidates

    result = extract_question(_domain_index("ecad"), "Show Address in ECAD", connect=True)
    with pytest.raises(ValueError, match="Candidate budget exceeded"):
        prepare_candidates(result, max_candidates=2)


def _prepared_ecad_selection():
    from process_sim.dtwise.experimental_shacl_candidates import prepare_candidates
    return prepare_candidates(
        extract_question(_domain_index("ecad"), "Show Address in ECAD", connect=True)
    )


def test_llm_selection_contract_accepts_known_id_from_json():
    import json
    from process_sim.dtwise.experimental_shacl_selection import validate_selection

    response = {"status": "selected", "selected_candidate_ids": ["C1"],
                "reason": "Device EndPoint specified"}
    assert validate_selection(json.dumps(response), _prepared_ecad_selection()) == response


def test_llm_selection_contract_preserves_ambiguity():
    from process_sim.dtwise.experimental_shacl_selection import validate_selection

    response = {"status": "ambiguous", "selected_candidate_ids": [],
                "reason": "Four equally plausible Address paths"}
    assert validate_selection(response, _prepared_ecad_selection()) == response


def test_llm_selection_contract_accepts_multiple_branches():
    from process_sim.dtwise.experimental_shacl_candidates import prepare_candidates
    from process_sim.dtwise.experimental_shacl_selection import validate_selection

    result = extract_question(
        _domain_index("dexpi"),
        "Show MeasuredVariable of InstrumentationFunction and "
        "ActuatedVariable of ActuatingFunction belonging to the same DEXPI",
        connect=True,
    )
    prepared = prepare_candidates(result)
    response = {"status": "selected", "selected_candidate_ids": ["C1", "C2"],
                "reason": "Both properties requested"}
    assert validate_selection(response, prepared) == response


def test_llm_selection_contract_rejects_invalid_responses():
    import pytest
    from process_sim.dtwise.experimental_shacl_selection import (
        SelectionContractError, validate_selection,
    )

    prepared = _prepared_ecad_selection()
    invalid = [
        "not json",
        "[]",
        {"status": "selected", "selected_candidate_ids": ["C99"], "reason": "invented"},
        {"status": "selected", "selected_candidate_ids": [], "reason": "empty"},
        {"status": "ambiguous", "selected_candidate_ids": ["C1"], "reason": "contradiction"},
        {"status": "unresolved", "selected_candidate_ids": ["C1"], "reason": "contradiction"},
        {"status": "selected", "selected_candidate_ids": ["C1", "C1"], "reason": "duplicate"},
        {"status": "selected", "selected_candidate_ids": ["C1"], "reason": ""},
        {"status": "selected", "selected_candidate_ids": "C1", "reason": "wrong type"},
        {"status": "selected", "selected_candidate_ids": ["C1"], "reason": "extra", "domain": "dexpi"},
        {"status": "guess", "selected_candidate_ids": [], "reason": "invalid status"},
    ]
    for response in invalid:
        with pytest.raises(SelectionContractError):
            validate_selection(response, prepared)


def test_llm_selection_contract_rejects_registry_mismatch():
    import pytest
    from process_sim.dtwise.experimental_shacl_selection import (
        SelectionContractError, validate_selection,
    )

    prepared = _prepared_ecad_selection()
    prepared["registry"].pop("C1")
    with pytest.raises(SelectionContractError, match="registry disagree"):
        validate_selection(
            {"status": "selected", "selected_candidate_ids": ["C2"], "reason": "test"},
            prepared,
        )


def test_ollama_pipeline_selects_verified_ecad_path_without_network():
    import json
    from process_sim.dtwise.experimental_shacl_ollama import run_local_selection

    calls = []
    def fake_transport(url, payload, timeout):
        calls.append((url, payload))
        return {"message": {"content": json.dumps({
            "status": "selected", "selected_candidate_ids": ["C1"],
            "reason": "Device EndPoint path",
        })}}

    result = run_local_selection(
        _domain_index("ecad"), "Show Address in ECAD", transport=fake_transport,
    )
    assert result["selection"]["status"] == "selected"
    assert result["selected_paths"][0]["path"] == "ECAD → Device → EndPoint → Address"
    assert len(result["selected_paths"][0]["verified"]["edges"]) == 2
    assert calls[0][0].endswith("/api/chat")
    assert calls[0][1]["model"] == "qwen2.5-coder:7b"
    assert calls[0][1]["options"]["temperature"] == 0
    assert len(json.loads(calls[0][1]["messages"][1]["content"])["candidates"]) == 4


def test_ollama_pipeline_preserves_ambiguous_response():
    from process_sim.dtwise.experimental_shacl_ollama import run_local_selection

    def fake_transport(url, payload, timeout):
        return {"message": {"content": '{"status":"ambiguous","selected_candidate_ids":[],"reason":"Four paths"}'}}
    result = run_local_selection(
        _domain_index("ecad"), "Show Address in ECAD", transport=fake_transport,
    )
    assert result["selection"]["status"] == "ambiguous"
    assert result["selected_paths"] == []


def test_ollama_pipeline_rejects_hallucinated_ids():
    import pytest
    from process_sim.dtwise.experimental_shacl_ollama import run_local_selection
    from process_sim.dtwise.experimental_shacl_selection import SelectionContractError

    def fake_transport(url, payload, timeout):
        return {"message": {"content": '{"status":"selected","selected_candidate_ids":["C999"],"reason":"guess"}'}}
    with pytest.raises(SelectionContractError, match="Unknown candidate"):
        run_local_selection(
            _domain_index("ecad"), "Show Address in ECAD", transport=fake_transport,
        )


def test_ollama_pipeline_no_candidates_skips_model():
    from process_sim.dtwise.experimental_shacl_ollama import run_local_selection

    def forbidden_transport(url, payload, timeout):
        raise AssertionError("Ollama should not be called")
    result = run_local_selection(
        _domain_index("ecad"), "Question with no schema labels",
        transport=forbidden_transport,
    )
    assert result["selection"]["status"] == "unresolved"
    assert result["selected_paths"] == []


def test_ollama_prompt_distinguishes_ambiguity_from_multiple_selection():
    from process_sim.dtwise.experimental_shacl_ollama import SYSTEM_PROMPT

    assert 'Show Address in ECAD' in SYSTEM_PROMPT
    assert '"status":"ambiguous"' in SYSTEM_PROMPT
    assert '"selected_candidate_ids":[]' in SYSTEM_PROMPT
    assert 'both EndPoint and PLCEndPoint' in SYSTEM_PROMPT
    assert '"selected_candidate_ids":["C1","C2"]' in SYSTEM_PROMPT
    assert "Do NOT select every path" in SYSTEM_PROMPT


def test_ollama_prompt_is_sent_with_ambiguous_ecad_candidates():
    import json
    from process_sim.dtwise.experimental_shacl_ollama import run_local_selection

    def fake_transport(url, payload, timeout):
        system = payload["messages"][0]["content"]
        user = json.loads(payload["messages"][1]["content"])
        assert "multiple possible owner paths" in system
        assert user["question"] == "Show Address in ECAD"
        assert len(user["candidates"]) == 4
        return {"message": {"content": json.dumps({
            "status": "ambiguous", "selected_candidate_ids": [],
            "reason": "No owner path specified",
        })}}

    result = run_local_selection(
        _domain_index("ecad"), "Show Address in ECAD", transport=fake_transport,
    )
    assert result["selection"]["status"] == "ambiguous"


def test_ollama_explicit_multiple_selection_can_validate():
    import json
    from process_sim.dtwise.experimental_shacl_ollama import run_local_selection

    question = "Show Address of both EndPoint and PLCEndPoint belonging to Device in ECAD"
    def fake_transport(url, payload, timeout):
        candidates = json.loads(payload["messages"][1]["content"])["candidates"]
        matches = [
            candidate["id"] for candidate in candidates
            if candidate["path"] in (
                "ECAD → Device → EndPoint → Address",
                "ECAD → Device → PLCEndPoint → Address",
            )
        ]
        assert len(matches) == 2
        return {"message": {"content": json.dumps({
            "status": "selected", "selected_candidate_ids": matches,
            "reason": "Both endpoint types requested",
        })}}

    result = run_local_selection(_domain_index("ecad"), question, transport=fake_transport)
    assert {p["path"] for p in result["selected_paths"]} == {
        "ECAD → Device → EndPoint → Address",
        "ECAD → Device → PLCEndPoint → Address",
    }


def test_semantic_schema_terms_are_domain_local():
    from process_sim.dtwise.experimental_shacl_semantic import schema_terms
    index = _domain_index("ecad")
    terms = schema_terms(index)
    assert any(t["kind"] == "property" and t["label"] == "Address" for t in terms)
    assert all(t["uri"] in index.shapes if t["kind"] == "shape"
               else t["owner"] in index.shapes for t in terms)


def test_semantic_ranking_mocked_embeddings_does_not_select_paths():
    from process_sim.dtwise.experimental_shacl_semantic import semantic_terms
    calls = []
    def fake_transport(url, payload, timeout):
        calls.append((url, payload))
        return {"embeddings": [[1.0, 0.0]] + [
            [1.0, 0.0] if "Address" in text else [0.0, 1.0]
            for text in payload["input"][1:]
        ]}
    result = semantic_terms(
        _domain_index("ecad"), "network addresses of connection points",
        top_k=5, transport=fake_transport,
    )
    assert result["domain"] == "ecad"
    assert any(t["label"] == "Address" for t in result["matches"])
    assert "selected_paths" not in result
    assert calls[0][0].endswith("/api/embed")
    assert calls[0][1]["model"] == "nomic-embed-text:latest"


def test_semantic_embeddings_reject_wrong_vector_count():
    import pytest
    from process_sim.dtwise.experimental_shacl_semantic import ollama_embed
    with pytest.raises(ValueError, match="Malformed"):
        ollama_embed(["a", "b"], transport=lambda url, payload, timeout: {
            "embeddings": [[1.0, 0.0]],
        })
