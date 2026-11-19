import unittest
from multicodex.profile_router import eligibility


class RoutingTests(unittest.TestCase):
    def row(self):
        return {'account': {'account_key': 'a' * 64, 'profile_id': 'Work',
                            'auth_state': 'AUTHENTICATED',
                            'membership_state': 'WORKSPACE_MEMBER', 'workspace_id': 'workspace'},
                'binding_available': True,
                'quota': {'freshness': 'LIVE_VERIFIED', 'capacity_confirmed': True,
                          'status': 'VERIFIED_AVAILABLE'}}

    def test_verified_allowlisted_profile_is_eligible(self):
        self.assertIsNone(eligibility(self.row(), ['Work']))

    def test_stale_quota_is_not_eligible(self):
        row = self.row()
        row['quota']['freshness'] = 'STALE'
        self.assertEqual(eligibility(row, ['Work']), 'QUOTA_UNAVAILABLE')

    def test_removed_member_is_not_eligible(self):
        row = self.row()
        row['account']['membership_state'] = 'ACCESS_REMOVED'
        self.assertEqual(eligibility(row, ['Work']), 'ACCESS_REMOVED')

    def test_requested_workspace_must_match(self):
        self.assertEqual(eligibility(self.row(), ['Work'], workspace_id='other'),
                         'CONTEXT_CHANGED')

    def test_unbound_or_non_allowlisted_profile_is_not_eligible(self):
        row = self.row()
        row['binding_available'] = False
        self.assertEqual(eligibility(row, ['Work']), 'AUTH_REQUIRED')
        self.assertEqual(eligibility(self.row(), []), 'NOT_ALLOWLISTED')


if __name__ == '__main__':
    unittest.main()
