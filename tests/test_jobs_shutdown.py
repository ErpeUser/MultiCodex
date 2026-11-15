"""Process exit is part of the worker lifecycle contract, not just close()."""
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

from multicodex.jobs import JobRunner


class JobShutdownTests(unittest.TestCase):
    def test_blocked_worker_cannot_keep_interpreter_alive(self):
        script = '''
import threading
from multicodex.jobs import JobRunner
started = threading.Event()
def blocked():
    started.set()
    threading.Event().wait()
jobs = JobRunner(workers=1)
jobs.submit('blocked', blocked)
assert started.wait(2)
jobs.close()
print('closed', flush=True)
'''
        try:
            run = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
                                 capture_output=True, text=True, timeout=4)
        except subprocess.TimeoutExpired:
            self.fail('JobRunner.close() left a blocked worker holding interpreter exit')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), 'closed')

    def test_close_discards_late_results_and_never_starts_queued_work(self):
        jobs = JobRunner(workers=1)
        started, release, finished, queued = (threading.Event() for _ in range(4))
        def blocked():
            started.set()
            release.wait(2)
            finished.set()
            return 'late'
        try:
            jobs.submit('active', blocked)
            self.assertTrue(started.wait(2))
            jobs.submit('queued', queued.set)
            jobs.close()
            release.set()
            self.assertTrue(finished.wait(2))
            deadline = time.monotonic() + 2
            while jobs.pending and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertEqual(jobs.drain(), [])
            self.assertEqual(jobs.pending, 0)
            self.assertFalse(queued.is_set())
        finally:
            release.set()
            jobs.close()
