import importlib
import importlib.util
import threading
import unittest
from urllib.error import HTTPError


def page(rows,more=False):
    return {'object':'list','data':rows,'has_more':more,
        'first_id':rows[0]['id'] if rows else None,'last_id':rows[-1]['id'] if rows else None}
def member(ident,email='person@example.invalid'):
    return {'object':'workspace.user','id':ident,'email':email}

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.workspace_provider'),'Workspace directory adapter missing')
        self.mod=importlib.import_module('multicodex.workspace_provider')
        self.calls=[];self.responses=[];self.cancel=threading.Event()
        def request(url,key,timeout):
            self.calls.append((url,key,timeout))
            return self.responses.pop(0)
        self.provider=self.mod.WorkspaceDirectory(request=request)
    def read(self,workspace='ws_test',key='test-secret'):
        return self.provider.read_members(workspace,key,cancel=self.cancel)
    def test_read_uses_official_scoped_endpoint_and_after_cursor(self):
        self.responses=[page([member('a')],True),page([member('b')])]
        result=self.read()
        self.assertEqual(result['workspace_id'],'ws_test')
        self.assertEqual([r['id'] for r in result['members']],['a','b'])
        self.assertEqual(self.calls[0][0],'https://api.chatgpt.com/v1/manage/workspaces/ws_test/users?limit=1000')
        self.assertEqual(self.calls[1][0],'https://api.chatgpt.com/v1/manage/workspaces/ws_test/users?limit=1000&after=a')
        self.assertNotIn('test-secret',repr(result))
    def test_inconsistent_page_is_rejected_not_partially_returned(self):
        bad=page([member('b')]);bad['last_id']='wrong'
        self.responses=[page([member('a')],True),bad]
        with self.assertRaises(self.mod.WorkspaceError):self.read()
    def test_duplicate_member_across_pages_fails_closed(self):
        self.responses=[page([member('a')],True),page([member('a')])]
        with self.assertRaises(self.mod.WorkspaceError):self.read()
    def test_empty_complete_directory_is_valid(self):
        self.responses=[page([])];self.assertEqual(self.read()['members'],[])
    def test_null_email_does_not_invent_identity(self):
        self.responses=[page([member('a',None)])]
        self.assertIsNone(self.read()['members'][0]['email'])
    def test_extra_response_data_and_credentials_are_not_retained(self):
        row={**member('a'),'access_token':'SENTINEL_SECRET','private_notes':'SENTINEL_SECRET'}
        self.responses=[page([row])]
        self.assertNotIn('SENTINEL_SECRET',repr(self.read()))
    def test_malformed_email_and_wrong_object_fail(self):
        for row in [member('a','bad\nmail'),member('a','bad\x00mail@example.invalid'),{**member('a'),'object':'organization.user'}]:
            self.responses=[page([row])]
            with self.assertRaises(self.mod.WorkspaceError):self.read()
    def test_path_injection_never_sends_key(self):
        for value in ['../other','ws?x=y','https://evil.invalid','ws%2Fother']:
            with self.assertRaises(self.mod.WorkspaceError):self.read(workspace=value)
        self.assertEqual(self.calls,[])
    def test_secret_header_injection_never_reaches_transport(self):
        for key in ['','a\nb','a\rb','a b']:
            with self.assertRaises(self.mod.WorkspaceError):self.read(key=key)
        self.assertEqual(self.calls,[])
    def test_cancel_prevents_network(self):
        self.cancel.set()
        with self.assertRaises(self.mod.WorkspaceError):self.read()
        self.assertEqual(self.calls,[])
    def test_unbounded_cursor_sequence_stops(self):
        self.provider=self.mod.WorkspaceDirectory(request=lambda *a:page([member('a')],True),max_pages=1)
        with self.assertRaises(self.mod.WorkspaceError):self.read()
    def test_transport_failure_never_leaks_key(self):
        def broken(*a):raise RuntimeError('SENTINEL_SECRET')
        self.provider=self.mod.WorkspaceDirectory(request=broken)
        with self.assertRaises(self.mod.WorkspaceError) as got:self.read()
        self.assertNotIn('SENTINEL_SECRET',str(got.exception))
    def test_http_forbidden_is_not_interpreted_as_empty_directory(self):
        def denied(*a):raise HTTPError('https://api.chatgpt.com',403,'SENTINEL_SECRET',{},None)
        self.provider=self.mod.WorkspaceDirectory(request=denied)
        with self.assertRaises(self.mod.WorkspaceError) as got:self.read()
        self.assertEqual(got.exception.code,'PERMISSION_DENIED')
    def test_redirect_handler_refuses_credential_forwarding(self):
        with self.assertRaises(self.mod.WorkspaceError):
            self.mod.NoRedirect().redirect_request(None,None,302,'',{},'https://evil.invalid')
    def test_invalid_boolean_pagination_is_rejected(self):
        row=page([member('a')]);row['has_more']=1;self.responses=[row]
        with self.assertRaises(self.mod.WorkspaceError):self.read()
