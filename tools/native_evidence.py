"""Bind machine evidence to a source commit and installer, never approve a release.

Reports can verify consistency, not the truth of human/provider assertions. Native
OAuth, identity isolation and keyboard acceptance remain in release_gate.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import warnings

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.release_gate import REQUIRED_CHECKS

PAGES = ('Overview', 'Instances', 'Accounts', 'Usage', 'Settings', 'Diagnostics')
SIZES = ((900, 640), (1180, 760))
DPI_PERCENT = (100, 125, 150, 200)
REPORTS = ('source-runtime.json', 'source-gui.json', 'packaged-runtime.json',
           'packaged-gui.json', 'installed/installed-runtime.json',
           'installed/installed-gui.json', 'installed/installer-smoke.json')
MAX_JSON = 262144


class EvidenceError(ValueError):
    """Controlled errors only; do not print file contents or subprocess output."""


def _safe_path(path: Path) -> Path:
    path = Path(path).absolute()
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise EvidenceError('LINKED_PATH')
    return path


def file_hash(path: Path) -> str:
    try:
        path = _safe_path(path)
        if not path.is_file() or path.stat().st_size > 2 * 1024**3:
            raise EvidenceError('INVALID_FILE')
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
    except OSError:
        raise EvidenceError('FILE_UNAVAILABLE') from None


def read_json(path: Path) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise EvidenceError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    try:
        path = _safe_path(path)
        with path.open('rb') as stream:
            data = stream.read(MAX_JSON + 1)
        if len(data) > MAX_JSON:
            raise EvidenceError('REPORT_TOO_LARGE')
        result = json.loads(data.decode('utf-8-sig'), object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if type(result) is not dict:
            raise EvidenceError('INVALID_REPORT')
        return result
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise EvidenceError('INVALID_REPORT') from None


def write_report(path: Path, report: dict) -> None:
    """Create a new report only. Never replace old evidence or a user-edited draft."""
    try:
        raw = (json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + '\n').encode()
        path = _safe_path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        _safe_path(path)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, ValueError, TypeError):
        raise EvidenceError('OUTPUT_NOT_CREATED') from None


def source_identity(root: Path) -> str:
    """Require a clean real git working tree, including untracked source files."""
    try:
        root = _safe_path(root)
        def git(*args):
            return subprocess.run(['git', '-C', str(root), *args], check=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=15, text=True).stdout.strip()
        commit = git('rev-parse', 'HEAD')
        if not re.fullmatch('[0-9a-f]{40}', commit) or git('status', '--porcelain', '--untracked-files=all'):
            raise EvidenceError('SOURCE_NOT_CLEAN')
        return commit
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise EvidenceError('SOURCE_UNAVAILABLE') from None


def capture_plan() -> list[dict]:
    return [{'page': page, 'theme': theme, 'window_size': list(size),
             'file': f'{theme}-{size[0]}x{size[1]}-{page.lower()}.png'}
            for theme in ('dark', 'light') for size in SIZES for page in PAGES]


def _validate_png(path: Path, size: list) -> None:
    from PIL import Image
    try:
        if (not isinstance(size, list) or len(size) != 2 or
                any(type(v) is not int or not 150 <= v <= 16384 for v in size) or
                size[0] * size[1] > 32_000_000 or path.stat().st_size > 32 * 1024**2):
            raise EvidenceError('INVALID_IMAGE')
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format != 'PNG' or tuple(size) != image.size:
                    raise EvidenceError('INVALID_IMAGE')
                image.verify()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        raise EvidenceError('INVALID_IMAGE') from None


def validate_capture(folder: Path, commit: str, setup_hash: str) -> dict:
    folder = _safe_path(folder)
    try:
        manifest = read_json(folder / 'manifest.json')
        percent = manifest.get('dpi_percent')
        if (type(manifest.get('schema')) is not int or manifest['schema'] != 1 or
                manifest.get('source_commit') != commit or manifest.get('setup_sha256') != setup_hash or
                manifest.get('platform') != 'win32' or manifest.get('capture_kind') != 'owned-window' or
                type(percent) is not int or percent not in DPI_PERCENT):
            raise EvidenceError('CAPTURE_BINDING_MISMATCH')
        rows = manifest.get('files')
        expected = {row['file']: row for row in capture_plan()}
        if not isinstance(rows, list) or len(rows) != len(expected):
            raise EvidenceError('CAPTURE_MATRIX_INCOMPLETE')
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('file'), str):
                raise EvidenceError('INVALID_CAPTURE')
            name = row['file']
            if name not in expected or name in seen:
                raise EvidenceError('INVALID_CAPTURE')
            seen.add(name)
            if (any(row.get(k) != v for k, v in expected[name].items()) or
                    type(row.get('native_dpi')) is not int or row['native_dpi'] != percent * 96 // 100 or
                    row.get('dpi_awareness') != 'per-monitor'):
                raise EvidenceError('CAPTURE_MATRIX_MISMATCH')
            path = _safe_path(folder / name)
            if row.get('sha256') != file_hash(path):
                raise EvidenceError('CAPTURE_HASH_MISMATCH')
            _validate_png(path, row.get('image_size'))
        return {'dpi_percent': percent, 'count': len(rows),
                'manifest_sha256': file_hash(folder / 'manifest.json')}
    except FileNotFoundError:
        raise EvidenceError('CAPTURE_MISSING') from None


def collect_evidence(evidence_dir: Path, setup: Path, commit: str,
                     capture_dirs=()) -> dict:
    if not isinstance(commit, str) or not re.fullmatch('[0-9a-f]{40}', commit):
        raise EvidenceError('INVALID_COMMIT')
    evidence_dir = _safe_path(evidence_dir)
    digest = file_hash(setup)
    try:
        build = read_json(evidence_dir / 'build.json')
    except FileNotFoundError:
        raise EvidenceError('BUILD_MISSING') from None
    if (build.get('source_commit') != commit or build.get('source_dirty') is not False or
            build.get('setup_sha256') != digest):
        raise EvidenceError('BUILD_BINDING_MISMATCH')
    checks = {}
    hashes = {'build.json': file_hash(evidence_dir / 'build.json')}
    supply_chain = {}
    if 'sbom_sha256' in build or 'license_report_sha256' in build:
        for field, name in (('sbom_sha256', 'SBOM.cdx.json'),
                            ('license_report_sha256', 'license-report.json')):
            try:
                actual = file_hash(evidence_dir / name)
            except (EvidenceError, FileNotFoundError):
                raise EvidenceError('SUPPLY_CHAIN_FILE_MISSING') from None
            if build.get(field) != actual:
                raise EvidenceError('SUPPLY_CHAIN_BINDING_MISMATCH')
            supply_chain[field] = actual
            hashes[name] = actual
    for name in REPORTS:
        try:
            doc = read_json(evidence_dir / name)
            hashes[name] = file_hash(evidence_dir / name)
            checks[name] = 'PASS' if doc.get('ready') is True else 'NOT_READY'
            if name.endswith('installer-smoke.json') and doc.get('setup_sha256') != digest:
                checks[name] = 'BINDING_MISMATCH'
        except FileNotFoundError:
            checks[name] = 'MISSING'
        except EvidenceError:
            checks[name] = 'INVALID'
    try:
        index = read_json(evidence_dir / 'build-index.json')
        checks['build-index.json'] = ('PASS' if type(index.get('schema')) is int and
            index['schema'] == 1 and index.get('source_commit') == commit and
            index.get('setup_sha256') == digest and index.get('report_sha256') == hashes
            else 'BINDING_MISMATCH')
    except FileNotFoundError:
        checks['build-index.json'] = 'MISSING'
    except EvidenceError:
        checks['build-index.json'] = 'INVALID'
    captures = [validate_capture(Path(folder), commit, digest) for folder in capture_dirs]
    present = {row['dpi_percent'] for row in captures}
    if len(present) != len(captures):
        raise EvidenceError('DUPLICATE_DPI_GROUP')
    missing = [percent for percent in DPI_PERCENT if percent not in present]
    return {'schema': 1, 'source_commit': commit, 'setup_sha256': digest,
            **supply_chain,
            'automated_ready': not missing and all(state == 'PASS' for state in checks.values()),
            'release_ready': False, 'checks': checks, 'report_sha256': hashes,
            'captures': sorted(captures, key=lambda row: row['dpi_percent']),
            'capture_count': sum(row['count'] for row in captures), 'missing_dpi_percent': missing,
            'pending_manual_checks': list(REQUIRED_CHECKS),
            'scope': 'Evidence consistency only; source-GUI captures are not packaged/native account acceptance.'}


def seal_build(evidence_dir: Path, setup: Path, commit: str) -> dict:
    """Record exact report bytes immediately after a successful fresh build.

    This is a hash index, not a digital signature or an independent attestation.
    The Windows runner archives old build output before invoking the builder.
    """
    report = collect_evidence(evidence_dir, setup, commit)
    if any(report['checks'][name] != 'PASS' for name in REPORTS):
        raise EvidenceError('BUILD_REPORTS_INCOMPLETE')
    index = {'schema': 1, 'source_commit': commit, 'setup_sha256': report['setup_sha256'],
             'report_sha256': report['report_sha256']}
    write_report(Path(evidence_dir) / 'build-index.json', index)
    return index


def acceptance_draft(report: dict) -> dict:
    return {'schema': 1, 'source_commit': report['source_commit'],
            'setup_sha256': report['setup_sha256'], 'reviewer': None, 'checked_at': None,
            'sbom_sha256': report.get('sbom_sha256'),
            'license_report_sha256': report.get('license_report_sha256'),
            'license_review': [],
            'checks': {name: False for name in REQUIRED_CHECKS}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--setup', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--captures', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--seal-build', action='store_true')
    parser.add_argument('--draft', type=Path)
    args = parser.parse_args(argv)
    if not args.seal_build and args.output is None:
        parser.error('--output is required when collecting evidence')
    try:
        if args.seal_build:
            seal_build(args.evidence, args.setup, args.commit)
            print('Build evidence hashes recorded; native acceptance is not granted.')
            return 0
        report = collect_evidence(args.evidence, args.setup, args.commit, args.captures)
        write_report(args.output, report)
        if args.draft is not None:
            write_report(args.draft, acceptance_draft(report))
    except (EvidenceError, OSError):
        print('Evidence could not be verified or new output could not be created. Existing evidence was not replaced.')
        return 2
    print(json.dumps({'automated_ready': report['automated_ready'], 'release_ready': False,
                      'capture_count': report['capture_count'], 'missing_dpi_percent': report['missing_dpi_percent']}))
    return 0 if report['automated_ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
