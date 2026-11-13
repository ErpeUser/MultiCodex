"""Atomic non-secret preferences; corrupt settings are preserved, not overwritten."""
from __future__ import annotations
import json
from pathlib import Path
from .locks import FileLock
from .profiles import _atomic_json, is_redirect

class SettingsStore:
    def __init__(self,root:Path):
        self.root=Path(root)
        if is_redirect(self.root):
            raise ValueError('Redirected settings root is forbidden')
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.path=self.root/'settings.json'
        self.problem=False

    def load(self):
        self.problem=False
        if not self.path.exists():return {'theme':'dark'}
        try:
            if is_redirect(self.path) or self.path.stat().st_size>65536:raise ValueError('unsafe settings')
            data=json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data,dict) or data.get('theme') not in ('dark','light'):raise ValueError('invalid settings')
            return {'theme':data['theme']}
        except (OSError,ValueError):
            self.problem=True
            return {'theme':'dark'}

    def save_theme(self,theme):
        if theme not in ('dark','light'):raise ValueError('Unsupported appearance')
        with FileLock(self.root/'.locks'/'settings.lock'):
            self.load()
            if self.problem:raise ValueError('Corrupt settings were preserved; repair them before saving')
            _atomic_json(self.path,{'theme':theme})
        return theme
