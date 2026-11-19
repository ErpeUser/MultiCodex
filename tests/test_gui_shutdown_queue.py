"""Saturated browser notifications and closing must remain recoverable."""
import queue
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from multicodex.gui import MultiCodexApp
from helpers.tk_cleanup import close_test_app


class BrowserHarness:
    _open_login_browser = MultiCodexApp._open_login_browser

    def __init__(self):
        self.login_events = queue.Queue(maxsize=16)
        self._browser_lock = threading.Lock()


class LoginQueueTests(unittest.TestCase):
    def test_seventeen_reopens_without_poller_retain_last_browser_failure(self):
        host, cancel = BrowserHarness(), threading.Event()
        with patch('multicodex.gui.webbrowser.open', return_value=False):
            for index in range(17):
                try:
                    host._open_login_browser(cancel, 'https://auth.openai.com/authorize?fixture=' + str(index))
                except queue.Full:
                    self.fail('Browser notifications must never leak queue.Full')
        events = []
        while not host.login_events.empty():
            events.append(host.login_events.get_nowait())
        self.assertLessEqual(len(events), 16)
        self.assertEqual(events[-1], (cancel, 'https://auth.openai.com/authorize?fixture=16', False))

    def test_busy_browser_with_full_queue_has_recoverable_final_state(self):
        host, cancel = BrowserHarness(), threading.Event()
        for _ in range(16):
            host.login_events.put_nowait((cancel, 'old', None))
        host._browser_lock.acquire()
        try:
            try:
                self.assertFalse(host._open_login_browser(cancel, 'https://auth.openai.com/authorize'))
            except queue.Full:
                self.fail('Busy browser path must tolerate a saturated poller')
        finally:
            host._browser_lock.release()
        events = []
        while not host.login_events.empty():
            events.append(host.login_events.get_nowait())
        self.assertEqual(events[-1], (cancel, 'https://auth.openai.com/authorize', False))

    def test_browser_exception_is_reported_after_saturation(self):
        host, cancel = BrowserHarness(), threading.Event()
        for _ in range(16):
            host.login_events.put_nowait((cancel, 'old', None))
        with patch('multicodex.gui.webbrowser.open', side_effect=OSError('fixture shell failure')):
            self.assertFalse(host._open_login_browser(cancel, 'https://auth.openai.com/authorize'))
        events = []
        while not host.login_events.empty():
            events.append(host.login_events.get_nowait())
        self.assertEqual(events[-1], (cancel, 'https://auth.openai.com/authorize', False))

    def test_cancelled_login_does_not_publish_to_a_saturated_queue(self):
        host, cancel = BrowserHarness(), threading.Event()
        for _ in range(16):
            host.login_events.put_nowait((cancel, 'old', None))
        cancel.set()
        with patch('multicodex.gui.webbrowser.open', side_effect=AssertionError('cancelled browser opened')):
            host._open_login_browser(cancel, 'https://auth.openai.com/authorize')
        self.assertEqual(host.login_events.qsize(), 16)


@unittest.skipUnless(sys.platform == 'win32', 'Native Windows GUI regression')
class GuiShutdownTests(unittest.TestCase):
    def test_login_close_reaps_owned_rpc_child_that_ignores_cancel_and_eof(self):
        import psutil
        with tempfile.TemporaryDirectory() as root:
            fixture = Path(root) / 'blocked_rpc_fixture.py'
            marker = Path(root) / 'child.json'
            cancelled = Path(root) / 'cancel-observed'
            fixture.write_text('''
import json, os, sys, threading
from pathlib import Path
import psutil
root = Path(__file__).parent
(root / 'child.json').write_text(json.dumps({'pid':os.getpid(), 'created':psutil.Process().create_time()}))
for line in sys.stdin:
    request = json.loads(line)
    method = request.get('method')
    if method == 'initialize':
        result = {}
    elif method == 'account/login/start':
        result = {'loginId':'fixture-login'}
    elif method == 'account/login/cancel':
        (root / 'cancel-observed').write_text('observed')
        continue
    else:
        continue
    print(json.dumps({'id':request['id'], 'result':result}), flush=True)
threading.Event().wait()  # Deliberately ignore stdin EOF as well.
''', encoding='utf-8')
            script = '''
import sys, threading
from pathlib import Path
from unittest.mock import patch
from multicodex.codex_client import CodexClient
from multicodex.gui import MultiCodexApp
root = Path(sys.argv[1])
app = MultiCodexApp(data_dir=root / 'data', auto_start=False)
cancel = app.login_cancel = threading.Event()
client = CodexClient([sys.executable, str(root / 'blocked_rpc_fixture.py')], root, timeout=30)
started = threading.Event()
def login():
    with client:
        reply = client.request('account/login/start', {'type':'chatgpt'})
        started.set()
        client.wait_login(reply['loginId'], cancel)
app._submit('login', login, lambda _: None)
assert started.wait(3)
with patch('multicodex.gui.messagebox.askyesno', return_value=True):
    app.after(0, app._close)
    app.mainloop()
assert cancel.is_set()
assert client.process.poll() is not None, 'owned app-server survived GUI close'
assert (root / 'cancel-observed').read_text() == 'observed'
print('child-reaped', flush=True)
'''
            try:
                run = subprocess.run([sys.executable, '-c', script, root],
                                     cwd=Path(__file__).resolve().parents[1],
                                     capture_output=True, text=True, timeout=16)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout.strip(), 'child-reaped')
                self.assertTrue(cancelled.is_file())
                child = json.loads(marker.read_text())
                self.assertFalse(psutil.pid_exists(child['pid']))
            finally:
                # A failing regression must clean up only its exact fixture,
                # checking creation time and command before any process action.
                if marker.is_file():
                    child = json.loads(marker.read_text())
                    try:
                        process = psutil.Process(child['pid'])
                        if (process.create_time() == child['created'] and
                                str(fixture) in process.cmdline()):
                            process.terminate()
                            process.wait(3)
                    except psutil.NoSuchProcess:
                        pass

    def test_cooperative_login_and_quota_work_finish_without_ui_callbacks_on_close(self):
        for operation in ('login', 'quota'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as root:
                app = MultiCodexApp(data_dir=Path(root), auto_start=False)
                app.login_cancel = threading.Event()
                cancel = app.login_cancel if operation == 'login' else app.quota.cancel
                started, finished = threading.Event(), threading.Event()
                callbacks = []
                def work(started=started, cancel=cancel, finished=finished):
                    started.set()
                    cancel.wait(3)
                    finished.set()
                    return 'late result'
                try:
                    app._submit(operation, work, callbacks.append)
                    self.assertTrue(started.wait(2))
                    with patch('multicodex.gui.messagebox.askyesno', return_value=True):
                        app._close()
                    self.assertTrue(finished.wait(2))
                    deadline = time.monotonic() + 3
                    while not app._destroyed and time.monotonic() < deadline:
                        app.update()
                        time.sleep(.01)
                    self.assertTrue(app._destroyed)
                    self.assertEqual(callbacks, [])
                    app._poll_results()
                finally:
                    close_test_app(app)

    def test_saturated_browser_queue_displays_latest_state_and_close_ignores_old_events(self):
        with tempfile.TemporaryDirectory() as root:
            app = MultiCodexApp(data_dir=Path(root), auto_start=False)
            try:
                cancel = app.login_cancel = threading.Event()
                with patch('multicodex.gui.webbrowser.open', return_value=False):
                    for index in range(17):
                        app._open_login_browser(cancel, 'https://auth.openai.com/authorize?fixture=' + str(index))
                app._poll_results()
                self.assertEqual(app.login_url, 'https://auth.openai.com/authorize?fixture=16')
                self.assertIn('konnte nicht', app.status_bar.cget('text'))
                for _ in range(16):
                    app.login_events.put_nowait((cancel, 'https://auth.openai.com/authorize?stale=1', True))
                app._close()
                self.assertTrue(cancel.is_set())
                app._poll_results()
                self.assertTrue(app._destroyed)
            finally:
                close_test_app(app)

    def test_real_profile_snapshot_updates_rows_without_rebuilding_or_losing_selection(self):
        from multicodex.profiles import Profile
        with tempfile.TemporaryDirectory() as root:
            app = MultiCodexApp(data_dir=Path(root), auto_start=False)
            try:
                profile = Profile('Fixture', Path(root) / 'fixture')
                first = {'profiles': [profile], 'processes': {'Fixture': {'running': False}},
                         'sessions': {}, 'recovery': {}, 'issues': []}
                app._set_page('Instances')
                app._snapshot_loaded(first)
                app.update()
                table = app.data_tables['profiles']
                table.table.selection_set('Fixture')
                app._snapshot_loaded(dict(first, processes={'Fixture': {'running': True, 'pids': [123]}}))
                app.update()
                self.assertIs(app.data_tables['profiles'], table)
                self.assertEqual(table.table.selection(), ('Fixture',))
                self.assertEqual(table.rows['Fixture']['cells']['state'], 'Läuft')
                self.assertEqual(table.rows['Fixture']['pids'], [123])
            finally:
                close_test_app(app)

    def test_blocked_gui_worker_exits_and_cancels_services(self):
        script = '''
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
from multicodex.gui import MultiCodexApp
with tempfile.TemporaryDirectory() as root:
    app = MultiCodexApp(data_dir=Path(root), auto_start=False)
    started = threading.Event()
    def blocked():
        started.set()
        threading.Event().wait()
    app.login_cancel = threading.Event()
    app._submit('blocked', blocked, lambda _: (_ for _ in ()).throw(AssertionError('late callback')))
    assert started.wait(2)
    with patch('multicodex.gui.messagebox.askyesno', return_value=True):
        app.after(0, app._close)
        app.mainloop()
    assert app.login_cancel.is_set()
    assert app.quota.cancel.is_set()
    assert app.admin.cancel.is_set()
    app._poll_results()  # stale callback after destroy must touch no Tk widget
    print('closed', flush=True)
'''
        try:
            run = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
                                 capture_output=True, text=True, timeout=16)
        except subprocess.TimeoutExpired:
            self.fail('GUI close must have a bounded deadline even for a blocked worker')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), 'closed')
