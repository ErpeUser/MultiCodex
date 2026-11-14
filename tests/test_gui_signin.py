"""Native regressions for the visible sign-in and activity lifecycle."""
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from multicodex.codex_client import CodexError
from helpers.tk_cleanup import close_test_app


@unittest.skipUnless(sys.platform == 'win32', 'Native Windows GUI regression')
class GuiSignInTests(unittest.TestCase):
    def setUp(self):
        from multicodex.gui import MultiCodexApp
        self.tmp = tempfile.TemporaryDirectory()
        self.app = MultiCodexApp(data_dir=Path(self.tmp.name), auto_start=False)
        self.release = threading.Event()
        self.app.update()

    def tearDown(self):
        self.release.set()
        if self.app.login_cancel is not None:
            self.app.login_cancel.set()
        self.pump(lambda: not self.app.jobs.pending)
        close_test_app(self.app)
        self.tmp.cleanup()

    def pump(self, condition, timeout=4):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            self.app.update()
            time.sleep(.01)
        self.app.update()
        return condition()

    def test_idle_and_background_refresh_do_not_display_signin_activity(self):
        self.assertFalse(self.app.progress.winfo_ismapped())
        self.assertFalse(self.app.cancel_button.winfo_ismapped())
        self.app._submit('snapshot', lambda: self.release.wait(2), lambda _: None)
        self.app.update()
        self.assertFalse(self.app.progress.winfo_ismapped())
        self.assertFalse(self.app.cancel_button.winfo_ismapped())

    def test_signin_entry_is_visible_on_diagnostics_and_opens_accounts(self):
        self.app._set_page('Diagnostics')
        self.app.update()
        self.assertTrue(hasattr(self.app, 'sign_in_button'), 'Sign-in needs a visible entry on every page')
        self.assertTrue(self.app.sign_in_button.winfo_ismapped())
        self.app.sign_in_button.invoke()
        self.app.update()
        self.assertEqual(self.app.page, 'Accounts')

    def test_browser_failure_keeps_login_cancellable_and_retryable(self):
        reached_browser = threading.Event()
        class Operations:
            def login(_self, name, *, confirmed, reauthenticate, on_browser, cancel):
                on_browser('https://auth.openai.com/authorize?fixture=1')
                reached_browser.set()
                cancel.wait(3)
                raise CodexError('CANCELLED')
        self.app.services.operations = Operations()
        self.app._set_page('Accounts')
        with patch.object(self.app, '_confirm_restart', return_value=True), patch('multicodex.gui.webbrowser.open', return_value=False):
            self.app._login('Test')
            self.assertTrue(self.pump(reached_browser.is_set), 'Browser launch failure must keep a recoverable sign-in')
            self.assertTrue(self.pump(lambda: getattr(self.app, 'login_url', None) is not None))
            self.assertTrue(self.app.cancel_button.winfo_ismapped())
            self.assertEqual(self.app.cancel_button.cget('state'), 'normal')
            import customtkinter as ctk
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            self.assertTrue(any(isinstance(b, ctk.CTkButton) and 'Browser' in b.cget('text') and b.cget('state') == 'normal'
                for b in descendants(self.app.page_frame)))
            self.app._cancel_login()
            self.assertTrue(self.pump(lambda: self.app.login_cancel is None and not self.app.jobs.pending))
        self.assertFalse(self.app.progress.winfo_ismapped())
        self.assertFalse(self.app.cancel_button.winfo_ismapped())
        self.assertIn('abgebrochen', self.app.status_bar.cget('text'))

    def test_stalled_browser_does_not_block_login_cancellation(self):
        class Operations:
            def login(_self, name, *, confirmed, reauthenticate, on_browser, cancel):
                on_browser('https://auth.openai.com/authorize?fixture=1')
                cancel.wait(3)
                raise CodexError('CANCELLED')
        self.app.services.operations = Operations()
        with patch.object(self.app, '_confirm_restart', return_value=True), patch('multicodex.gui.webbrowser.open', side_effect=lambda *_a, **_k: self.release.wait(3)):
            self.app._login('Test')
            self.assertTrue(self.pump(lambda: getattr(self.app, 'login_url', None) is not None))
            self.app._cancel_login()
            self.assertTrue(self.pump(lambda: self.app.login_cancel is None and not self.app.jobs.pending, timeout=1))
