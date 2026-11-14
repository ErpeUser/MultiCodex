"""Pure, localized quota view models. No I/O, credentials or widget references."""
from __future__ import annotations

STATUS_TEXT = {
    'UNKNOWN':'Unbekannt', 'VERIFIED_AVAILABLE':'Quota gepr\u00fcft',
    'QUOTA_WARNING':'Warnschwelle', 'QUOTA_EXHAUSTED':'Limit erreicht',
    'ACCESS_REMOVED':'Zugang entfernt', 'VERIFICATION_REQUIRED':'Pr\u00fcfung erforderlich',
    'AUTHENTICATION_REQUIRED':'Anmeldung erforderlich'}
FRESHNESS_TEXT = {'LIVE_VERIFIED':'Live gepr\u00fcft','CACHED':'Gespeichert',
                  'STALE':'Veraltet','UNKNOWN':'Unbekannt'}
ACCESS_TEXT = {'WORKSPACE_ACCESS_UNKNOWN':'Workspace-Zugang nicht verifiziert',
    'WORKSPACE_MEMBER':'Mitgliedschaft verifiziert', 'ACCESS_REMOVED':'Zugang entfernt',
    'WORKSPACE_ACCESS_REMOVED':'Zugang entfernt', 'SEAT_UNAVAILABLE':'Seat nicht verf\u00fcgbar',
    'INVITATION_PENDING':'Einladung ausstehend','INVITATION_ACCEPTED':'Einladung angenommen'}
ERROR_TEXT = {'TIMEOUT':'Zeitlimit der Abfrage erreicht.', 'UNAVAILABLE':'Codex-App-Server nicht erreichbar.',
    'NOT_AUTHENTICATED':'Erneut \u00fcber den offiziellen Login anmelden.',
    'ACCOUNT_MISMATCH':'Kontoidentit\u00e4t stimmt nicht mit dem Profil \u00fcberein.',
    'AUTH_FAILED':'Die offizielle Kontoabfrage wurde abgelehnt.',
    'PROTOCOL':'Antwortformat der installierten Codex-Version nicht unterst\u00fctzt.',
    'BUSY':'F\u00fcr dieses Profil l\u00e4uft bereits eine Aktion.',
    'STORAGE':'Quota-Speicher nicht lesbar. Originaldateien bleiben erhalten.',
    'UNKNOWN':'Abfrage fehlgeschlagen. Keine historischen Werte ersetzt.'}
REMOVED = frozenset({'ACCESS_REMOVED','WORKSPACE_ACCESS_REMOVED','SEAT_UNAVAILABLE'})
CHECK = frozenset({'UNKNOWN','VERIFICATION_REQUIRED','AUTHENTICATION_REQUIRED','ACCESS_REMOVED'})


def window_text(window, *, compact=False):
    if not isinstance(window,dict):return 'Unbekannt'
    if window.get('state') == 'NOT_REPORTED':return 'Nicht gemeldet'
    used=window.get('used_percent')
    if type(used) not in (int,float):return 'Unbekannt'
    value=f'{used:g} %'
    return value + (' / Pr\u00fcfung n\u00f6tig' if not compact and window.get('state')=='RESET_TIME_REACHED' else '')


def display_windows(windows):
    """Map known durations without relabeling an unknown window as absent."""
    result = {w.get('kind'): w for w in windows if w.get('kind') in ('five_hour', 'weekly')}
    absent = next((w for w in windows if w.get('state') == 'NOT_REPORTED'), None)
    if absent is not None and all(w.get('kind') in ('five_hour', 'weekly', 'not_reported') for w in windows):
        for kind in ('five_hour', 'weekly'):
            result.setdefault(kind, absent)
    return result


def filter_rows(rows, *, query='', status='all', sort_by='account'):
    query=query.strip().casefold()
    result=[]
    for row in rows:
        account,quota=row['account'],row['quota']
        text=' '.join(str(account.get(k) or '') for k in ('profile_id','email','workspace_id','plan_type')).casefold()
        if query and query not in text:continue
        state=quota['status']
        if status=='removed' and account.get('membership_state') not in REMOVED:continue
        if status=='warning' and state not in ('QUOTA_WARNING','QUOTA_EXHAUSTED'):continue
        if status=='check' and state not in CHECK:continue
        result.append(row)
    if sort_by=='reset':
        result.sort(key=lambda row:(row['quota'].get('next_reset_at') is None,
            row['quota'].get('next_reset_at') or 0,row['account']['account_key']))
    elif sort_by=='usage':
        result.sort(key=lambda row:(-(row['quota'].get('max_used_percent') or 0),row['account']['account_key']))
    else:
        result.sort(key=lambda row:(row['account'].get('profile_id','').casefold(),row['account'].get('email','').casefold(),row['account']['account_key']))
    return result


def summarize_rows(rows):
    return {'accounts':len(rows),
        'live':sum(r['quota']['freshness']=='LIVE_VERIFIED' for r in rows),
        'needs_check':sum(r['quota']['status'] in CHECK for r in rows),
        'removed':sum(r['account'].get('membership_state') in REMOVED for r in rows),
        'critical':sum(r['quota']['status'] in ('QUOTA_WARNING','QUOTA_EXHAUSTED') for r in rows)}
