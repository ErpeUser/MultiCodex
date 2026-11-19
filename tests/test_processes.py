import os
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

    @unittest.skipUnless(os.name == 'nt', 'Windows 8.3 aliases only')
    def test_short_windows_path_alias_selects_only_the_same_profile(self):
        long_home = Path('C:/Program Files/Common Files')
        short_home = Path('C:/PROGRA~1/Common Files')
        if not long_home.is_dir() or not short_home.is_dir():
            self.skipTest('Host does not expose a known 8.3 path alias')
        selected = FakeProcess(10, ['ChatGPT.exe', '--user-data-dir', str(short_home / 'electron')])
        other = FakeProcess(11, ['ChatGPT.exe', '--user-data-dir', str(short_home) + '-other/electron'])
        matches = InstanceController(FakePlatform([selected, other])).matching(long_home)
        self.assertEqual([process.pid for process in matches], [10])

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
            self.assertEqual(Path(env['CODEX_HOME']).resolve(), (profile/'.codex').resolve())
            self.assertEqual(Path(env['CODEX_ELECTRON_USER_DATA_PATH']).resolve(), (profile/'electron').resolve())
            self.assertEqual(args[0], '--user-data-dir')
            self.assertEqual(Path(args[1]).resolve(), (profile/'electron').resolve())


if __name__ == '__main__': unittest.main()
