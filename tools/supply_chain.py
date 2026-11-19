"""Post-build CycloneDX inventory and conservative, fail-closed license gate.

Uses only the standard library. Inventory every shipped file, not the build
environment. Metadata declarations are evidence, not legal conclusions. Native
binaries without a separately reviewed attribution remain release blockers.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.parser import Parser
import hashlib
import json
from pathlib import Path
import re
import stat
import sys
from urllib.parse import quote


class InventoryError(ValueError):
    pass


# Deliberately small policy: unfamiliar expressions require review, never guess.
REVIEWED_EXPRESSIONS = frozenset({
    'MIT', 'BSD-2-Clause', 'BSD-3-Clause', 'Apache-2.0',
    'Apache-2.0 OR BSD-2-Clause', 'PSF-2.0',
    'MIT-CMU', 'HPND', 'ISC', 'Zlib',
    'GPL-2.0-or-later WITH Bootloader-exception',
})
IGNORED_OUTPUTS = frozenset({'SBOM.cdx.json', 'license-report.json'})


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _files(root: Path) -> list[Path]:
    result = []
    for path in sorted(root.rglob('*')):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise InventoryError('Linked bundle paths are not supported')
        if path.is_file() and path.relative_to(root).as_posix() not in IGNORED_OUTPUTS:
            result.append(path)
    return result


def _json(path: Path) -> dict:
    def unique(items):
        result = {}
        for name, value in items:
            if name in result:
                raise InventoryError('Duplicate JSON key')
            result[name] = value
        return result
    value = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise InventoryError('Expected a JSON object')
    return value


def _name(value: str) -> str:
    return re.sub(r'[-_.]+', '-', value).lower()


def _license_files(directory: Path) -> list[Path]:
    # Avoid attributing a nested npm package's notice to its parent.
    return [p for p in directory.rglob('*') if p.is_file()
            and 'node_modules' not in p.relative_to(directory).parts
            and re.match(r'^(license|licence|copying|notice|authors)(\.|$|[-_])', p.name, re.I)]


def inventory(bundle: Path, python_lock: Path, node_lock: Path, commit: str, *,
              python_version: str, node_version: str, node_archive_sha256: str) -> tuple[dict, dict]:
    bundle = bundle.absolute()
    if not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise InventoryError('Invalid source commit')
    if not re.fullmatch(r'[a-f0-9]{64}', node_archive_sha256):
        raise InventoryError('Missing verified Node archive hash')
    for part in (bundle, *bundle.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise InventoryError('Linked bundle root is not supported')
    files = _files(bundle)
    locked_python = {}
    for line in python_lock.read_text(encoding='utf-8-sig').splitlines():
        match = re.fullmatch(r'([\w.-]+)==([^ ]+)\s+--hash=sha256:([a-f0-9]{64})', line.strip())
        if match:
            locked_python[_name(match[1])] = (match[2], match[3])
        elif line.strip() and not line.lstrip().startswith('#'):
            raise InventoryError('Unsupported Python lock entry')
    locked_node = _json(node_lock).get('packages', {})
    components, blockers, dependencies = [], [], []
    owners = []

    def add_package(kind, name, version, expression, notices, properties=None, refs=None):
        purl = f'pkg:{kind}/{quote(name, safe="/")}@{quote(version, safe="")}'
        component = {'type': 'library', 'bom-ref': purl, 'name': name,
                     'version': version, 'purl': purl,
                     'properties': properties or []}
        if expression:
            component['licenses'] = [{'expression': expression}]
        if expression not in REVIEWED_EXPRESSIONS:
            blockers.append('LICENSE_REVIEW_REQUIRED:' + purl)
        if not notices:
            blockers.append('LICENSE_TEXT_MISSING:' + purl)
        for notice in notices:
            component['properties'].append({'name': 'multicodex:license-file',
                                           'value': notice.relative_to(bundle).as_posix()})
        if refs:
            component['externalReferences'] = refs
        components.append(component)
        return purl

    python_packages = {}
    for metadata in (p for p in files if p.name == 'METADATA' and p.parent.name.endswith('.dist-info')):
        message = Parser().parsestr(metadata.read_text(encoding='utf-8'))
        name, version = message.get('Name', ''), message.get('Version', '')
        if not name or not version:
            raise InventoryError('Incomplete Python distribution metadata')
        normalized = _name(name)
        locked = locked_python.get(normalized)
        if not locked or version != locked[0]:
            blockers.append('PYTHON_LOCK_MISMATCH:' + normalized)
        expression = message.get('License-Expression', '')
        if not expression:
            # Classifier is independently declared metadata, not text guessing.
            classifiers = message.get_all('Classifier', [])
            classifier_map = {'License :: OSI Approved :: MIT License': 'MIT',
                              'License :: OSI Approved :: BSD License': None,
                              'License :: OSI Approved :: Apache Software License': 'Apache-2.0'}
            candidates = {classifier_map[x] for x in classifiers if x in classifier_map}
            if len(candidates) == 1:
                expression = candidates.pop() or ''
        props = [{'name': 'multicodex:metadata', 'value': metadata.relative_to(bundle).as_posix()}]
        if locked:
            props.append({'name': 'multicodex:locked-wheel-sha256', 'value': locked[1]})
        ref = add_package('pypi', normalized, version, expression, _license_files(metadata.parent), props)
        python_packages[normalized] = (ref, message.get_all('Requires-Dist', []))
        owners.append((metadata.parent, ref))

    node_packages = {}
    modules = bundle / 'runtime'
    for package in (p for p in files if p.name == 'package.json' and 'node_modules' in p.parts):
        relative = package.parent.relative_to(modules).as_posix()
        # Only package roots, not examples/fixtures shipped inside a package.
        vendor = '/vendor/' in relative and relative.count('/vendor/') == 1
        if not vendor and not re.search(r'(?:^|/)node_modules/(?:@[^/]+/)?[^/]+$', relative):
            continue
        data = _json(package)
        name, version = data.get('name'), data.get('version')
        if not isinstance(name, str) or not isinstance(version, str):
            raise InventoryError('Incomplete npm package metadata')
        lock_path = relative
        if vendor:
            lock_path = relative.split('/vendor/', 1)[0] + '/node_modules/' + name
        locked = locked_node.get(lock_path)
        props = [{'name': 'multicodex:installed-path', 'value': relative}]
        if vendor:
            props.append({'name': 'multicodex:vendored-source-copy', 'value': lock_path})
        references = []
        if not isinstance(locked, dict) or locked.get('version') != version:
            blockers.append('NODE_LOCK_MISMATCH:' + name)
        else:
            origin = locked
            if locked.get('inBundle'):
                ancestor = lock_path
                while '/node_modules/' in ancestor:
                    ancestor = ancestor.rsplit('/node_modules/', 1)[0]
                    parent = locked_node.get(ancestor, {})
                    if parent.get('integrity'):
                        origin = parent
                        props.append({'name': 'multicodex:integrity-inherited-from', 'value': ancestor})
                        break
            if not origin.get('integrity'):
                blockers.append('NODE_INTEGRITY_MISSING:' + name)
            else:
                props.append({'name': 'multicodex:npm-integrity', 'value': origin['integrity']})
            if isinstance(origin.get('resolved'), str) and origin['resolved'].startswith('https://'):
                references.append({'type': 'distribution', 'url': origin['resolved']})
            if locked.get('license') and locked['license'] != data.get('license'):
                blockers.append('NODE_LICENSE_MISMATCH:' + name)
        expression = data.get('license') if isinstance(data.get('license'), str) else ''
        ref = add_package('npm', name, version, expression, _license_files(package.parent), props, references)
        # Distinct physical installations can have the same purl; references must remain unique.
        if ref in node_packages.values():
            components[-1]['bom-ref'] = ref + '?path=' + quote(relative, safe='')
            ref = components[-1]['bom-ref']
        node_packages[relative] = ref
        owners.append((package.parent, ref))

    for relative, locked in locked_node.items():
        if (relative and isinstance(locked, dict) and not locked.get('dev')
                and not locked.get('optional') and relative not in node_packages):
            blockers.append('NODE_PACKAGE_MISSING:' + relative)

    for ref, requires in python_packages.values():
        children = []
        for requirement in requires:
            match = re.match(r'([\w.-]+)', requirement)
            if match and _name(match[1]) in python_packages:
                children.append(python_packages[_name(match[1])][0])
        dependencies.append({'ref': ref, 'dependsOn': sorted(set(children))})
    for relative, ref in node_packages.items():
        package = _json(modules / relative / 'package.json')
        children = []
        for name in package.get('dependencies', {}):
            base = relative
            while True:
                candidate = base + '/node_modules/' + name
                if candidate in node_packages:
                    children.append(node_packages[candidate])
                    break
                if '/node_modules/' not in base:
                    candidate = 'node_modules/' + name
                    if candidate in node_packages:
                        children.append(node_packages[candidate])
                    break
                base = base.rsplit('/node_modules/', 1)[0]
        dependencies.append({'ref': ref, 'dependsOn': sorted(set(children))})

    for name, version, license_path in (
        ('CPython', python_version, '_internal/licenses/LICENSE.txt'),
        ('Node.js', node_version, 'runtime/Node-LICENSE.txt'),
    ):
        path = bundle / license_path
        component = {'type': 'platform', 'bom-ref': 'runtime:' + name, 'name': name,
                     'version': version,
                     'properties': [{'name': 'multicodex:license-file', 'value': license_path}]}
        if name == 'Node.js':
            component['externalReferences'] = [{'type': 'distribution',
                'url': f'https://nodejs.org/dist/v{version}/node-v{version}-win-x64.zip',
                'hashes': [{'alg': 'SHA-256', 'content': node_archive_sha256}]}]
        if not path.is_file():
            blockers.append('RUNTIME_LICENSE_MISSING:' + name)
        # Bundled runtime aggregate notices include multiple upstream licenses.
        blockers.append('RUNTIME_LICENSE_REVIEW_REQUIRED:' + name)
        components.append(component)

    for path in files:
        relative = path.relative_to(bundle).as_posix()
        component = {'type': 'file', 'bom-ref': 'file:' + relative, 'name': relative,
                     'hashes': [{'alg': 'SHA-256', 'content': digest(path)}]}
        owner = next((ref for directory, ref in sorted(owners, key=lambda x: len(x[0].parts), reverse=True)
                      if path.is_relative_to(directory)), None)
        if owner:
            component['properties'] = [{'name': 'multicodex:package', 'value': owner}]
        if path.suffix.lower() in ('.dll', '.pyd', '.exe'):
            blockers.append('NATIVE_LICENSE_REVIEW_REQUIRED:' + relative)
        components.append(component)
    bom = {'bomFormat': 'CycloneDX', 'specVersion': '1.6', 'version': 1,
           'metadata': {'timestamp': datetime.now(timezone.utc).isoformat(),
                        'lifecycles': [{'phase': 'post-build'}],
                        'component': {'type': 'application', 'name': 'MultiCodex',
                                      'version': commit},
                        'properties': [{'name': 'multicodex:source-commit', 'value': commit},
                                       {'name': 'multicodex:python-lock-sha256', 'value': digest(python_lock)},
                                       {'name': 'multicodex:node-lock-sha256', 'value': digest(node_lock)}]},
           'components': components, 'dependencies': dependencies}
    report = {'schema': 1, 'source_commit': commit, 'files': len(files),
              'components': len(components), 'ready': not blockers,
              'blockers': sorted(set(blockers)),
              'scope': 'Post-build files and declared package metadata; native/aggregate license review required. '
                       'Lock hashes establish acquisition provenance, not extracted-byte equivalence.'}
    return bom, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--python-lock', type=Path, required=True)
    parser.add_argument('--node-lock', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--node-version', required=True)
    parser.add_argument('--node-archive-sha256', required=True)
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args()
    try:
        bom, report = inventory(args.bundle, args.python_lock, args.node_lock, args.commit,
            python_version='.'.join(map(str, sys.version_info[:3])), node_version=args.node_version,
            node_archive_sha256=args.node_archive_sha256)
        bom_path = args.bundle / 'SBOM.cdx.json'
        bom_path.write_text(json.dumps(bom, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
        report['sbom_sha256'] = digest(bom_path)
        (args.bundle / 'license-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    except (ValueError, OSError, UnicodeError, RecursionError):
        print('Bundle inventory could not be verified')
        return 1
    print(json.dumps({'components': report['components'], 'files': report['files'],
                      'license_blockers': len(report['blockers']), 'release_ready': report['ready']}))
    return 1 if args.strict and not report['ready'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
