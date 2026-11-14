"""Native regression for Tk finalizers accidentally running in service workers."""
import gc
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from helpers.tk_cleanup import close_test_app


@unittest.skipUnless(sys.platform == 'win32', 'Native Windows GUI regression')
class GuiLifecycleTests(unittest.TestCase):
    def test_cyclic_finalizers_run_on_gui_thread_and_gc_policy_is_restored(self):
        from multicodex.gui import MultiCodexApp
        owner = threading.get_ident()
        finalized = []
        thresholds = gc.get_threshold()
        was_enabled = gc.isenabled()
        class Cycle:
            def __init__(self):
                self.loop = self
            def __del__(self):
                finalized.append(threading.get_ident())
        with tempfile.TemporaryDirectory() as root:
            app = MultiCodexApp(data_dir=Path(root), auto_start=False)
            try:
                gc.set_threshold(10, 10, 10)
                def allocate():
                    Cycle()
                    for _ in range(1000):
                        cycle = []
                        cycle.append(cycle)
                worker = threading.Thread(target=allocate)
                worker.start()
                worker.join(timeout=5)
                self.assertFalse(worker.is_alive())
                deadline = time.monotonic() + 3
                while not finalized and time.monotonic() < deadline:
                    app.update()
                    time.sleep(.02)
                self.assertEqual(finalized, [owner], 'Cyclic GUI resources must never be finalized by a worker')
            finally:
                close_test_app(app)
                gc.set_threshold(*thresholds)
        self.assertEqual(gc.isenabled(), was_enabled)


if __name__ == '__main__':
    unittest.main()
