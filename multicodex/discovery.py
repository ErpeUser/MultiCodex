"""Read-only discovery of legacy profiles and supported legacy desktop packages."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


class UnsupportedDesktop(RuntimeError):
    pass


@dataclass(frozen=True)
class LegacyProfile:
    name: str
    path: Path


def discover_legacy_profiles(roots: list[Path]) -> list[LegacyProfile]:
    found: list[LegacyProfile] = []
    seen: set[str] = set()
    for root in roots:
        root = Path(root)
        if not root.is_dir() or root.is_symlink():
            continue
        try:
            entries = sorted(root.iterdir(), key=lambda x: x.name.casefold())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir() or entry.is_symlink():
                continue
            name = entry.name
            key = str(entry.resolve()).casefold()
            if key not in seen:
                found.append(LegacyProfile(name, entry.resolve()))
                seen.add(key)
    return found


def default_legacy_roots() -> list[Path]:
    """Only known locations; never search other browser data or whole disk."""
    cwd = Path.cwd()
    local = Path(os.environ.get('LOCALAPPDATA') or Path.home())
    return [cwd / 'CodexProfiles', Path(__file__).resolve().parents[2] / 'CodexProfiles',
            local / 'CodexProfiles']


def find_legacy_codex_executable() -> Path:
    if os.name != 'nt':
        raise UnsupportedDesktop('Windows required for desktop-instance launches')
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                                  '(Get-AppxPackage -Name OpenAI.Codex*).InstallLocation'],
                                capture_output=True, text=True, timeout=15,
                                creationflags=0x08000000)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UnsupportedDesktop('Could not query installed Codex packages') from exc
    for row in result.stdout.splitlines():
        package = Path(row.strip())
        if package.name.startswith('OpenAI.Codex_'):
            exe = package / 'app' / 'ChatGPT.exe'
            if exe.is_file():
                return exe
    raise UnsupportedDesktop('Supported Codex desktop package not found. Combined ChatGPT builds are unverified.')


def find_codex_cli() -> Path:
    """Prefer the official desktop's bundled CLI; never run a multi-auth wrapper."""
    import shutil
    try:
        candidate = find_legacy_codex_executable().parent / 'resources' / 'codex.exe'
        if candidate.is_file():
            return candidate
    except UnsupportedDesktop:
        pass
    candidate = shutil.which('codex.exe' if os.name == 'nt' else 'codex')
    if candidate:
        path = Path(candidate).resolve()
        if path.is_file() and path.suffix.casefold() not in ('.cmd', '.bat', '.ps1'):
            return path
    raise UnsupportedDesktop('Official Codex CLI not found in the supported installation or PATH')
