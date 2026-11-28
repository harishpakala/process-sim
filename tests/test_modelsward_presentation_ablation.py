from process_sim.dtwise.shacl_planner.presentation_ablation import ablate_prompt

def test_preserves_ids_and_mapping_pairs_without_mutation():
    p={'question':'Show Device LocalId','candidates':[{'id':'P1','kind':'property','domain':'ecad','path':'ECAD → Device → LocalId'},{'id':'P2','kind':'property','domain':'ecad','path':'ECAD → Symbol → LocalId'},{'id':'R1','kind':'result','path':'ECAD → Device','identifier_path_ids':['I1']}],'identifier_path_candidates':[{'id':'I1','domain':'ecad','owner':'Device','property':'AssetIdentifier'}],'mapping_candidates':[{'id':'M1','allowed_pairs':[['I1','I2']]}]}
    a=ablate_prompt(p)
    assert [c['id'] for c in a['candidates']]==['P1','P2','R1']
    assert [c['path'] for c in a['candidates']]==['LocalId','LocalId','Device']
    assert 'identifier_path_ids' not in a['candidates'][2]
    assert 'owner' not in a['identifier_path_candidates'][0]
    assert a['mapping_candidates']==p['mapping_candidates']
    assert p['candidates'][0]['path']=='ECAD → Device → LocalId'
    assert p['identifier_path_candidates'][0]['owner']=='Device'
