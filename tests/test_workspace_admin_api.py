"""Contract tests use deliberately synthetic routes, not guessed live endpoints."""
import copy
import json
import unittest
from urllib.error import HTTPError, URLError
from multicodex.workspace_admin_api import AdminAPI, AdminContract, AdminAPIError

BASE = 'https://api.chatgpt.com/v1'
SCHEMA_URL = 'https://chatgpt.com/public/admin/api-reference/openapi.json'
USER = {'type': 'object', 'required': ['id', 'role', 'is_scim_managed'],
        'properties': {'id': {'type': 'string'}, 'role': {'type': 'string'},
                       'is_scim_managed': {'type': 'boolean'}}}

def contract():
    """Small, complete OpenAPI fixture; strings are intentionally test-only."""
    return {'openapi': '3.0.2', 'info': {'version': 'test-only'}, 'servers': [{'url': BASE}],
        'components': {'schemas': {'Update': {'type': 'object', 'additionalProperties': False,
            'properties': {'role': {'type': 'string', 'enum': ['account-owner', 'standard-user']},
                           'seat_type': {'type': 'string', 'enum': ['default', 'usage_based']}}}}},
        'paths': {
            '/manage/workspaces/{workspace_id}/users': {'get': {
                'parameters': [{'name': 'limit', 'in': 'query', 'schema': {'type': 'integer', 'minimum': 1, 'maximum': 100}}],
                'responses': {'200': {'content': {'application/json': {'schema': {'type': 'object'}}}}}}},
            '/manage/workspaces/{workspace_id}/users/{user_id}': {
                'get': {'responses': {'200': {'content': {'application/json': {'schema': USER}}}}},
                'patch': {'requestBody': {'required': True, 'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Update'}}}},
                    'responses': {'200': {'content': {'application/json': {'schema': USER}}}}},
                'delete': {'responses': {'204': {'description': 'removed'}}}},
            '/manage/workspaces/{workspace_id}/invitations': {
                'get': {'responses': {'200': {'content': {'application/json': {'schema': {'type': 'object'}}}}}},
                'post': {'requestBody': {'required': True, 'content': {'application/json': {'schema': {
                    'type': 'object', 'required': ['email'], 'additionalProperties': False,
                    'properties': {'email': {'type': 'string', 'format': 'email'},
                                   'role': {'type': 'string', 'enum': ['standard-user']}}}}}},
                    'responses': {'201': {'content': {'application/json': {'schema': {'type': 'object', 'required': ['id'], 'properties': {'id': {'type': 'string'}}}}}}}}},
            '/manage/workspaces/{workspace_id}/invitations/{invitation_id}': {
                'get': {'responses': {'200': {'content': {'application/json': {'schema': {'type': 'object'}}}}}},
                'delete': {'responses': {'204': {'description': 'removed'}}}},
            '/manage/workspaces/{workspace_id}/invitations/{invitation_id}/resend': {
                'post': {'responses': {'200': {'content': {'application/json': {'schema': {'type': 'object'}}}}}}},
            '/compliance/workspaces/{workspace_id}/users/{user_id}/memories': {
                'delete': {'responses': {'204': {'description': 'never allowed'}}}}
        }}

class RecordingTransport:
    def __init__(self, status=200, value=None):
        self.status = status
        self.value = value if value is not None else {'id': 'user-a', 'role': 'standard-user', 'is_scim_managed': False}
        self.requests = []
    def __call__(self, method, url, key, body, timeout):
        self.requests.append((method, url, body))
        return self.status, self.value

class AdminContractTests(unittest.TestCase):
    def test_discovers_only_present_workspace_operations(self):
        c = AdminContract(contract())
        self.assertEqual(set(c.operations), {'list_users','get_user','update_user','remove_user',
            'list_invites','get_invite','create_invite','resend_invite','cancel_invite'})
        self.assertNotIn('delete_memories', c.operations)
    def test_old_contract_does_not_invent_mutation_capabilities(self):
        d = contract(); d['paths'] = {'/manage/workspaces/{workspace_id}/users': d['paths']['/manage/workspaces/{workspace_id}/users']}
        c = AdminContract(d)
        self.assertEqual(list(c.operations), ['list_users'])
        with self.assertRaises(AdminAPIError): c.request('create_invite', 'workspace-a', body={'email':'a@example.com'})
    def test_schema_values_are_not_hardcoded_seat_names(self):
        c = AdminContract(contract())
        self.assertEqual(c.choices('update_user','seat_type'), ('default','usage_based'))
    def test_refs_are_resolved_and_input_fields_validated(self):
        c = AdminContract(contract())
        req = c.request('update_user','workspace-a', target='user-a', body={'role':'standard-user'})
        self.assertEqual(req[:2], ('PATCH', BASE+'/manage/workspaces/workspace-a/users/user-a'))
        self.assertEqual(req[2], {'role':'standard-user'})
        for body in ({'role':'owner'}, {'token':'secret'}, {'role':1}, {}):
            with self.subTest(body=body), self.assertRaises(AdminAPIError):
                c.request('update_user','workspace-a',target='user-a',body=body)
    def test_external_refs_and_contract_servers_are_rejected(self):
        for replacement in ('https://attacker.example/v1', 'http://api.chatgpt.com/v1', BASE+'@attacker.example'):
            d = contract(); d['servers'][0]['url'] = replacement
            with self.subTest(server=replacement), self.assertRaises(AdminAPIError): AdminContract(d)
        d=contract(); d['components']['schemas']['Update']={'$ref':'https://attacker.example/schema'}
        with self.assertRaises(AdminAPIError): AdminContract(d).request('update_user','w',target='u',body={'role':'standard-user'})
    def test_path_and_operation_server_overrides_are_rejected(self):
        for place in ('path','operation'):
            d=contract(); p=d['paths']['/manage/workspaces/{workspace_id}/users']
            (p if place=='path' else p['get'])['servers']=[{'url':'https://attacker.example'}]
            with self.subTest(place=place), self.assertRaises(AdminAPIError): AdminContract(d)
    def test_traversal_and_header_controls_cannot_enter_a_request(self):
        c=AdminContract(contract())
        for target in ('../users','u/other','u?x=1','u\r\nX:y',''):
            with self.subTest(target=target), self.assertRaises(AdminAPIError): c.request('get_user','w',target=target)
    def test_email_validation_rejects_controls_or_missing_at(self):
        c=AdminContract(contract())
        for email in ('not-an-email','x@example.com\n','x@','x y@example.com'):
            with self.subTest(email=email), self.assertRaises(AdminAPIError): c.request('create_invite','w',body={'email':email})
    def test_query_is_checked_against_contract_not_arbitrary_parameters(self):
        c=AdminContract(contract())
        self.assertEqual(c.request('list_users','w',query={'limit':5})[1], BASE+'/manage/workspaces/w/users?limit=5')
        for q in ({'limit':101},{'limit':True},{'evil':'x'}):
            with self.subTest(query=q), self.assertRaises(AdminAPIError): c.request('list_users','w',query=q)
    def test_ambiguous_mutation_is_rejected(self):
        d=contract(); p=d['paths']['/manage/workspaces/{workspace_id}/users/{user_id}'];p['post']=copy.deepcopy(p['patch'])
        with self.assertRaises(AdminAPIError): AdminContract(d)
    def test_recursive_ref_is_bounded(self):
        d=contract();d['components']['schemas']['Update']={'$ref':'#/components/schemas/Update'}
        with self.assertRaises(AdminAPIError): AdminContract(d).request('update_user','w',target='u',body={'role':'standard-user'})
    def test_oneof_accepts_exactly_one_shape(self):
        d=contract();d['components']['schemas']['Update']={'oneOf':[
          {'type':'object','required':['role'],'additionalProperties':False,'properties':{'role':{'type':'string'}}},
          {'type':'object','required':['seat_type'],'additionalProperties':False,'properties':{'seat_type':{'type':'string'}}}]}
        c=AdminContract(d)
        self.assertEqual(c.request('update_user','w',target='u',body={'role':'member'})[2],{'role':'member'})
        with self.assertRaises(AdminAPIError): c.request('update_user','w',target='u',body={'role':'member','seat_type':'default'})
    def test_unsupported_schema_constraints_fail_closed(self):
        d=contract();d['components']['schemas']['Update']['not']={'required':['role']}
        with self.assertRaises(AdminAPIError): AdminContract(d).request('update_user','w',target='u',body={'role':'standard-user'})
    def test_contract_is_immutable_after_validation(self):
        d=contract();c=AdminContract(d);d['servers'][0]['url']='https://attacker.example'
        self.assertEqual(c.request('get_user','w',target='u')[1], BASE+'/manage/workspaces/w/users/u')

class AdminAPITests(unittest.TestCase):
    def test_writes_require_explicit_authorization_per_call(self):
        t=RecordingTransport();api=AdminAPI(AdminContract(contract()),t)
        with self.assertRaises(AdminAPIError):api.call('update_user','w','test-key',target='u',body={'role':'standard-user'})
        self.assertEqual(t.requests,[])
        r=api.call('update_user','w','test-key',target='u',body={'role':'standard-user'},allow_write=True)
        self.assertEqual(r['role'],'standard-user')
    def test_response_validation_happens_before_success(self):
        api=AdminAPI(AdminContract(contract()),RecordingTransport(value={'id':'u'}))
        with self.assertRaises(AdminAPIError) as caught:api.call('get_user','w','test-key',target='u')
        self.assertEqual(caught.exception.code,'RESPONSE_INVALID')
    def test_undocumented_response_status_is_not_success(self):
        api=AdminAPI(AdminContract(contract()),RecordingTransport(status=202))
        with self.assertRaises(AdminAPIError):api.call('get_user','w','test-key',target='u')
    def test_no_content_is_accepted_only_when_documented(self):
        api=AdminAPI(AdminContract(contract()),RecordingTransport(status=204,value={}))
        self.assertIsNone(api.call('remove_user','w','test-key',target='u',allow_write=True))
    def test_credential_is_not_retained_in_client(self):
        api=AdminAPI(AdminContract(contract()),RecordingTransport())
        api.call('get_user','w','test-ephemeral-key',target='u')
        self.assertNotIn('test-ephemeral-key',repr(vars(api)))
    def test_invalid_key_is_rejected_before_transport(self):
        t=RecordingTransport();api=AdminAPI(AdminContract(contract()),t)
        for key in ('','key\r\nHeader:x','bearer key'):
            with self.assertRaises(AdminAPIError):api.call('get_user','w',key,target='u')
        self.assertEqual(t.requests,[])
    def test_write_transport_failure_is_unknown_not_safe_to_retry(self):
        def fail(*args):raise URLError('provider secret text')
        api=AdminAPI(AdminContract(contract()),fail)
        with self.assertRaises(AdminAPIError) as c:api.call('update_user','w','key',target='u',body={'role':'standard-user'},allow_write=True)
        self.assertTrue(c.exception.outcome_unknown)
        self.assertNotIn('provider secret',str(c.exception))
    def test_permission_failure_does_not_leak_provider_text_or_retry(self):
        calls=[]
        def deny(*args):
            calls.append(1);raise HTTPError(BASE,403,'provider-secret',{},None)
        api=AdminAPI(AdminContract(contract()),deny)
        with self.assertRaises(AdminAPIError) as c:api.call('update_user','w','key',target='u',body={'role':'standard-user'},allow_write=True)
        self.assertEqual(c.exception.code,'PERMISSION_DENIED');self.assertFalse(c.exception.outcome_unknown)
        self.assertEqual(len(calls),1)
    def test_rate_limit_preserves_bounded_retry_after_without_retrying(self):
        def rate(*args):raise HTTPError(BASE,429,'secret',{'Retry-After':'17'},None)
        with self.assertRaises(AdminAPIError) as c:AdminAPI(AdminContract(contract()),rate).call('get_user','w','key',target='u')
        self.assertEqual(c.exception.retry_after,17)
    def test_bad_write_response_is_unknown_until_readback(self):
        api=AdminAPI(AdminContract(contract()),RecordingTransport(value={'id':'u'}))
        with self.assertRaises(AdminAPIError) as c:api.call('update_user','w','key',target='u',body={'role':'standard-user'},allow_write=True)
        self.assertTrue(c.exception.outcome_unknown)

if __name__=='__main__':unittest.main()
