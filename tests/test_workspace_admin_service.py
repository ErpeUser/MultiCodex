"""Exercise the UI service against real journals and a synthetic HTTP boundary."""
import copy
import importlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from multicodex.quota_store import QuotaStore
from multicodex.workspace_admin_api import AdminAPI, AdminContract, AdminAPIError
from multicodex.workspace_operations import OperationError
from test_workspace_admin_api import contract


class DirectoryHTTP:
    def __init__(self):
        self.members = {
            'owner': {'id': 'owner', 'email': 'owner@example.invalid', 'role': 'account-owner',
                      'seat_type': 'default', 'is_scim_managed': False},
            'user': {'id': 'user', 'email': 'user@example.invalid', 'role': 'standard-user',
                     'seat_type': 'default', 'is_scim_managed': False}}
        self.invites = {}
        self.writes = []
        self.lose_response = False

    def __call__(self, method, url, key, body, timeout):
        assert key == 'temporary-test-key'
        tail = urlsplit(url).path.split('/workspaces/workspace-a/')[1]
        kind, _, target = tail.partition('/')
        rows = self.members if kind == 'users' else self.invites
        if method == 'GET':
            if target:
                return 200, copy.deepcopy(rows[target])
            data = copy.deepcopy(list(rows.values()))
            return 200, {'object': 'list', 'data': data, 'has_more': False,
                         'first_id': data[0]['id'] if data else None,
                         'last_id': data[-1]['id'] if data else None}
        self.writes.append((method, tail, copy.deepcopy(body)))
        if method == 'DELETE':
            del rows[target]
            result = (204, None)
        elif method == 'PATCH':
            rows[target].update(body)
            result = (200, copy.deepcopy(rows[target]))
        elif target.endswith('/resend'):
            result = (200, {'id': target.split('/')[0]})
        else:
            rows['invite-new'] = {'id': 'invite-new', **body, 'status': 'pending'}
            result = (201, copy.deepcopy(rows['invite-new']))
        if self.lose_response:
            raise OSError('PRIVATE RESPONSE MUST NOT ESCAPE')
        return result


class WorkspaceAdminServiceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.workspace_admin_service'))
        self.module = importlib.import_module('multicodex.workspace_admin_service')
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.quota = QuotaStore(self.root / 'quota')
        self.account = self.quota.register(profile_id='Work', session_id='default',
            email='user@example.invalid', account_id='user', workspace_id='workspace-a', now=900)
        self.quota.capture(self.account, {'source': 'official-app-server', 'windows': [
            {'label': 'primary', 'used_percent': 97, 'minutes': 300, 'reset_at': 2000},
            {'label': 'secondary', 'used_percent': 60, 'minutes': 10080, 'reset_at': 604800}]}, observed_at=950)
        self.http = DirectoryHTTP(); self.document = contract(); self.clock = 1000
        self.service = self.make_service()
        self.key = 'temporary-test-key'

    def make_service(self):
        return self.module.WorkspaceAdminService(self.root / 'admin', self.quota,
            contract_loader=lambda: AdminContract(self.document),
            api_factory=lambda c: AdminAPI(c, self.http), clock=lambda: self.clock)

    def connect(self):
        return self.service.connect('workspace-a', self.key)

    def prepare(self, action, **kwargs):
        body = kwargs.get('body') or {}
        if kwargs.get('account_key') is None and (
            action == 'remove_user' or
            action == 'update_user' and {'seat_type', 'role'} & set(body)
        ):
            kwargs['account_key'] = self.account
        return self.service.prepare(action, 'workspace-a', self.key, **kwargs)['selected']

    def execute(self, row):
        return self.service.execute(row['operation_id'], row['digest'], self.key)['selected']

    def test_connect_lists_members_and_capabilities_without_mutation(self):
        model = self.connect()
        self.assertEqual({r['id'] for r in model['members']}, {'owner', 'user'})
        self.assertEqual(set(model['capabilities']), {'create_invite','resend_invite','cancel_invite','update_user','remove_user'})
        self.assertTrue(model['capabilities']['remove_user']['enabled'])
        self.assertEqual(self.http.writes, [])
        self.assertNotIn(self.key, repr(model))

    def test_missing_contract_routes_disable_only_dependent_actions(self):
        self.document['paths'] = {k:v for k,v in self.document['paths'].items() if k.endswith('/users')}
        model = self.connect()
        self.assertFalse(any(c['enabled'] for c in model['capabilities'].values()))
        self.assertEqual(len(model['members']), 2)

    def test_prepare_does_not_write_and_binds_full_review(self):
        self.connect(); row = self.prepare('remove_user', target='user', account_key=self.account)
        self.assertEqual(row['state'], 'REVIEW_REQUIRED')
        self.assertEqual(row['review']['workspace_id'], 'workspace-a')
        self.assertIsNotNone(row['snapshot_id'])
        self.assertEqual(self.http.writes, [])

    def test_remove_executes_once_preserves_snapshot_and_readbacks(self):
        self.connect(); row = self.prepare('remove_user', target='user', account_key=self.account)
        result = self.execute(row)
        self.assertEqual(result['state'], 'VERIFIED')
        self.assertEqual(len(self.http.writes), 1)
        self.assertEqual(self.quota.latest(self.account)['primary_used_percent'], 97)
        self.assertEqual(self.quota.account(self.account)['membership_state'], 'ACCESS_REMOVED')
        with self.assertRaises(OperationError): self.execute(row)
        self.assertEqual(len(self.http.writes), 1)

    def test_invitation_waits_for_acceptance_not_false_success(self):
        self.connect(); row = self.prepare('create_invite', body={'email':'new@example.invalid','role':'standard-user'})
        result = self.execute(row)
        self.assertEqual(result['state'], 'AWAITING_ACCEPTANCE')
        self.http.invites.clear()
        self.http.members['new'] = {'id':'new','email':'new@example.invalid','role':'standard-user','is_scim_managed':False}
        result = self.service.action(row['operation_id'], 'reconcile', self.key)['selected']
        self.assertEqual(result['state'], 'VERIFIED')
        self.assertEqual(len(self.http.writes), 1)

    def test_role_change_is_verified(self):
        self.connect(); row = self.prepare('update_user', target='user', body={'role':'account-owner'})
        self.assertEqual(self.execute(row)['state'], 'VERIFIED')
        self.assertEqual(self.http.members['user']['role'], 'account-owner')

    def test_seat_change_preserves_history_and_requires_new_quota_check(self):
        self.connect(); row = self.prepare('update_user', target='user', body={'seat_type':'usage_based'}, account_key=self.account)
        self.assertEqual(self.execute(row)['state'], 'VERIFIED')
        self.assertEqual(self.quota.latest(self.account)['secondary_used_percent'], 60)
        self.assertEqual(self.quota.account(self.account)['membership_state'], 'WORKSPACE_ACCESS_UNKNOWN')

    def test_resend_acknowledges_request_not_delivery(self):
        self.http.invites['i']={'id':'i','email':'new@example.invalid','status':'pending'}
        self.connect(); row=self.prepare('resend_invite',target='i')
        self.assertEqual(self.execute(row)['state'], 'REQUEST_ACCEPTED')

    def test_cancel_invitation_verifies_absence(self):
        self.http.invites['i']={'id':'i','email':'new@example.invalid','status':'pending'}
        self.connect(); row=self.prepare('cancel_invite',target='i')
        self.assertEqual(self.execute(row)['state'], 'VERIFIED')
        self.assertNotIn('i',self.http.invites)

    def test_wrong_digest_never_authorizes_write(self):
        self.connect(); row=self.prepare('remove_user',target='user',account_key=self.account)
        with self.assertRaises(OperationError): self.service.execute(row['operation_id'],'0'*64,self.key)
        self.assertEqual(self.http.writes,[])

    def test_unknown_outcome_is_reconciled_without_replay(self):
        self.connect();row=self.prepare('remove_user',target='user',account_key=self.account)
        self.http.lose_response=True
        self.assertEqual(self.execute(row)['state'],'OUTCOME_UNKNOWN')
        self.assertEqual(self.service.action(row['operation_id'],'reconcile',self.key)['selected']['state'],'VERIFIED')
        self.assertEqual(len(self.http.writes),1)

    def test_contract_refresh_before_execution_demands_new_review(self):
        self.connect();row=self.prepare('update_user',target='user',body={'role':'account-owner'})
        self.document['info']['version']='test-new'
        result=self.execute(row)
        self.assertEqual(result['state'],'REVIEW_REQUIRED')
        self.assertNotEqual(result['operation_id'],row['operation_id'])
        self.assertEqual(self.http.writes,[])

    def test_disconnected_service_reads_history_but_cannot_execute(self):
        self.connect();row=self.prepare('update_user',target='user',body={'role':'account-owner'})
        other=self.make_service()
        self.assertEqual(other.history()[0]['operation_id'],row['operation_id'])
        with self.assertRaises(OperationError):other.execute(row['operation_id'],row['digest'],self.key)
        self.assertEqual(self.http.writes,[])

    def test_workspace_mismatch_is_rejected_before_preflight(self):
        self.connect()
        with self.assertRaises(OperationError):self.service.prepare('create_invite','other',self.key,body={'email':'x@example.invalid'})
        self.assertEqual(self.http.writes,[])

    def test_key_is_not_in_persisted_records_or_service_state(self):
        self.connect();row=self.prepare('update_user',target='user',body={'role':'account-owner'})
        self.execute(row)
        self.assertNotIn(self.key,repr(vars(self.service)))
        for path in self.root.rglob('*.sqlite3'):
            self.assertNotIn(self.key.encode(),path.read_bytes())

    def test_cancelling_local_review_never_changes_provider(self):
        self.connect();row=self.prepare('update_user',target='user',body={'role':'account-owner'})
        self.assertEqual(self.service.action(row['operation_id'],'cancel')['selected']['state'],'CANCELLED')
        self.assertEqual(self.http.writes,[])


if __name__=='__main__':unittest.main()
