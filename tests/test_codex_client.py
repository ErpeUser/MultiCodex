import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from multicodex.codex_client import CodexClient, CodexError, CodexAccountService, validate_login_url, AccountIdentity

FIXTURE = Path(__file__).parent/'helpers'/'fake_app_server.py'

class CodexClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)

    def client(self, mode=''):
        return CodexClient([sys.executable,str(FIXTURE)], self.home,
                           environment={'MULTICODEX_FIXTURE_MODE':mode}, timeout=1)

    def test_initialization_and_real_subprocess_framing(self):
        with self.client() as client:
            result=client.request('account/read', {'refreshToken':False})
            self.assertEqual(AccountIdentity.from_response(result).email,'test@example.invalid')
        self.assertIsNotNone(client.process.poll())

    def test_notifications_before_response_are_not_lost(self):
        with self.client() as client:
            reply=client.request('account/login/start', {'type':'chatgpt'})
            event=client.wait_login(reply['loginId'], threading.Event(), timeout=1)
            self.assertTrue(event['success'])

    def test_timeout_is_bounded_and_secret_free(self):
        with self.client('hang') as client:
            with self.assertRaises(CodexError) as caught:
                client.request('account/read', {}, timeout=.1)
            self.assertEqual(caught.exception.code,'TIMEOUT')

    def test_cancel_interrupts_a_pending_account_request(self):
        with self.client('hang') as client:
            client.cancel = threading.Event()
            timer = threading.Timer(.05, client.cancel.set)
            timer.start()
            self.addCleanup(timer.join)
            with self.assertRaises(CodexError) as caught:
                client.request('account/read', {}, timeout=.5)
            self.assertEqual(caught.exception.code, 'CANCELLED')

    def test_describe_can_be_cancelled_during_account_read(self):
        cancel = threading.Event()
        service = CodexAccountService(cli_resolver=lambda: FIXTURE)
        timer = threading.Timer(.05, cancel.set)
        timer.start()
        self.addCleanup(timer.join)
        with patch.object(service, 'client', return_value=self.client('hang')):
            try:
                service.describe(self.home, cancel=cancel)
            except CodexError as exc:
                self.assertEqual(exc.code, 'CANCELLED')
            except TypeError:
                self.fail('Account preparation must accept and observe cancellation')
            else:
                self.fail('Cancelled account read must not succeed')

    def test_raw_server_error_is_not_exposed(self):
        with self.client('secret-error') as client:
            with self.assertRaises(CodexError) as caught:
                client.request('account/read', {})
            self.assertNotIn('fixture-secret',str(caught.exception))

    def test_oversized_server_line_is_rejected(self):
        with self.client('oversized') as client:
            with self.assertRaises(CodexError):
                client.request('account/read', {})

    def test_login_url_does_not_open_arbitrary_hosts_or_credentials(self):
        for value in ['http://auth.openai.com/', 'https://auth.openai.com.evil.invalid/',
                      'https://user:pass@auth.openai.com/', 'file:///C:/a',
                      'https://auth.openai.com:444/', 'https://evil.invalid/']:
            with self.subTest(value=value), self.assertRaises(CodexError):
                validate_login_url(value)
        self.assertEqual(validate_login_url('https://auth.openai.com/authorize?state=x'),
                         'https://auth.openai.com/authorize?state=x')

    def test_authentication_config_is_keyring_not_auto_fallback(self):
        with self.client() as client:
            self.assertIn('cli_auth_credentials_store="keyring"',client.process.args)
            self.assertEqual(client.environment['CODEX_HOME'],str(self.home))
            self.assertNotIn('OPENAI_API_KEY',client.environment)

    def test_identity_must_be_chatgpt_and_complete(self):
        for result in [None,[],{}, {'account':None}, {'account':{'type':'apiKey'}},
                       {'account':{'type':'chatgpt','email':'bad\nemail'}}]:
            with self.subTest(result=result), self.assertRaises(CodexError):
                AccountIdentity.from_response(result)

    def test_account_id_fallback_and_symmetric_matching(self):
        identity = AccountIdentity.from_response({'account': {
            'type': 'chatgpt', 'email': 'test@example.invalid',
            'accountId': None, 'id': 'fallback-id'}})
        self.assertEqual(identity.account_id, 'fallback-id')
        missing = AccountIdentity('test@example.invalid', account_id=None)
        known = AccountIdentity('test@example.invalid', account_id='known-id')
        self.assertFalse(missing.same_account(known))
        self.assertFalse(known.same_account(missing))
        self.assertTrue(missing.same_account(AccountIdentity('test@example.invalid')))

    def test_cancelled_wait_never_reports_success(self):
        with self.client() as client:
            event=threading.Event();event.set()
            with self.assertRaises(CodexError) as caught:
                client.wait_login('other',event,timeout=.1)
            self.assertEqual(caught.exception.code,'CANCELLED')
