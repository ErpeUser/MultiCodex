from pathlib import Path
from types import SimpleNamespace
import importlib
import importlib.util
import tempfile
import unittest

class Process:
    def __init__(self,home):
        self.pid=1234;self.created=10.;self.alive=True
        self.command=['ChatGPT.exe','--user-data-dir',str(home/'electron')]
        self.environment={'CODEX_HOME':str(home/'.codex'),'CODEX_ELECTRON_USER_DATA_PATH':str(home/'electron')}
    def create_time(self):return self.created
    def is_running(self):return self.alive
    def cmdline(self):return self.command
    def environ(self):return self.environment

class DesktopBindingTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.desktop_binding'),'Desktop binding verifier is missing')
        self.module=importlib.import_module('multicodex.desktop_binding')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        home=Path(self.temp.name);(home/'.codex').mkdir();(home/'electron').mkdir()
        self.profile=SimpleNamespace(home=home,codex_home=home/'.codex')
        self.process=Process(home)
        self.record=SimpleNamespace(pid=1234,created=10.,command=list(self.process.command),process=self.process)
        self.records=[self.record];self.calls=[]
        runtime=SimpleNamespace(controller=SimpleNamespace(matching=lambda home:self.records))
        self.windows=SimpleNamespace(focus=lambda pid,valid:self.calls.append(pid) is None and valid())
        self.verifier=self.module.DesktopBinding(runtime,window_api=self.windows)

    def test_exact_root_and_auth_home_can_be_verified(self):self.assertTrue(self.verifier.verify(self.profile))
    def test_multiple_roots_are_ambiguous(self):
        self.records.append(self.record);self.assertFalse(self.verifier.verify(self.profile))
    def test_reused_pid_is_rejected(self):
        self.process.created=20.;self.assertFalse(self.verifier.verify(self.profile))
    def test_wrong_auth_home_is_rejected(self):
        self.process.environment['CODEX_HOME']=str(self.profile.home/'other');self.assertFalse(self.verifier.verify(self.profile))
    def test_missing_auth_home_is_not_inferred_from_a_saved_account(self):
        del self.process.environment['CODEX_HOME'];self.assertFalse(self.verifier.verify(self.profile))
    def test_changed_command_is_rejected(self):
        self.process.command=['ChatGPT.exe'];self.assertFalse(self.verifier.verify(self.profile))
    def test_unreadable_environment_is_unknown(self):
        def deny():raise PermissionError('SECRET')
        self.process.environ=deny;self.assertFalse(self.verifier.verify(self.profile))
    def test_focus_only_receives_verified_pid(self):
        self.assertTrue(self.verifier.focus(self.profile));self.assertEqual(self.calls,[1234])
    def test_focus_does_not_touch_unverified_process(self):
        self.process.alive=False;self.assertFalse(self.verifier.focus(self.profile));self.assertEqual(self.calls,[])
    def test_pid_change_during_focus_is_rejected(self):
        def focus(pid,valid):self.process.created=99.;return valid()
        self.windows.focus=focus;self.assertFalse(self.verifier.focus(self.profile))
