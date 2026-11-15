"""Toolkit-independent application boundary and redacted user-facing failures."""
from __future__ import annotations
from .account_bridge import AccountBridgeError
from .codex_client import CodexError
from .controller import SessionController, OperationError
from .discovery import UnsupportedDesktop
from .locks import BusyError
from .processes import ProcessSafetyError
from .profiles import ProfileError


def user_error(error: BaseException) -> str:
    """Never render arbitrary exception messages, subprocess output or OAuth URLs."""
    if isinstance(error, CodexError):
        return {
            'CANCELLED': 'Anmeldung abgebrochen. Die bisherige Zuordnung bleibt erhalten.',
            'TIMEOUT': 'Die offizielle Anwendung antwortet nicht. Installation und Verbindung pr\u00fcfen.',
            'UNAVAILABLE': 'Die offizielle Codex-CLI ist nicht verf\u00fcgbar.',
            'AUTH_FAILED': 'Anmeldung oder Kontopr\u00fcfung fehlgeschlagen. Erneut anmelden.',
            'NOT_AUTHENTICATED': 'Keine gespeicherte Anmeldung gefunden. Konto hinzuf\u00fcgen.',
            'ACCOUNT_MISMATCH': 'Die neue Anmeldung geh\u00f6rt nicht zum ausgew\u00e4hlten Konto. Nichts umgestellt.',
            'UNSAFE_URL': 'Unerwartete Anmeldeadresse abgewiesen. Offizielle Installation pr\u00fcfen.',
            'PLAINTEXT_AUTH': 'Sichere Speicherung nicht best\u00e4tigt. Anmeldung wurde nicht aktiviert.',
            'PROTOCOL': 'Die installierte Codex-Version liefert ein nicht unterst\u00fctztes Antwortformat.',
        }.get(error.code, 'Die Kontoaktion konnte nicht abgeschlossen werden.')
    if isinstance(error, AccountBridgeError):
        return 'Der bestehende Multi-Auth-Pool ist nicht verf\u00fcgbar. Details unter Diagnose.'
    if isinstance(error, BusyError):
        return 'F\u00fcr dieses Profil l\u00e4uft bereits eine Aktion. Abschluss abwarten.'
    if isinstance(error, UnsupportedDesktop):
        return 'Unterst\u00fctzte Codex-Desktop-Installation nicht gefunden. Kombinierte ChatGPT-Builds sind nicht verifiziert.'
    if isinstance(error, ProfileError):
        return 'Profil, Name oder Metadaten sind ung\u00fcltig. Originaldaten wurden nicht gel\u00f6scht; Diagnose pr\u00fcfen.'
    if isinstance(error, ProcessSafetyError):
        return 'Der ausgew\u00e4hlte Prozess konnte nicht sicher gestartet oder beendet werden. Fenster manuell schlie\u00dfen und erneut pr\u00fcfen.'
    if isinstance(error, OperationError):
        return 'Aktion nicht abgeschlossen. Aktuelle Zuordnung pr\u00fcfen; bei markiertem Profil Wiederherstellung ausf\u00fchren.'
    return 'Aktion fehlgeschlagen. Installation und lokale Dateiberechtigungen pr\u00fcfen. Fehlerdetails wurden aus Sicherheitsgr\u00fcnden nicht angezeigt.'


class ApplicationServices:
    def __init__(self, store, instances, auth):
        self.store = store
        self.instances = instances
        self.auth = auth
        self.operations = SessionController(store, instances, auth)
        self.sessions = self.operations.sessions

    def snapshot(self) -> dict:
        """One worker-side filesystem/process snapshot, no network or token reads."""
        profiles = self.store.list()
        issues = list(self.store.issues)
        try:
            processes = self.instances.snapshot(profiles)
        except Exception:
            processes = {p.name: {'running': None, 'pids': []} for p in profiles}
            issues.append({'name': 'Prozesse', 'error': 'Prozessstatus nicht verf\u00fcgbar'})
        sessions, recovery = {}, {}
        for profile in profiles:
            if profile.linked:
                sessions[profile.name], recovery[profile.name] = [], False
                continue
            try:
                sessions[profile.name] = self.sessions.list(profile.name)
                recovery[profile.name] = self.sessions.journal(profile.name) is not None
            except (ValueError, OSError):
                sessions[profile.name], recovery[profile.name] = [], True
                issues.append({'name': profile.name, 'error': 'Sitzungsmetadaten pr\u00fcfen; weitere Kontoaktionen sind gesperrt'})
        return {'profiles': profiles, 'processes': processes, 'sessions': sessions,
                'recovery': recovery, 'issues': issues}


def usage_lines(data: dict) -> list[str]:
    """Translate the one sanitized service contract, never arbitrary provider JSON."""
    from datetime import datetime
    import math
    if not isinstance(data, dict) or data.get('source') != 'official-app-server' or not isinstance(data.get('windows'), list):
        raise ValueError('Unsupported usage response')
    if not data['windows']:
        return ['Die Anwendung hat keine unterst\u00fctzten Limits gemeldet.']
    lines = []
    for row in data['windows']:
        value = row.get('used_percent') if isinstance(row, dict) else None
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1000:
            raise ValueError('Invalid usage value')
        label = {'primary': 'Prim\u00e4res Limit', 'secondary': 'Sekund\u00e4res Limit'}.get(row.get('label'), 'Limit')
        text = f'{label}: {value:g}% verwendet'
        minutes = row.get('minutes')
        if type(minutes) is int and minutes > 0:
            text += f' | Fenster: {minutes} Minuten'
        lines.append(text)
        reset = row.get('reset_at')
        if type(reset) is int and reset >= 0:
            try:
                lines.append('Reset: ' + datetime.fromtimestamp(reset).astimezone().strftime('%d.%m.%Y %H:%M %Z'))
            except (ValueError, OSError, OverflowError):
                lines.append('Reset-Zeit nicht darstellbar.')
    return lines
