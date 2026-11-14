"""The bridge queues I/O and handles lifecycle boundaries on the UI thread."""
import importlib
import importlib.util
import unittest
from types import SimpleNamespace


class Host:
    def __init__(self):
        self.closing=False;self.mutating=False;self.theme_name='dark';self.jobs=[];self.status=[];self.accept=True
    def _submit(self,key,work,callback,**kwargs):
        if not self.accept:return False
        self.jobs.append((key,work,callback,kwargs));return True
    def _set_status(self,text):self.status.append(text)


class Service:
    def __init__(self):self.calls=[]
    def view(self):return {'records':[],'capabilities':{},'workspace_id':None}
    def connect(self,workspace_id,key):self.calls.append(('connect',workspace_id,key));return self.view()
    def prepare(self,*args,**kwargs):self.calls.append(('prepare',args,kwargs));return self.view()
    def execute(self,*args):self.calls.append(('execute',args));return self.view()
    def action(self,*args,**kwargs):self.calls.append(('action',args,kwargs));return self.view()


class AdminGuiBridgeTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.workspace_admin_gui'))
        module=importlib.import_module('multicodex.workspace_admin_gui')
        self.host=Host();self.service=Service();self.factories=[]
        def factory():self.factories.append('created');return self.service
        self.bridge=module.WorkspaceAdminGuiController(self.host, '/unused',service_factory=factory)
    def test_connect_is_queued_not_called_in_handler(self):
        self.bridge.event('connect',{'workspace_id':'w','key':'transient'})
        self.assertEqual(self.factories,[]);self.assertEqual(self.service.calls,[])
        key,work,callback,options=self.host.jobs[0]
        self.assertEqual(key,'workspace-admin');self.assertTrue(options['mutation'])
        callback(work());self.assertEqual(self.service.calls,[('connect','w','transient')])
        self.assertNotIn('transient',repr(self.bridge.model))
    def test_execute_passes_review_digest_unmodified(self):
        self.bridge.event('execute',{'identity':'a'*32,'digest':'b'*64,'key':'test-key'})
        self.host.jobs[0][1]()
        self.assertEqual(self.service.calls,[('execute',('a'*32,'b'*64,'test-key'))])
    def test_prepare_preserves_explicit_quota_mapping(self):
        data={'action':'remove_user','workspace_id':'w','target':'u','account_key':'c'*64,'key':'k'}
        self.bridge.event('prepare',data);self.host.jobs[0][1]()
        self.assertEqual(self.service.calls[0],('prepare',('remove_user','w','k'),{'target':'u','body':None,'account_key':'c'*64}))
    def test_unknown_command_is_not_queued(self):
        self.bridge.event('delete_everything',{})
        self.assertEqual(self.host.jobs,[])
    def test_mutating_host_and_closed_bridge_reject_commands(self):
        self.host.mutating=True;self.bridge.event('connect',{'workspace_id':'w','key':'k'})
        self.host.mutating=False;self.bridge.close();self.bridge.event('connect',{'workspace_id':'w','key':'k'})
        self.assertEqual(self.host.jobs,[])
    def test_busy_queue_does_not_leave_controller_stuck(self):
        self.host.accept=False;self.bridge.event('connect',{'workspace_id':'w','key':'k'})
        self.assertFalse(self.bridge.busy)
    def test_raw_provider_error_is_not_reported(self):
        self.bridge.event('connect',{'workspace_id':'w','key':'k'})
        self.host.jobs[0][3]['error_callback'](RuntimeError('SENSITIVE_PROVIDER_TEXT'))
        self.assertNotIn('SENSITIVE_PROVIDER_TEXT',' '.join(self.host.status))
        self.assertFalse(self.bridge.busy)
    def test_late_callback_does_not_render_closed_host(self):
        self.bridge.event('connect',{'workspace_id':'w','key':'k'});self.host.closing=True
        self.host.jobs[0][2]({'records':[{'sentinel':True}]})
        self.assertEqual(self.bridge.model['records'],[])
    def test_payload_is_copied_before_background_execution(self):
        data={'action':'update_user','workspace_id':'w','target':'u','body':{'role':'member'},'key':'k'}
        self.bridge.event('prepare',data);data['body']['role']='owner';self.host.jobs[0][1]()
        self.assertEqual(self.service.calls[0][2]['body'],{'role':'member'})


if __name__=='__main__':unittest.main()
