import unittest
from unittest.mock import patch
from multicodex.health import check_runtime

class HealthTests(unittest.TestCase):
    def probe(self, value):
        with patch('multicodex.health.find_spec', return_value=object()), patch('multicodex.health.AccountBridge.request', return_value=value):
            return check_runtime()

    def test_transport_alive_is_not_a_ready_installation(self):
        report = self.probe({'serviceReady': True, 'protocol': 1, 'upstreamReady': False, 'nodeCompatible': True, 'ready': False})
        self.assertFalse(report['ready'])
        self.assertFalse(report['upstream'])

    def test_all_dependencies_and_protocol_required(self):
        report = self.probe({'serviceReady':True, 'protocol':1, 'nodeCompatible':True, 'upstreamReady':True, 'ready':True})
        self.assertTrue(report['ready'])

    def test_untrusted_health_fields_not_copied_to_report(self):
        report = self.probe({'serviceReady':True, 'protocol':1, 'token':'secret-not-for-report'})
        self.assertNotIn('secret-not-for-report', str(report))
        self.assertFalse(report['ready'])

    def test_provider_failure_contains_no_raw_exception(self):
        with patch('multicodex.health.AccountBridge.request', side_effect=RuntimeError('private-secret')):
            report = check_runtime()
        self.assertFalse(report['ready'])
        self.assertNotIn('private-secret', str(report))

    def test_missing_gui_dependency_prevents_success(self):
        with patch('multicodex.health.find_spec', side_effect=lambda n: None if n=='customtkinter' else object()), patch('multicodex.health.AccountBridge.request', return_value={'serviceReady':True, 'protocol':1, 'nodeCompatible':True, 'upstreamReady':True, 'ready':True}):
            self.assertFalse(check_runtime()['ready'])
