"""Require native acceptance tied to the exact source commit AND installer bytes.

This gate validates evidence bindings, not the truth of a human's assertions.
The GitHub 'release' environment must additionally require a human reviewer.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

MAX_ACCEPTANCE_AGE = timedelta(days=14)
MAX_FUTURE_SKEW = timedelta(minutes=5)

REQUIRED_CHECKS = (
    'windows_11_x64', 'three_isolated_instances', 'switch_target_only',
    'oauth_relogin', 'cancelled_relogin_preserves_old', 'wrong_account_rejected',
    'existing_profile_preserved', 'existing_pool_secure_import',
    'crash_recovery', 'encrypted_credentials', 'gui_actions',
    'dark_light_dpi_keyboard', 'installer_upgrade_uninstall',
    'desktop_version_compatibility', 'dependency_locks', 'licenses_and_app_icon',
)

class ReleaseBlocked(ValueError):
    pass


def check_acceptance(evidence: dict, commit: str, setup: Path) -> dict:
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ReleaseBlocked('Invalid source commit')
    if not isinstance(evidence, dict) or type(evidence.get('schema')) is not int or evidence['schema'] != 1:
        raise ReleaseBlocked('Native acceptance report is missing or unsupported')
    if evidence.get('source_commit') != commit:
        raise ReleaseBlocked('Acceptance does not cover this source commit')
    with setup.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if evidence.get('setup_sha256') != digest:
        raise ReleaseBlocked('Acceptance does not cover these installer bytes')
    reviewer = evidence.get('reviewer')
    if not isinstance(reviewer, str) or not re.fullmatch(r'[A-Za-z0-9_.@ -]{1,100}', reviewer) or not reviewer.strip():
        raise ReleaseBlocked('A named native-test reviewer is required')
    try:
        date = datetime.fromisoformat(evidence['checked_at'])
        if date.tzinfo is None:
            raise ValueError('Time zone required')
        checked_at = date.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        if checked_at > now + MAX_FUTURE_SKEW:
            raise ValueError('Acceptance timestamp is in the future')
        if now - checked_at > MAX_ACCEPTANCE_AGE:
            raise ValueError('Acceptance timestamp is too old')
    except (KeyError, TypeError, ValueError) as exc:
        raise ReleaseBlocked('A valid native-test timestamp is required') from exc
    checks = evidence.get('checks')
    missing = [key for key in REQUIRED_CHECKS if not isinstance(checks, dict) or checks.get(key) is not True]
    if missing:
        raise ReleaseBlocked('Native acceptance incomplete: ' + ', '.join(missing))
    return {'source_commit': commit, 'setup_sha256': digest, 'checks_passed': len(REQUIRED_CHECKS)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--commit', required=True)
    parser.add_argument('--setup', type=Path, required=True)
    args = parser.parse_args()
    raw = os.environ.get('MULTICODEX_RELEASE_ACCEPTANCE', '')
    try:
        if not raw or len(raw) > 65536:
            raise ReleaseBlocked('Set native acceptance for this exact build before publication')
        result = check_acceptance(json.loads(raw), args.commit, args.setup)
    except (ReleaseBlocked, ValueError, OSError) as exc:
        # Own controlled failure messages only; never echo the supplied JSON.
        print(str(exc) if isinstance(exc, ReleaseBlocked) else 'Acceptance report or installer could not be verified')
        return 1
    print(json.dumps(result))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
