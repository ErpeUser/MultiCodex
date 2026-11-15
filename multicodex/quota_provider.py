"""Read-only official app-server quota adapter; never exports credentials.

Protocol reference: https://learn.chatgpt.com/docs/app-server
A quota response proves only the selected metered bucket, not workspace roles.
"""
from __future__ import annotations
import threading
import time
from .codex_client import AccountIdentity, CodexAccountService, CodexError
from .quota_store import (CREDIT_STATUSES, LIMIT_TYPES, RESET_TYPES, QuotaError,
                           _reset_credits, _stamp, _text, normalized_usage)


def _sanitize_reset_credits(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {'availableCount', 'credits'} or 'availableCount' not in value:
        raise CodexError('PROTOCOL')
    count = value['availableCount']
    if type(count) is not int or count < 0 or count > 1000000:
        raise CodexError('PROTOCOL')
    credits = value.get('credits')
    if credits is not None and (not isinstance(credits, list) or len(credits) > 10000):
        raise CodexError('PROTOCOL')
    result = {'available_count': count, 'credits': None if credits is None else []}
    if credits is not None:
        for credit in credits:
            if not isinstance(credit, dict):
                raise CodexError('PROTOCOL')
            allowed = {'id', 'resetType', 'status', 'grantedAt', 'expiresAt', 'title', 'description'}
            required = {'id', 'resetType', 'status', 'grantedAt'}
            if set(credit) - allowed or not required.issubset(credit):
                raise CodexError('PROTOCOL')
            item = {
                'id': _text(credit['id'], 160),
                'reset_type': credit['resetType'],
                'status': credit['status'],
                'granted_at': credit['grantedAt'],
                'expires_at': credit.get('expiresAt'),
                'title': credit.get('title'),
                'description': credit.get('description'),
            }
            if item['reset_type'] not in RESET_TYPES or item['status'] not in CREDIT_STATUSES:
                raise CodexError('PROTOCOL')
            try:
                _stamp(item['granted_at'])
                if item['expires_at'] is not None:
                    _stamp(item['expires_at'])
                _text(item['title'], 1000, optional=True)
                _text(item['description'], 1000, optional=True)
                _reset_credits({'available_count': count, 'credits': [item]})
            except QuotaError as exc:
                raise CodexError('PROTOCOL') from exc
            result['credits'].append(item)
    return result


def sanitize_limits(data: dict) -> dict:
    """Select the documented Codex bucket and allowlist its numeric fields."""
    if not isinstance(data, dict):
        raise CodexError('PROTOCOL')
    buckets = data.get('rateLimitsByLimitId')
    additional = False
    if buckets is not None:
        if not isinstance(buckets, dict):
            raise CodexError('PROTOCOL')
        if buckets:
            selected = buckets.get('codex')
            additional = bool(set(buckets) - {'codex'})
        else:
            selected = data.get('rateLimits')
    else:
        selected = data.get('rateLimits')
    if not isinstance(selected, dict) or selected.get('limitId') not in (None, 'codex'):
        raise CodexError('PROTOCOL')
    result = {'source': 'official-app-server', 'windows': [], 'reported': {},
              'additional_limits_reported': additional}
    for label in ('primary', 'secondary'):
        if label not in selected:
            result['reported'][label] = None
        elif selected[label] is None:
            result['reported'][label] = False
        else:
            window = selected[label]
            if not isinstance(window, dict):
                raise CodexError('PROTOCOL')
            result['reported'][label] = True
            result['windows'].append({'label': label, 'used_percent': window.get('usedPercent'),
                'minutes': window.get('windowDurationMins'), 'reset_at': window.get('resetsAt')})
    for camel, snake in (('ordinaryUsageAllowed','ordinary_usage_allowed'),
                         ('spendControlReached','spend_control_reached')):
        values = [obj.get(camel) for obj in (data, selected)]
        if any(value is not None and type(value) is not bool for value in values):
            raise CodexError('PROTOCOL')
        # A denial at either scope wins. Do not hide an outer spend/access limit.
        denial = False if camel == 'ordinaryUsageAllowed' else True
        result[snake] = denial if any(v is denial for v in values) else next((v for v in values if v is not None), None)
    reached = next((obj.get('rateLimitReachedType') for obj in (selected,data)
                    if obj.get('rateLimitReachedType') is not None),None)
    result['rate_limit_reached_type'] = (None if reached is None else reached
        if isinstance(reached,str) and reached in LIMIT_TYPES else 'UNKNOWN_PROVIDER_LIMIT')
    result['reset_credits'] = _sanitize_reset_credits(data.get('rateLimitResetCredits'))
    try:
        result['account_id'] = _text(data.get('accountId'),optional=True)
        result['plan_type'] = _text(selected.get('planType'),64,optional=True)
        normalized_usage(result)
    except QuotaError as exc:
        raise CodexError('PROTOCOL') from exc
    return result


class QuotaAccountService(CodexAccountService):
    """Reuse official process/credential handling; do not change existing login."""
    def __init__(self, cli_resolver=None, *, clock=time.time):
        super().__init__(cli_resolver)
        self.clock = clock

    def observe(self, home, *, expected: AccountIdentity, cancel: threading.Event | None = None,
                secure=True) -> dict:
        if not isinstance(expected, AccountIdentity):
            raise CodexError('ACCOUNT_MISMATCH')
        if cancel is not None and cancel.is_set():
            raise CodexError('CANCELLED')
        client = self.client(home, secure=secure)
        client.cancel = cancel
        with client:
            before = AccountIdentity.from_response(client.request('account/read', {'refreshToken': False}))
            if not expected.same_account(before):
                raise CodexError('ACCOUNT_MISMATCH')
            usage = sanitize_limits(client.request('account/rateLimits/read', {}))
            after = AccountIdentity.from_response(client.request('account/read', {'refreshToken': False}))
            if (before.email.casefold() != after.email.casefold() or
                before.account_id != after.account_id or before.plan != after.plan):
                raise CodexError('ACCOUNT_MISMATCH')
        if cancel is not None and cancel.is_set():
            raise CodexError('CANCELLED')
        response_id = usage.get('account_id')
        if ((response_id is None) != (after.account_id is None) or
                (response_id is not None and response_id != after.account_id)):
            raise CodexError('ACCOUNT_MISMATCH')
        response_plan = usage.get('plan_type')
        if response_plan is not None and after.plan is not None and response_plan != after.plan:
            raise CodexError('ACCOUNT_MISMATCH')
        usage['account_id'] = response_id or after.account_id
        return {'identity': after.public(), 'usage': usage, 'observed_at': int(self.clock())}
