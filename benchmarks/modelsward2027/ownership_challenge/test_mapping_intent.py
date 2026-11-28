import unittest
from process_sim.dtwise.shacl_planner.mapping_intent import restrict_shared_key

class MappingIntentTests(unittest.TestCase):
    def setUp(self):
        self.graph={'identifier_path_candidates':[{'id':'a','path':'Root → Owner → AssetIdentifier'},{'id':'b','path':'Root → Other → AssetIdentifier'}],
                    'mapping_candidates':[{'id':'m','left_identifier_candidate_ids':['a'],'right_identifier_candidate_ids':['b'],'join_alternatives':[{'left_id':'a','right_id':'b'}]}]}
    def test_registered(self):
        self.assertEqual(len(restrict_shared_key('joined by AssetIdentifier',self.graph)['mapping_candidates']),1)
    def test_unregistered(self):
        self.assertEqual(restrict_shared_key('joined using LocalId',self.graph)['mapping_candidates'],[])
    def test_filter_is_not_join(self):
        self.assertEqual(len(restrict_shared_key('joined by AssetIdentifier with LocalId equal to X',self.graph)['mapping_candidates']),1)
    def test_sort_is_not_join(self):
        self.assertEqual(len(restrict_shared_key('joined by AssetIdentifier ordered by LocalId',self.graph)['mapping_candidates']),1)
    def test_implicit(self):
        self.assertIs(restrict_shared_key('matching entities',self.graph),self.graph)
    def test_unknown_key(self):
        self.assertEqual(restrict_shared_key('joined on UnknownKey',self.graph)['mapping_candidates'],[])
