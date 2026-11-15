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
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.supply_chain import REVIEWED_EXPRESSIONS

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


def check_supply_chain(evidence: dict, commit: str, sbom: Path, license_report: Path) -> dict:
    """Bind independently reviewed supply-chain files to native acceptance.

    Native assertions alone cannot stand in for an actual post-build inventory.
    The reviewer must cover the exact two hashes alongside the installer hash.
    """
    def read(path, limit):
        if path.stat().st_size > limit:
            raise ReleaseBlocked('Supply-chain report exceeds its size limit')
        raw = path.read_bytes()
        if len(raw) > limit:
            raise ReleaseBlocked('Supply-chain report exceeds its size limit')
        def unique(items):
            value = {}
            for key, item in items:
                if key in value:
                    raise ReleaseBlocked('Duplicate supply-chain report key')
                value[key] = item
            return value
        value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique)
        if not isinstance(value, dict):
            raise ReleaseBlocked('Unsupported supply-chain report')
        return value, hashlib.sha256(raw).hexdigest()

    bom, bom_hash = read(sbom, 64 * 1024 * 1024)
    report, report_hash = read(license_report, 4 * 1024 * 1024)
    if evidence.get('sbom_sha256') != bom_hash or evidence.get('license_report_sha256') != report_hash:
        raise ReleaseBlocked('Acceptance does not cover these SBOM and license-report bytes')
    if (bom.get('bomFormat') != 'CycloneDX' or bom.get('specVersion') != '1.6'
            or bom.get('metadata', {}).get('component', {}).get('version') != commit
            or not isinstance(bom.get('components'), list) or not bom['components']):
        raise ReleaseBlocked('Unsupported SBOM or source binding')
    if (type(report.get('schema')) is not int or report['schema'] != 1
            or report.get('source_commit') != commit or report.get('sbom_sha256') != bom_hash
            or report.get('components') != len(bom['components'])):
        raise ReleaseBlocked('Bundle license review is incomplete or incorrectly bound')
    blockers = report.get('blockers')
    if (not isinstance(blockers, list) or any(not isinstance(item, str) for item in blockers)
            or len(blockers) != len(set(blockers)) or type(report.get('ready')) is not bool
            or report['ready'] != (not blockers)):
        raise ReleaseBlocked('Invalid automatic license disposition')
    reviews = evidence.get('license_review', [])
    if not isinstance(reviews, list) or len(reviews) != len(blockers):
        raise ReleaseBlocked('Every license blocker requires an explicit human disposition')
    allowed = ('LICENSE_REVIEW_REQUIRED:', 'LICENSE_TEXT_MISSING:',
               'NATIVE_LICENSE_REVIEW_REQUIRED:', 'RUNTIME_LICENSE_REVIEW_REQUIRED:',
               'RUNTIME_LICENSE_MISSING:')
    notices = {}
    for component in bom['components']:
        if isinstance(component, dict) and component.get('type') == 'file':
            for hash_value in component.get('hashes', []):
                if hash_value.get('alg') == 'SHA-256':
                    notices[component.get('name')] = hash_value.get('content')
    covered = set()
    for review in reviews:
        if not isinstance(review, dict):
            raise ReleaseBlocked('Unsupported license review')
        blocker = review.get('blocker')
        notice = review.get('notice')
        if (not isinstance(blocker, str) or blocker not in blockers or blocker in covered
                or not blocker.startswith(allowed)
                or review.get('reviewer') != evidence.get('reviewer')
                or review.get('license_expression') not in REVIEWED_EXPRESSIONS
                or not isinstance(notice, str) or notice not in notices
                or not re.search(r'(?i)(?:license|licence|copying|notice)', notice)
                or not re.fullmatch(r'[a-f0-9]{64}', str(review.get('notice_sha256', '')))
                or review['notice_sha256'] != notices[notice]):
            raise ReleaseBlocked('License review does not establish a shipped, reviewed attribution')
        covered.add(blocker)
    return {'sbom_sha256': bom_hash, 'license_report_sha256': report_hash,
            'manually_reviewed_license_blockers': len(covered)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--commit', required=True)
    parser.add_argument('--setup', type=Path, required=True)
    parser.add_argument('--sbom', type=Path, required=True)
    parser.add_argument('--license-report', type=Path, required=True)
    args = parser.parse_args()
    raw = os.environ.get('MULTICODEX_RELEASE_ACCEPTANCE', '')
    try:
        if not raw or len(raw) > 65536:
            raise ReleaseBlocked('Set native acceptance for this exact build before publication')
        evidence = json.loads(raw)
        result = check_acceptance(evidence, args.commit, args.setup)
        result.update(check_supply_chain(evidence, args.commit, args.sbom, args.license_report))
    except (ReleaseBlocked, ValueError, OSError, TypeError, AttributeError, RecursionError) as exc:
        # Own controlled failure messages only; never echo the supplied JSON.
        print(str(exc) if isinstance(exc, ReleaseBlocked) else 'Acceptance report or installer could not be verified')
        return 1
    print(json.dumps(result))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
