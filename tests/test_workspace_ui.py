import importlib
import importlib.util
import tkinter as tk
import unittest

class WorkspaceWidgetTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.workspace_ui'),'Workspace controls missing')
        self.mod=importlib.import_module('multicodex.workspace_ui')
        try:self.root=tk.Tk()
        except tk.TclError as exc:self.skipTest(str(exc))
        self.addCleanup(self.root.destroy);self.calls=[]
        self.panel=self.mod.WorkspacePanel(self.root,on_read=lambda wid,key:self.calls.append((wid,key)))
        self.panel.pack();self.root.update()
    def test_read_sends_explicit_workspace_and_clears_key_entry(self):
        self.panel.workspace.insert(0,'ws_test');self.panel.key.insert(0,'test-secret')
        self.panel.read_button.invoke()
        self.assertEqual(self.calls,[('ws_test','test-secret')]);self.assertEqual(self.panel.key.get(),'')
    def test_secret_is_masked(self):
        self.assertEqual(self.panel.key.cget('show'),'*')
    def test_incomplete_configuration_is_not_submitted(self):
        self.panel.workspace.insert(0,'ws_test');self.panel.read_button.invoke()
        self.assertEqual(self.calls,[])
    def test_directory_displays_verified_member_not_invented_role(self):
        self.panel.set_model({'workspace_id':'ws_test','complete':True,
            'members':[{'id':'u_1','email':'a@example.invalid'}]})
        self.assertEqual(self.panel.tree.item('u_1','values'),('a@example.invalid','u_1'))
    def test_failed_read_retains_directory_with_stale_warning(self):
        self.panel.set_model({'workspace_id':'ws_test','complete':True,
            'members':[{'id':'u_1','email':'a@example.invalid'}]})
        self.panel.set_error('PERMISSION_DENIED')
        self.assertEqual(len(self.panel.tree.get_children()),1)
        self.assertIn('nicht aktuell',self.panel.message.cget('text'))
