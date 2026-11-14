"""End-to-end operation tests: real SQLite, quota store, schema client; fake HTTP only."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from multicodex.quota_store import QuotaStore
from multicodex.workspace_admin_api import AdminAPI, AdminContract
from multicodex.workspace_operations import WorkspaceOperations, OperationError
from test_workspace_admin_api import contract

class Provider:
    def __init__(self):
        self.users = {'owner-a': {'id':'owner-a','email':'owner@example.com','role':'account-owner','seat_type':'default','is_scim_managed':False},
                      'user-a': {'id':'user-a','email':'a@example.com','role':'standard-user','seat_type':'default','is_scim_managed':False}}
        self.invites = {}
        self.writes = []
        self.disconnect_after_write = False
        self.ignore_update = False
    def page(self, rows):
        rows=copy.deepcopy(list(rows))
        return {'object':'list','data':rows,'has_more':False,'first_id':rows[0]['id'] if rows else None,'last_id':rows[-1]['id'] if rows else None}
    def __call__(self, method,url,key,body,timeout):
        path=urlsplit(url).path.split('/workspaces/w/')[1]
        pieces=path.split('/');group=pieces[0];items=self.users if group=='users' else self.invites
        ident=pieces[1] if len(pieces)>1 else None
        if method=='GET':
            if ident is None:return 200,self.page(items.values())
            if ident not in items:raise HTTPError(url,404,'not found',{},None)
            return 200,copy.deepcopy(items[ident])
        self.writes.append((method,path,copy.deepcopy(body)))
        if method=='PATCH':
            if not self.ignore_update:items[ident].update(body)
            result=(200,copy.deepcopy(items[ident]))
        elif method=='DELETE':
            items.pop(ident,None);result=(204,None)
        elif ident is None:
            items['invite-a']={'id':'invite-a','status':'pending',**body};result=(201,copy.deepcopy(items['invite-a']))
        else:
            result=(200,copy.deepcopy(items[ident]))
        if self.disconnect_after_write:raise URLError('sensitive upstream data')
        return result

class OperationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.now=1000;self.provider=Provider();self.api=AdminAPI(AdminContract(contract()),self.provider)
        self.quota=QuotaStore(self.root/'quota')
        self.account=self.quota.register(profile_id='Test',session_id='default',email='a@example.com',workspace_id='w',now=900)
        self.snap=self.quota.capture(self.account,{'source':'official-app-server','windows':[
            {'label':'primary','used_percent':95,'minutes':300,'reset_at':2000},
            {'label':'secondary','used_percent':40,'minutes':10080,'reset_at':9000}]},observed_at=950)
        self.ops=WorkspaceOperations(self.root/'admin',self.api,self.quota,clock=lambda:self.now)
    def tearDown(self):self.tmp.cleanup()
    def prepare(self,action='remove_user',**kw):
        return self.ops.prepare(action,'w','ephemeral-test-key',target=kw.pop('target','user-a'),
                                account_key=kw.pop('account_key',self.account),**kw)
    def authorized(self,**kw):
        op=self.prepare(**kw);self.ops.approve(op['operation_id'],op['digest']);return op['operation_id']
    def test_prepare_and_approve_do_not_send_writes(self):
        op=self.prepare();self.assertEqual(op['state'],'REVIEW_REQUIRED')
        self.assertEqual(op['snapshot_id'],self.snap['snapshot_id'])
        self.ops.approve(op['operation_id'],op['digest']);self.assertEqual(self.provider.writes,[])
    def test_unapproved_operation_never_executes(self):
        op=self.prepare()
        with self.assertRaises(OperationError):self.ops.execute(op['operation_id'],'key')
        self.assertEqual(self.provider.writes,[])
    def test_wrong_digest_cannot_approve_another_payload(self):
        op=self.prepare()
        with self.assertRaises(OperationError):self.ops.approve(op['operation_id'],'0'*64)
    def test_removal_requires_quota_evidence_before_network_mutation(self):
        blank=self.quota.register(profile_id='Blank',session_id='default',email='a@example.com',workspace_id='w',now=900)
        with self.assertRaises(OperationError) as error:self.prepare(account_key=blank)
        self.assertEqual(error.exception.code,'SNAPSHOT_REQUIRED');self.assertEqual(self.provider.writes,[])

    def test_role_change_requires_quota_evidence_before_network_mutation(self):
        self.provider.users['owner-b']={'id':'owner-b','email':'a@example.com','role':'account-owner',
                                       'seat_type':'default','is_scim_managed':False}
        blank=self.quota.register(profile_id='BlankRole',session_id='default',email='a@example.com',workspace_id='w',now=900)
        with self.assertRaises(OperationError) as error:
            self.prepare(action='update_user',target='owner-b',body={'role':'standard-user'},account_key=blank)
        self.assertEqual(error.exception.code,'SNAPSHOT_REQUIRED')
        self.assertEqual(self.provider.writes,[])
    def test_account_email_must_match_remote_member(self):
        wrong=self.quota.register(profile_id='Wrong',session_id='default',email='other@example.com',workspace_id='w',now=900)
        with self.assertRaises(OperationError):self.prepare(account_key=wrong)

    def test_provider_account_id_must_match_local_identity(self):
        account=self.quota.register(profile_id='Identified',session_id='default',
                                    email='a@example.com',account_id='provider-b',
                                    workspace_id='w',now=900)
        self.provider.users['user-a']['account_id']='provider-a'
        with self.assertRaises(OperationError) as error:
            self.prepare(account_key=account)
        self.assertEqual(error.exception.code,'ACCOUNT_MISMATCH')
        self.assertEqual(self.provider.writes,[])
    def test_known_other_workspace_is_not_relabelled(self):
        wrong=self.quota.register(profile_id='Wrong',session_id='default',email='a@example.com',workspace_id='other',now=900)
        with self.assertRaises(OperationError):self.prepare(account_key=wrong)
    def test_confirmed_removal_keeps_quota_and_marks_only_bound_context(self):
        identity=self.authorized();result=self.ops.execute(identity,'key')
        self.assertEqual(result['state'],'VERIFIED')
        self.assertNotIn('user-a',self.provider.users)
        self.assertEqual(self.quota.latest(self.account),self.snap)
        self.assertEqual(self.quota.account(self.account)['membership_state'],'ACCESS_REMOVED')
        self.assertEqual(self.provider.writes,[('DELETE','users/user-a',None)])
    def test_completed_operation_is_idempotent(self):
        identity=self.authorized();self.ops.execute(identity,'key');self.ops.execute(identity,'key')
        self.assertEqual(len(self.provider.writes),1)
    def test_operation_survives_reopening_database(self):
        identity=self.authorized()
        reopened=WorkspaceOperations(self.root/'admin',self.api,self.quota,clock=lambda:self.now)
        self.assertEqual(reopened.execute(identity,'key')['state'],'VERIFIED')
    def test_network_failure_is_reconciled_without_replaying_delete(self):
        identity=self.authorized();self.provider.disconnect_after_write=True
        result=self.ops.execute(identity,'key');self.assertEqual(result['state'],'OUTCOME_UNKNOWN')
        result=self.ops.reconcile(identity,'key');self.assertEqual(result['state'],'VERIFIED')
        self.assertEqual(len(self.provider.writes),1)
    def test_unknown_write_cannot_be_replayed(self):
        identity=self.authorized();self.provider.disconnect_after_write=True;self.ops.execute(identity,'key')
        with self.assertRaises(OperationError):self.ops.execute(identity,'key')
        self.assertEqual(len(self.provider.writes),1)
    def test_last_owner_cannot_be_removed_or_demoted(self):
        for action,body in (('remove_user',None),('update_user',{'role':'standard-user'})):
            with self.subTest(action=action),self.assertRaises(OperationError) as error:
                self.prepare(action,target='owner-a',body=body)
            self.assertEqual(error.exception.code,'LAST_OWNER')
        self.assertEqual(self.provider.writes,[])
    def test_scim_members_remain_with_identity_provider(self):
        self.provider.users['user-a']['is_scim_managed']=True
        with self.assertRaises(OperationError) as error:self.prepare()
        self.assertEqual(error.exception.code,'SCIM_MANAGED')
    def test_unknown_identity_management_blocks_mutation(self):
        del self.provider.users['user-a']['is_scim_managed']
        with self.assertRaises(OperationError):
            self.prepare()
        self.assertEqual(self.provider.writes,[])
    def test_changed_member_invalidates_approval(self):
        identity=self.authorized();self.provider.users['user-a']['seat_type']='usage_based'
        result=self.ops.execute(identity,'key')
        self.assertEqual(result['state'],'REVIEW_REQUIRED');self.assertEqual(self.provider.writes,[])
    def test_expired_approval_does_not_write(self):
        identity=self.authorized();self.now=2000
        result=self.ops.execute(identity,'key');self.assertEqual(result['state'],'EXPIRED');self.assertEqual(self.provider.writes,[])
    def test_duplicate_pending_operations_return_same_identity(self):
        a=self.prepare();b=self.prepare();self.assertEqual(a['operation_id'],b['operation_id'])
    def test_cancel_prevents_execution(self):
        identity=self.authorized();self.ops.cancel(identity)
        with self.assertRaises(OperationError):self.ops.execute(identity,'key')
        self.assertEqual(self.provider.writes,[])
    def test_member_update_requires_actual_readback(self):
        identity=self.authorized(action='update_user',body={'seat_type':'usage_based'})
        self.provider.ignore_update=True
        result=self.ops.execute(identity,'key');self.assertEqual(result['state'],'OUTCOME_UNKNOWN')
    def test_seat_change_is_verified_and_quota_values_are_not_reset(self):
        identity=self.authorized(action='update_user',body={'seat_type':'usage_based'})
        result=self.ops.execute(identity,'key');self.assertEqual(result['state'],'VERIFIED')
        self.assertEqual(self.quota.latest(self.account),self.snap)
    def test_create_invitation_is_pending_not_membership(self):
        op=self.ops.prepare('create_invite','w','key',body={'email':'new@example.com','role':'standard-user'})
        self.ops.approve(op['operation_id'],op['digest'])
        result=self.ops.execute(op['operation_id'],'key')
        self.assertEqual(result['state'],'AWAITING_ACCEPTANCE')
        self.assertEqual(result['result_id'],'invite-a');self.assertEqual(len(self.provider.writes),1)
    def test_existing_member_is_not_reinvited(self):
        with self.assertRaises(OperationError):self.ops.prepare('create_invite','w','key',body={'email':'a@example.com'})
        self.assertEqual(self.provider.writes,[])
    def test_existing_invitation_prevents_duplicate_email(self):
        self.provider.invites['i']={'id':'i','email':'new@example.com','status':'pending'}
        with self.assertRaises(OperationError):self.ops.prepare('create_invite','w','key',body={'email':'new@example.com'})
    def test_resend_reports_acceptance_not_mail_delivery(self):
        self.provider.invites['i']={'id':'i','email':'new@example.com','status':'pending'}
        op=self.ops.prepare('resend_invite','w','key',target='i');self.ops.approve(op['operation_id'],op['digest'])
        self.assertEqual(self.ops.execute(op['operation_id'],'key')['state'],'REQUEST_ACCEPTED')
    def test_cancel_invite_readback_is_verified(self):
        self.provider.invites['i']={'id':'i','email':'new@example.com','status':'pending'}
        op=self.ops.prepare('cancel_invite','w','key',target='i');self.ops.approve(op['operation_id'],op['digest'])
        self.assertEqual(self.ops.execute(op['operation_id'],'key')['state'],'VERIFIED')
    def test_key_never_reaches_database_or_public_operation(self):
        identity=self.authorized();self.ops.execute(identity,'unique-private-key')
        for path in (self.root/'admin').glob('*'):
            if path.is_file():self.assertNotIn(b'unique-private-key',path.read_bytes())
        self.assertNotIn('unique-private-key',json.dumps(self.ops.list()))
    def test_no_arbitrary_payloads_are_persisted(self):
        with self.assertRaises(OperationError):self.prepare('update_user',body={'token':'secret'})
        for path in (self.root/'admin').glob('*'):
            if path.is_file():self.assertNotIn(b'secret',path.read_bytes())
    def test_symlink_directory_is_rejected(self):
        link=self.root/'link'
        try:
            link.symlink_to(self.root/'admin',target_is_directory=True)
        except OSError as exc:
            if getattr(exc, 'winerror', None) == 1314:
                self.skipTest('symlink privilege unavailable')
            raise
        with self.assertRaises(OperationError):WorkspaceOperations(link,self.api,self.quota)

    def test_expired_unexecuted_review_can_be_prepared_again(self):
        first=self.prepare();self.now=1400;second=self.prepare()
        self.assertNotEqual(first['operation_id'],second['operation_id'])
        self.assertEqual(self.ops.get(first['operation_id'])['state'],'EXPIRED')
    def test_account_key_is_validated_even_without_snapshot_requirement(self):
        with self.assertRaises(OperationError):
            self.prepare('update_user',body={'role':'standard-user'},account_key='secret-key')
    def test_authorization_is_bound_to_exact_request_route(self):
        op=self.ops.prepare('create_invite','w','key',body={'email':'new@example.com'})
        self.ops.approve(op['operation_id'],op['digest'])
        d=contract()
        for path in list(d['paths']):
            if '/invitations' in path:d['paths'][path.replace('/invitations','/invites')]=d['paths'].pop(path)
        self.ops.api=AdminAPI(AdminContract(d),self.provider)
        result=self.ops.execute(op['operation_id'],'key')
        self.assertNotEqual(result['state'],'AWAITING_ACCEPTANCE')
        self.assertEqual(self.provider.writes,[])
    def test_unknown_quota_scope_is_not_marked_removed_globally(self):
        account=self.quota.register(profile_id='Unknown',session_id='default',email='a@example.com',now=900)
        self.quota.capture(account,{'source':'official-app-server','windows':[]},observed_at=950)
        op=self.prepare(account_key=account);self.ops.approve(op['operation_id'],op['digest'])
        self.assertEqual(self.ops.execute(op['operation_id'],'key')['state'],'VERIFIED')
        self.assertEqual(self.quota.account(account)['membership_state'],'WORKSPACE_ACCESS_UNKNOWN')
    def test_lease_blocks_other_mutation_in_same_workspace(self):
        identity=self.authorized()
        with self.ops._db() as db:db.execute('INSERT INTO leases VALUES(?,?,?)',('w','another-process',2000))
        with self.assertRaises(OperationError) as err:self.ops.execute(identity,'key')
        self.assertEqual(err.exception.code,'BUSY');self.assertEqual(self.provider.writes,[])
    def test_crashed_execution_recovers_only_to_readback(self):
        identity=self.authorized()
        with self.ops._db() as db:
            row=self.ops._load(db,identity);row['state']='EXECUTING';self.ops._save(db,row)
        with self.assertRaises(OperationError):self.ops.recover(identity)
        self.now=1400;self.assertEqual(self.ops.recover(identity)['state'],'OUTCOME_UNKNOWN')
        with self.assertRaises(OperationError):self.ops.execute(identity,'key')
        self.assertEqual(self.provider.writes,[])

if __name__=='__main__':unittest.main()
