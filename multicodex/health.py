"""Credential-free runtime health. Transport liveness alone is never readiness."""
from __future__ import annotations
import sys
from importlib.util import find_spec
from .account_bridge import AccountBridge


def check_runtime() -> dict:
    dependencies = {}
    for name in ('customtkinter', 'tkinter', 'psutil'):
        try:
            dependencies[name] = find_spec(name) is not None
        except (ImportError, ValueError):
            dependencies[name] = False
    try:
        result = AccountBridge().request('health', timeout=8)
    except Exception:
        result = {}
    if not isinstance(result, dict):
        result = {}
    report = {'python': sys.version_info >= (3, 12), 'dependencies': dependencies,
              'bridge': result.get('serviceReady') is True,
              'protocol': type(result.get('protocol')) is int and result['protocol'] == 1,
              'node': result.get('nodeCompatible') is True,
              'upstream': result.get('upstreamReady') is True}
    report['ready'] = all(report[k] for k in ('python', 'bridge', 'protocol', 'node', 'upstream')) and all(dependencies.values())
    report['scope'] = 'bundled-runtime-only; not desktop, OAuth or installer acceptance'
    return report
