import tempfile
import unittest
from pathlib import Path
from multicodex.processes import InstanceController, ProcessSafetyError


class FakeProcess:
    def __init__(self, pid, command, alive=True):
        self.pid=pid; self.command=command; self.alive=alive; self.stopped=False
    def terminate(self): self.stopped=True; self.alive=False
    def wait(self, timeout): return None

class FakePlatform:
    def __init__(self, processes): self.processes=processes; self.launched=[]
    def list_processes(self): return [p for p in self.processes if p.alive]
    def start(self, exe, args, env):
        self.launched.append((exe,args,env)); return FakeProcess(55, [exe,*args])

class ProcessTests(unittest.TestCase):
    def test_stop_touches_only_selected_profile(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d,'a');b=Path(d,'b')
            a.mkdir();b.mkdir()
            pa=FakeProcess(1,['ChatGPT.exe','--user-data-dir',str(a/'electron')])
            pb=FakeProcess(2,['ChatGPT.exe','--user-data-dir',str(b/'electron')])
            unrelated=FakeProcess(3,['ChatGPT.exe'])
            platform=FakePlatform([pa,pb,unrelated])
            manager=InstanceController(platform)
            self.assertEqual(manager.stop(a),1)
            self.assertTrue(pa.stopped)
            self.assertFalse(pb.stopped)
            self.assertFalse(unrelated.stopped)

    def test_requires_exact_profile_flag_not_substring(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d,'Work');a.mkdir()
            malicious=FakeProcess(1,['ChatGPT.exe','--user-data-dir',str(a/'electron')+'-other'])
            self.assertEqual(InstanceController(FakePlatform([malicious])).stop(a),0)
            self.assertFalse(malicious.stopped)

    def test_refuses_unsafe_profile_root(self):
        with self.assertRaises(ProcessSafetyError):
            InstanceController(FakePlatform([])).stop(Path('/'))

    def test_launch_creates_isolated_environment(self):
        with tempfile.TemporaryDirectory() as d:
            profile=Path(d,'Work');profile.mkdir()
            Path(d,'ChatGPT.exe').touch()
            platform=FakePlatform([])
            InstanceController(platform).launch(Path(d,'ChatGPT.exe'),profile)
            exe,args,env=platform.launched[0]
            self.assertEqual(env['CODEX_HOME'],str(profile/'.codex'))
            self.assertEqual(env['CODEX_ELECTRON_USER_DATA_PATH'],str(profile/'electron'))
            self.assertEqual(args, ['--user-data-dir',str(profile/'electron')])


if __name__ == '__main__': unittest.main()
