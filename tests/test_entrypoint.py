import io
import sys
import unittest
from unittest.mock import patch
import run

class EntrypointTests(unittest.TestCase):
    def test_self_check_fails_when_only_transport_is_ready(self):
        with patch.object(sys, 'argv', ['run.py','--self-check']), patch.object(sys, 'stdout', io.StringIO()), patch('multicodex.account_bridge.AccountBridge.request', return_value={'serviceReady':True,'protocol':1,'upstreamReady':False,'nodeCompatible':True,'ready':False}):
            self.assertEqual(run.main(),1)

    def test_windowed_self_check_does_not_require_stdout(self):
        with patch.object(sys, 'argv', ['run.py','--self-check']), patch.object(sys, 'stdout', None), patch('multicodex.account_bridge.AccountBridge.request', side_effect=RuntimeError('private')):
            self.assertEqual(run.main(),1)
