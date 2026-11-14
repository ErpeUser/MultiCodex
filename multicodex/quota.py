"""Pure quota interpretation: historical reset times never manufacture capacity."""
from __future__ import annotations

from datetime import datetime
import math
import time

from .quota_store import QuotaError, MAX_TIMESTAMP


REMOVED = {'ACCESS_REMOVED', 'WORKSPACE_ACCESS_REMOVED', 'SEAT_UNAVAILABLE'}
WINDOW_NAMES = {300: 'five_hour', 10080: 'weekly'}


def _valid_number(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1000


def evaluate_snapshot(snapshot, account=None, *, now=None, max_age_seconds=120,
                      warning_threshold_percent=90):
    """Return a renderable decision; capacity is not authorization to use an account.

    Explicitly absent windows are displayed as NOT_REPORTED, not as unlimited.
    Unrecognized/missing durations, stale observations, errors and expired reset
    timestamps prevent capacity confirmation. No membership is inferred here.
    """
    now = int(time.time()) if now is None else now
    if (type(now) is not int or not 0 <= now <= MAX_TIMESTAMP or
        type(max_age_seconds) is not int or max_age_seconds <= 0 or
        type(warning_threshold_percent) not in (int, float) or
        not math.isfinite(warning_threshold_percent) or not 0 < warning_threshold_percent <= 100):
        raise QuotaError()
    account = account if isinstance(account, dict) else {}
    result = {'status': 'UNKNOWN', 'freshness': 'UNKNOWN', 'capacity_confirmed': False,
              'windows': [], 'observed_at': None, 'reset_predicted': False,
              'next_reset_at': None, 'max_used_percent': None}
    if not isinstance(snapshot, dict) or snapshot.get('source') != 'official-app-server':
        return result
    observed = snapshot.get('observed_at')
    if type(observed) is not int or not 0 <= observed <= now:
        return result
    result['observed_at'] = observed
    age = now - observed
    access_removed = account.get('membership_state') in REMOVED
    failed = bool(account.get('last_error_code'))
    freshness = 'STALE' if age > max_age_seconds else ('CACHED' if failed or access_removed else 'LIVE_VERIFIED')
    result['freshness'] = freshness
    unknown = False
    kinds = set()
    present = []
    resets = []
    for slot in ('primary', 'secondary'):
        exists = snapshot.get(slot + '_present')
        used = snapshot.get(slot + '_used_percent')
        duration = snapshot.get(slot + '_duration_minutes')
        reset = snapshot.get(slot + '_reset_at')
        valid_reset = type(reset) is int and 0 <= reset <= MAX_TIMESTAMP
        valid_used = _valid_number(used)
        kind = WINDOW_NAMES.get(duration, 'other') if type(duration) is int else 'unknown'
        row = {'slot': slot, 'kind': kind, 'duration_minutes': duration if type(duration) is int else None,
               'used_percent': used if valid_used else None,
               'remaining_percent': max(0, 100-used) if valid_used else None,
               'reset_at': reset if valid_reset else None,
               'reset_in_seconds': max(0, reset-now) if valid_reset else None,
               'state': 'UNKNOWN'}
        if exists is False:
            row.update(state='NOT_REPORTED', used_percent=None, remaining_percent=None,
                       duration_minutes=None, kind='not_reported', reset_at=None, reset_in_seconds=None)
        elif exists is not True:
            unknown = True
        else:
            present.append(row)
            if kind in kinds or kind not in ('five_hour','weekly'):
                unknown = True
            kinds.add(kind)
            if not valid_used or not valid_reset:
                unknown = True
            elif reset <= now:
                row['state'] = 'RESET_TIME_REACHED'
                result['reset_predicted'] = True
            else:
                resets.append(reset)
                row['state'] = ('EXHAUSTED' if used >= 100 else
                                'WARNING' if used >= warning_threshold_percent else 'AVAILABLE')
        result['windows'].append(row)
    result['next_reset_at'] = min(resets) if resets else None
    values = [w['used_percent'] for w in present if w['used_percent'] is not None]
    result['max_used_percent'] = max(values) if values else None
    changed = (account.get('context_revision', 0) != snapshot.get('context_revision', 0) or any(account.get(k) != snapshot.get(k) for k in ('plan_type','seat_type') if k in account) or
               type(account.get('access_changed_at')) is int and account['access_changed_at'] >= observed)
    denied = (snapshot.get('ordinary_usage_allowed') is False or
              snapshot.get('spend_control_reached') is True or
              bool(snapshot.get('rate_limit_reached_type')))
    if access_removed:
        result['status'] = 'ACCESS_REMOVED'
    elif account.get('auth_state') in ('SESSION_EXPIRED', 'DISABLED'):
        result['status'] = 'AUTHENTICATION_REQUIRED'
    elif changed:
        result['status'] = 'VERIFICATION_REQUIRED'
    elif denied:
        result['status'] = 'QUOTA_EXHAUSTED'
    elif result['reset_predicted']:
        result['status'] = 'VERIFICATION_REQUIRED'
    elif freshness != 'LIVE_VERIFIED':
        result['status'] = 'VERIFICATION_REQUIRED'
    elif snapshot.get('additional_limits_reported') is True or unknown or not present:
        result['status'] = 'UNKNOWN'
    elif any(w['state'] == 'EXHAUSTED' for w in present):
        result['status'] = 'QUOTA_EXHAUSTED'
    else:
        # The backend permission is authoritative. Older clients may omit it;
        # show their measurements, but do not infer renewed usable capacity.
        permission = snapshot.get('ordinary_usage_allowed') is True
        warning = any(w['state'] == 'WARNING' for w in present)
        result['status'] = 'QUOTA_WARNING' if warning else ('VERIFIED_AVAILABLE' if permission else 'VERIFICATION_REQUIRED')
        result['capacity_confirmed'] = permission
    return result


def format_reset(timestamp):
    """Local timezone/DST rendering without interpreting an absent time as now."""
    if type(timestamp) is not int or not 0 <= timestamp <= MAX_TIMESTAMP:
        return 'Unbekannt'
    try:
        return datetime.fromtimestamp(timestamp).astimezone().strftime('%d.%m.%Y %H:%M %Z')
    except (ValueError, OSError, OverflowError):
        return 'Nicht darstellbar'


def format_countdown(seconds):
    if type(seconds) is not int or seconds < 0:
        return 'Unbekannt'
    if seconds == 0:
        return 'Resetzeit erreicht; Pruefung erforderlich'
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    return (f'{days}d ' if days else '') + f'{hours}h {minutes}m'
