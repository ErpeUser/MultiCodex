import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from multicodex.locks import FileLock, BusyError

class LockTests(unittest.TestCase):
    def test_reentrant_lock_and_other_thread_busy(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'operation.lock';result=[]
            def compete():
                try:
                    with FileLock(path): result.append('acquired')
                except BusyError: result.append('busy')
            with FileLock(path), FileLock(path):
                t=threading.Thread(target=compete);t.start();t.join(2)
            self.assertEqual(result,['busy'])
            with FileLock(path): pass

    def test_other_process_cannot_take_lock_then_can_after_release(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'operation.lock'
            code='from multicodex.locks import FileLock,BusyError\nimport sys\ntry:\n with FileLock(sys.argv[1]): pass\nexcept BusyError: sys.exit(7)'
            with FileLock(path):
                result=subprocess.run([sys.executable,'-c',code,str(path)],capture_output=True,timeout=5)
                self.assertEqual(result.returncode,7,result.stderr)
            result=subprocess.run([sys.executable,'-c',code,str(path)],capture_output=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
