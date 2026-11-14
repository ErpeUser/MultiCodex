"""Explicit, deterministic profile eligibility; never rotate on exhausted quota."""
from __future__ import annotations


def eligibility(row, allowed_profiles, *, workspace_id=None):
    if not isinstance(row, dict): return 'AUTH_REQUIRED'
    account = row.get('account', {})
    if account.get('profile_id') not in allowed_profiles: return 'NOT_ALLOWLISTED'
    if not row.get('binding_available'): return 'AUTH_REQUIRED'
    if account.get('membership_state') in {'ACCESS_REMOVED', 'WORKSPACE_ACCESS_REMOVED', 'SEAT_UNAVAILABLE'}:
        return 'ACCESS_REMOVED'
    if workspace_id is not None and (account.get('workspace_id') != workspace_id or
                                    account.get('membership_state') != 'WORKSPACE_MEMBER'):
        return 'CONTEXT_CHANGED'
    if account.get('auth_state') in {'SESSION_EXPIRED', 'DISABLED'}: return 'AUTH_REQUIRED'
    quota = row.get('quota', {})
    if quota.get('status') == 'QUOTA_EXHAUSTED': return 'QUOTA_UNAVAILABLE'
    if quota.get('freshness') != 'LIVE_VERIFIED' or quota.get('capacity_confirmed') is not True:
        return 'QUOTA_UNAVAILABLE'
    return None


def rank_candidates(rows, allowed_profiles, *, workspace_id=None):
    """Preview only. A caller must bind a start request to one explicit account key."""
    accepted = [r for r in rows if eligibility(r, allowed_profiles, workspace_id=workspace_id) is None]
    return sorted(accepted, key=lambda r: (r['quota'].get('max_used_percent', 1000),
        r['account']['profile_id'].casefold(), r['account']['account_key']))
