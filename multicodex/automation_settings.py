"""Versioned non-secret quota preferences, separate from existing theme settings."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import re
import tempfile
from .locks import FileLock
from .quota_store import QuotaError, _safe_path


class SettingsError(ValueError):
    def __init__(self, code='INVALID_SETTINGS'):
        self.code = code if code in ('INVALID_SETTINGS','CORRUPT_SETTINGS','ACTIVATION_UNSUPPORTED') else 'INVALID_SETTINGS'
        super().__init__(self.code)


MAX_SETTINGS_BYTES = 65536
DEFAULTS = {'schema_version': 1, 'enabled': False, 'poll_interval_seconds': 60,
    'warning_threshold_percent': 90, 'allowed_profiles': [], 'maximum_retries': 3,
    'cooldown_seconds': 300, 'max_age_seconds': 120, 'idle_instance_policy': 'keep_open',
    'automatic_activation_enabled': False, 'notification_preferences': 'in_app'}


def validate_settings(data):
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise SettingsError()
    out = {**DEFAULTS, **data}
    if type(out['schema_version']) is not int or out['schema_version'] != 1:
        raise SettingsError()
    for name in ('enabled','automatic_activation_enabled'):
        if type(out[name]) is not bool:
            raise SettingsError()
    for name, minimum, maximum in (('poll_interval_seconds',30,3600),('maximum_retries',1,10),
            ('cooldown_seconds',30,86400),('max_age_seconds',30,86400)):
        if type(out[name]) is not int or not minimum <= out[name] <= maximum:
            raise SettingsError()
    value = out['warning_threshold_percent']
    if type(value) not in (int,float) or not math.isfinite(value) or not 0 < value <= 100:
        raise SettingsError()
    profiles = out['allowed_profiles']
    if (not isinstance(profiles,list) or len(profiles)>1000 or any(
        not isinstance(p,str) or not re.fullmatch(r'[\w .()-]{1,60}',p) or
        p.strip()!=p or p.startswith('.') or p.endswith(('.', ' ')) for p in profiles)):
        raise SettingsError()
    if len({p.casefold() for p in profiles}) != len(profiles):
        raise SettingsError()
    if out['idle_instance_policy'] != 'keep_open' or out['notification_preferences'] not in ('in_app','off'):
        raise SettingsError()
    out['allowed_profiles'] = list(profiles)
    return out


class AutomationSettings:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self.path = self.root / 'quota-automation.json'

    def load(self):
        try:
            _safe_path(self.path)
            if not self.path.exists():
                return validate_settings({})
            if self.path.stat().st_size > MAX_SETTINGS_BYTES:
                raise SettingsError('CORRUPT_SETTINGS')
            return validate_settings(json.loads(self.path.read_text(encoding='utf-8')))
        except (OSError,ValueError) as exc:
            raise SettingsError('CORRUPT_SETTINGS') from exc

    def save(self, changes):
        if not isinstance(changes,dict) or set(changes) - set(DEFAULTS):
            raise SettingsError()
        temp = None
        try:
            _safe_path(self.path)
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            with FileLock(self.root / '.locks' / 'quota-settings.lock'):
                data = validate_settings({**self.load(), **changes})
                payload = json.dumps(data,ensure_ascii=True,indent=2,allow_nan=False).encode('utf-8')
                if len(payload) > MAX_SETTINGS_BYTES:
                    raise SettingsError()
                fd, temp = tempfile.mkstemp(prefix='.quota-settings-',dir=self.root)
                with os.fdopen(fd,'wb') as stream:
                    stream.write(payload)
                    stream.flush();os.fsync(stream.fileno())
                _safe_path(self.path)
                os.replace(temp,self.path)
                return data
        except QuotaError as exc:
            raise SettingsError('CORRUPT_SETTINGS') from exc
        except OSError as exc:
            raise SettingsError('CORRUPT_SETTINGS') from exc
        finally:
            if temp is not None and os.path.exists(temp):
                os.unlink(temp)
