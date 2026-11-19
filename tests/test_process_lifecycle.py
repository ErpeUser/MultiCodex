import tempfile
import unittest
from pathlib import Path
from multicodex.processes import InstanceController, ProcessSafetyError

class ManagedProcess:
    def __init__(self, pid, home, *, refuses=False):
        self.pid=pid;self.command=['ChatGPT.exe','--user-data-dir',str(home/'electron')]
        self.alive=True;self.refuses=refuses;self.graceful=0;self.forced=0
    def request_close(self):
        self.graceful+=1
        if not self.refuses: self.alive=False
    def terminate(self): self.forced+=1;self.alive=False
    def kill(self): self.terminate()
    def children(self): return []
    def wait(self,timeout):
        if self.alive: raise TimeoutError('test process did not exit')

class Platform:
    def __init__(self,processes): self.processes=processes;self.launched=[]
    def list_processes(self): return [p for p in self.processes if p.alive]
    def start(self,executable,args,env): self.launched.append((executable,args,env));return None

class ProcessLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)/'Work';self.home.mkdir()
    def test_normal_stop_requests_graceful_close(self):
        p=ManagedProcess(1,self.home)
        self.assertEqual(InstanceController(Platform([p])).stop(self.home),1)
        self.assertEqual(p.graceful,1);self.assertEqual(p.forced,0)
    def test_timeout_never_automatically_force_kills(self):
        p=ManagedProcess(1,self.home,refuses=True)
        with self.assertRaises(ProcessSafetyError): InstanceController(Platform([p])).stop(self.home,timeout=.01)
        self.assertEqual(p.forced,0);self.assertTrue(p.alive)
    def test_explicit_force_targets_only_selected_instance(self):
        a=ManagedProcess(1,self.home,refuses=True)
        b=ManagedProcess(2,self.home.parent/'Other')
        InstanceController(Platform([a,b])).stop(self.home,force=True)
        self.assertEqual(a.forced,1);self.assertEqual(b.forced,0)
    def test_selected_session_gets_own_codex_home(self):
        slot=self.home/'.sessions'/'test';slot.mkdir(parents=True)
        executable=self.home.parent/'ChatGPT.exe';executable.touch();platform=Platform([])
        InstanceController(platform).launch(executable,self.home,auth_home=slot)
        self.assertEqual(Path(platform.launched[0][2]['CODEX_HOME']).resolve(), slot.resolve())
    def test_auth_home_cannot_escape_profile(self):
        outside=self.home.parent/'outside';outside.mkdir()
        executable=self.home.parent/'ChatGPT.exe';executable.touch()
        with self.assertRaises(ProcessSafetyError):
            InstanceController(Platform([])).launch(executable,self.home,auth_home=outside)
    def test_child_processes_are_waited_for_without_name_wide_killing(self):
        root=ManagedProcess(1,self.home);child=ManagedProcess(2,self.home,refuses=True)
        root.children=lambda:[child]
        with self.assertRaises(ProcessSafetyError): InstanceController(Platform([root])).stop(self.home,timeout=.01)
        self.assertEqual(child.forced,0)
