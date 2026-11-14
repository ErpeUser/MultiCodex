"""Regression tests for contract-pinned approvals and read-only fields."""
import unittest
from multicodex.workspace_admin_api import AdminContract, AdminAPIError
from test_workspace_admin_api import contract

class ContractSecurityTests(unittest.TestCase):
    def test_readonly_request_properties_are_not_writable(self):
        d=contract();d['components']['schemas']['Update']['properties']['role']['readOnly']=True
        with self.assertRaises(AdminAPIError):AdminContract(d).request('update_user','w',target='u',body={'role':'standard-user'})
    def test_contract_digest_changes_even_if_version_does_not(self):
        d=contract();before=AdminContract(d).fingerprint
        d['components']['schemas']['Update']['properties']['role']['enum'].append('new-role')
        self.assertNotEqual(AdminContract(d).fingerprint,before)

