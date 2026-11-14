"""Exercise the real sanitizer and adapter; only the official process is faked."""
import copy
import importlib
import importlib.util
import threading
import unittest
from contextlib import contextmanager
from multicodex.codex_client import AccountIdentity, CodexError


def limits():
    return {'rateLimits': {'limitId': 'codex', 'planType': 'business',
        'primary': {'usedPercent': 42, 'windowDurationMins': 300, 'resetsAt': 18000},
        'secondary': {'usedPercent': 64, 'windowDurationMins': 10080, 'resetsAt': 604800},
        'rateLimitReachedType': None}}


class FakeClient:
    def __init__(self, data, identities=None):
        self.data = data
        self.identities = list(identities or [AccountIdentity('one@example.invalid','business','one')]*2)
        self.cancel = None
        self.calls = []
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def request(self, method, params):
        self.calls.append((method, params))
        if self.cancel is not None and self.cancel.is_set():
            raise CodexError('CANCELLED')
        if method == 'account/read':
            item = self.identities.pop(0)
            return {'account': {'type': 'chatgpt', 'email': item.email,
                    'planType': item.plan, 'accountId': item.account_id}}
        if method == 'account/rateLimits/read':
            return copy.deepcopy(self.data)
        raise AssertionError('Unexpected production action')


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('multicodex.quota_provider'),
                             'Quota observation adapter is not implemented')
        self.mod = importlib.import_module('multicodex.quota_provider')

    def test_real_duration_and_reset_fields_are_preserved(self):
        out = self.mod.sanitize_limits(limits())
        self.assertEqual(out['windows'][0], {'label':'primary','used_percent':42,'minutes':300,'reset_at':18000})
        self.assertEqual(out['reported'], {'primary':True,'secondary':True})

    def test_reset_credits_are_sanitized_as_snapshot_metadata(self):
        data = limits()
        data['rateLimitResetCredits'] = {
            'availableCount': 2,
            'credits': [{
                'id': 'credit-1', 'resetType': 'codexRateLimits', 'status': 'available',
                'grantedAt': 1000, 'expiresAt': 2000,
                'title': 'Full reset', 'description': 'Ready to redeem',
            }],
        }
        out = self.mod.sanitize_limits(data)
        self.assertEqual(out['reset_credits'], {
            'available_count': 2,
            'credits': [{
                'id': 'credit-1', 'reset_type': 'codexRateLimits', 'status': 'available',
                'granted_at': 1000, 'expires_at': 2000,
                'title': 'Full reset', 'description': 'Ready to redeem',
            }],
        })

    def test_null_window_differs_from_omitted_window(self):
        data = limits(); data['rateLimits']['primary'] = None; del data['rateLimits']['secondary']
        out = self.mod.sanitize_limits(data)
        self.assertEqual(out['reported'], {'primary':False,'secondary':None})
        self.assertEqual(out['windows'], [])

    def test_unknown_used_percent_keeps_window_and_reset(self):
        data = limits(); data['rateLimits']['primary']['usedPercent'] = None
        out = self.mod.sanitize_limits(data)
        self.assertIsNone(out['windows'][0]['used_percent'])
        self.assertEqual(out['windows'][0]['reset_at'], 18000)

    def test_non_finite_bool_and_bad_numbers_raise_protocol(self):
        for val in (float('nan'),float('inf'),True,-1,'20',1001):
            data=limits();data['rateLimits']['primary']['usedPercent']=val
            with self.subTest(val=val), self.assertRaises(CodexError) as caught:
                self.mod.sanitize_limits(data)
            self.assertEqual(caught.exception.code,'PROTOCOL')

    def test_arbitrary_provider_fields_are_not_exported(self):
        data=limits();data['access_token']='SENTINEL_SECRET';data['rateLimits']['credits']={'secret':'SENTINEL_SECRET'}
        self.assertNotIn('SENTINEL_SECRET',str(self.mod.sanitize_limits(data)))

    def test_codex_bucket_is_selected_instead_of_unrelated_fallback(self):
        data=limits();target=copy.deepcopy(data['rateLimits']);target['primary']['usedPercent']=93
        data['rateLimitsByLimitId']={'codex':target,'other':{'primary':{'usedPercent':0}}}
        out=self.mod.sanitize_limits(data)
        self.assertEqual(out['windows'][0]['used_percent'],93)
        self.assertTrue(out['additional_limits_reported'])

    def test_ambiguous_bucket_fails_closed(self):
        data=limits();data['rateLimitsByLimitId']={'other':data['rateLimits']}
        with self.assertRaises(CodexError):self.mod.sanitize_limits(data)

    def test_mismatched_bucket_identifier_is_not_codex(self):
        data=limits();data['rateLimits']['limitId']='other'
        with self.assertRaises(CodexError):self.mod.sanitize_limits(data)

    def test_provider_limit_denial_survives_sanitization(self):
        data=limits();data['rateLimits']['rateLimitReachedType']='workspaceCreditLimitReached'
        out=self.mod.sanitize_limits(data)
        self.assertEqual(out['rate_limit_reached_type'],'workspaceCreditLimitReached')

    def test_unrecognized_limit_denial_is_safe_but_not_ignored(self):
        data=limits();data['rateLimits']['rateLimitReachedType']='SENTINEL_SECRET'
        out=self.mod.sanitize_limits(data)
        self.assertEqual(out['rate_limit_reached_type'],'UNKNOWN_PROVIDER_LIMIT')
        self.assertNotIn('SENTINEL_SECRET',str(out))

    def test_observe_verifies_identity_before_and_after_read(self):
        client=FakeClient(limits());service=self.mod.QuotaAccountService(cli_resolver=lambda:"unused",clock=lambda:1234)
        service.client=lambda home,secure=True:client
        out=service.observe('/unused',expected=AccountIdentity('one@example.invalid','business','one'))
        self.assertEqual(out['observed_at'],1234)
        self.assertEqual(out['identity']['account_id'],'one')
        self.assertEqual([m for m,p in client.calls],['account/read','account/rateLimits/read','account/read'])

    def test_quota_response_account_is_verified_not_overwritten_by_cached_identity(self):
        data=limits();data['accountId']='different-account'
        client=FakeClient(data);service=self.mod.QuotaAccountService(cli_resolver=lambda:'unused')
        service.client=lambda home,secure=True:client
        with self.assertRaises(CodexError) as caught:
            service.observe('/unused',expected=AccountIdentity('one@example.invalid','business','one'))
        self.assertEqual(caught.exception.code,'ACCOUNT_MISMATCH')

    def test_quota_response_supplies_account_id_when_local_read_does_not(self):
        data=limits();data['accountId']='response-account'
        client=FakeClient(data,[AccountIdentity('one@example.invalid','business',None)]*2)
        service=self.mod.QuotaAccountService(cli_resolver=lambda:'unused',clock=lambda:1234)
        service.client=lambda home,secure=True:client
        result=service.observe('/unused',expected=AccountIdentity('one@example.invalid'))
        self.assertEqual(result['usage']['account_id'],'response-account')

    def test_quota_plan_mismatch_is_not_accepted_as_current_business_usage(self):
        data=limits();data['rateLimits']['planType']='free'
        client=FakeClient(data);service=self.mod.QuotaAccountService(cli_resolver=lambda:'unused')
        service.client=lambda home,secure=True:client
        with self.assertRaises(CodexError):
            service.observe('/unused',expected=AccountIdentity('one@example.invalid','business','one'))

    def test_malformed_account_id_is_not_echoed(self):
        data=limits();data['accountId']='SENTINEL_SECRET\ninvalid'
        with self.assertRaises(CodexError) as caught:self.mod.sanitize_limits(data)
        self.assertEqual(caught.exception.code,'PROTOCOL')
        self.assertNotIn('SENTINEL_SECRET',str(caught.exception))

    def test_outer_limit_denial_is_not_hidden_by_inner_null(self):
        data=limits();data['rateLimitReachedType']='workspaceUsageLimitReached'
        self.assertEqual(self.mod.sanitize_limits(data)['rate_limit_reached_type'],'workspaceUsageLimitReached')

    def test_wrong_identity_stops_before_quota_request(self):
        client=FakeClient(limits());service=self.mod.QuotaAccountService(cli_resolver=lambda:"unused")
        service.client=lambda home,secure=True:client
        with self.assertRaises(CodexError) as caught:
            service.observe('/unused',expected=AccountIdentity('wrong@example.invalid'))
        self.assertEqual(caught.exception.code,'ACCOUNT_MISMATCH')
        self.assertEqual(len(client.calls),1)

    def test_identity_changed_mid_call_rejects_observation(self):
        client=FakeClient(limits(),[AccountIdentity('one@example.invalid','business','one'),AccountIdentity('one@example.invalid','business','two')])
        service=self.mod.QuotaAccountService(cli_resolver=lambda:"unused");service.client=lambda home,secure=True:client
        with self.assertRaises(CodexError):
            service.observe('/unused',expected=AccountIdentity('one@example.invalid','business','one'))

    def test_cancelled_observation_never_starts_provider(self):
        service=self.mod.QuotaAccountService(cli_resolver=lambda:"unused");service.client=lambda *a,**k:self.fail('Provider started after cancellation')
        cancel=threading.Event();cancel.set()
        with self.assertRaises(CodexError) as caught:service.observe('/unused',expected=AccountIdentity('one@example.invalid'),cancel=cancel)
        self.assertEqual(caught.exception.code,'CANCELLED')

    def test_plan_changed_mid_observation_requires_new_read(self):
        client=FakeClient(limits(),[AccountIdentity('one@example.invalid','business','one'),AccountIdentity('one@example.invalid','free','one')])
        service=self.mod.QuotaAccountService(cli_resolver=lambda:"unused");service.client=lambda home,secure=True:client
        with self.assertRaises(CodexError):service.observe('/unused',expected=AccountIdentity('one@example.invalid','business','one'))

if __name__=='__main__':unittest.main()
