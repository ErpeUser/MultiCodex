import unittest
from multicodex.profile_router import eligibility,rank_candidates

class RoutingTests(unittest.TestCase):
    def row(self,key='a',used=10):
        return {'account':{'account_key':key*64,'profile_id':'Work','auth_state':'AUTHENTICATED',
                          'membership_state':'WORKSPACE_MEMBER','workspace_id':'workspace'},
                'binding_available':True,'quota':{'freshness':'LIVE_VERIFIED','capacity_confirmed':True,
                'status':'VERIFIED_AVAILABLE','max_used_percent':used}}
    def test_unknown_or_stale_quota_is_not_a_candidate(self):
        row=self.row();row['quota']['freshness']='STALE'
        self.assertEqual(rank_candidates([row],['Work']),[])
    def test_removed_member_cannot_be_ranked(self):
        row=self.row();row['account']['membership_state']='ACCESS_REMOVED'
        self.assertEqual(eligibility(row,['Work']),'ACCESS_REMOVED')
    def test_requested_workspace_must_match(self):
        self.assertEqual(rank_candidates([self.row()],['Work'],workspace_id='other'),[])
    def test_order_is_deterministic_and_uses_all_window_summary(self):
        a,b=self.row('a',90),self.row('b',40)
        self.assertEqual([r['account']['account_key'] for r in rank_candidates([a,b],['Work'])],['b'*64,'a'*64])
    def test_unbound_login_or_non_allowlisted_profile_is_not_selected(self):
        row=self.row();row['binding_available']=False
        self.assertEqual(rank_candidates([row],['Work']),[])
        self.assertEqual(rank_candidates([self.row()],[]),[])
