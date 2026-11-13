import unittest
import tempfile
from pathlib import Path
from multicodex.account_bridge import AccountBridge, AccountBridgeError


class BridgeTests(unittest.TestCase):
    def test_health_works_without_upstream_installed(self):
        self.assertTrue(AccountBridge().request('health')['serviceReady'])

    def test_missing_upstream_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            # A temporary service copy guarantees a missing node_modules even on CI,
            # where the upstream package is installed in the project bridge folder.
            source = Path(__file__).resolve().parents[1] / 'bridge' / 'service.mjs'
            isolated = Path(d) / 'service.mjs'
            isolated.write_text(source.read_text(encoding='utf8'), encoding='utf8')
            with self.assertRaises(AccountBridgeError) as caught:
                AccountBridge(service=isolated).list_accounts()
            self.assertEqual(caught.exception.code,'UPSTREAM_UNAVAILABLE')

    def test_bad_account_index_is_rejected(self):
        with self.assertRaises(AccountBridgeError) as caught:
            AccountBridge().switch(0)
        self.assertEqual(caught.exception.code,'BAD_PARAMS')


if __name__=='__main__': unittest.main()
