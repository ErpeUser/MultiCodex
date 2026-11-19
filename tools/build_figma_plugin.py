"""Build/check an offline Figma development plugin using application color tokens.

Supply the plugin ID assigned by Figma's New Plugin dialog. No invented ID,
remote upload, credential access or third-party font redistribution is performed.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat


class PackageError(ValueError):
    pass


def _plain_path(path: Path) -> Path:
    path = Path(path).absolute()
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise PackageError('LINKED_PATH')
    return path


def _source_files(root: Path, plugin_id: str) -> dict[str, bytes]:
    if not isinstance(plugin_id, str) or re.fullmatch(r'[0-9]{10,40}', plugin_id) is None:
        raise PackageError('ASSIGNED_FIGMA_PLUGIN_ID_REQUIRED')
    root = _plain_path(root)
    try:
        token_bytes = _plain_path(root / 'multicodex/ui_tokens.py').read_bytes()
        renderer = _plain_path(root / 'plugins/figma/renderer.js').read_bytes()
        if len(token_bytes) > 65536 or len(renderer) > 262144:
            raise PackageError('SOURCE_TOO_LARGE')
        values = {}
        for statement in ast.parse(token_bytes.decode('utf-8')).body:
            if isinstance(statement, ast.Assign):
                for target in statement.targets:
                    if isinstance(target, ast.Name) and target.id in {'THEMES', 'NAV_WIDTH', 'RADIUS', 'RADIUS_SCALE'}:
                        node = statement.value
                        if (target.id == 'RADIUS' and isinstance(node, ast.Subscript)
                                and isinstance(node.value, ast.Name) and node.value.id == 'RADIUS_SCALE'):
                            values[target.id] = values['RADIUS_SCALE'][ast.literal_eval(node.slice)]
                        else:
                            values[target.id] = ast.literal_eval(node)
        themes = values['THEMES']
        names = {'canvas', 'rail', 'panel', 'text', 'muted', 'accent', 'accent_text', 'border', 'selected'}
        if set(themes) != {'dark', 'light'}:
            raise PackageError('INVALID_TOKENS')
        for palette in themes.values():
            if not names <= set(palette) or any(not isinstance(v, str) or re.fullmatch(r'#[0-9A-Fa-f]{6}', v) is None for v in palette.values()):
                raise PackageError('INVALID_TOKENS')
        if (type(values['NAV_WIDTH']) is not int or not 180 <= values['NAV_WIDTH'] <= 300 or
                type(values['RADIUS']) is not int or not 0 <= values['RADIUS'] <= 32):
            raise PackageError('INVALID_TOKENS')
        config = {'schema': 1, 'themes': themes, 'navWidth': values['NAV_WIDTH'], 'radius': values['RADIUS']}
        prefix = 'const MC_CONFIG = ' + json.dumps(config, ensure_ascii=True, allow_nan=False) + ';\n'
        suffix = ("\nbuildReference(figma, MC_CONFIG).then(() => {\n"
                  "  figma.closePlugin('12 editierbare Designreferenzen erstellt. Keine Laufzeitabnahme.');\n"
                  "}).catch(() => {\n"
                  "  figma.closePlugin('Designreferenz nicht abgeschlossen. Bestehende Ansichten wurden nicht ersetzt; eine neue Teilseite kann erhalten bleiben.');\n"
                  "});\n")
        code = prefix.encode() + renderer + suffix.encode()
        manifest = {'name': 'MultiCodex - Designreferenz', 'id': plugin_id, 'api': '1.0.0',
                    'main': 'code.js', 'editorType': ['figma'], 'documentAccess': 'dynamic-page',
                    'networkAccess': {'allowedDomains': ['none']}}
        metadata = {'schema': 1, 'token_source_sha256': hashlib.sha256(token_bytes).hexdigest(),
                    'renderer_source_sha256': hashlib.sha256(renderer).hexdigest(),
                    'code_sha256': hashlib.sha256(code).hexdigest(),
                    'scope': 'local development plugin; live Figma rendering still requires inspection'}
        encode = lambda value: (json.dumps(value, indent=2, ensure_ascii=True) + '\n').encode()
        return {'manifest.json': encode(manifest), 'code.js': code, 'package-meta.json': encode(metadata)}
    except (KeyError, TypeError, SyntaxError, UnicodeError, OSError, ValueError):
        raise PackageError('SOURCE_INVALID_OR_UNAVAILABLE') from None


def build_package(root: Path, output: Path, plugin_id: str) -> dict:
    files = _source_files(root, plugin_id)
    try:
        output = _plain_path(output)
        output.mkdir(parents=True, exist_ok=False)
        for name, content in files.items():
            path = _plain_path(output / name)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
        return {'files': sorted(files), 'scope': 'package created, not executed in Figma'}
    except OSError:
        raise PackageError('OUTPUT_NOT_CREATED_OR_ALREADY_EXISTS') from None


def verify_package(root: Path, output: Path, plugin_id: str) -> bool:
    expected = _source_files(root, plugin_id)
    try:
        output = _plain_path(output)
        if {path.name for path in output.iterdir()} != set(expected):
            raise PackageError('UNEXPECTED_PACKAGE_FILES')
        for name, content in expected.items():
            path = _plain_path(output / name)
            if path.stat().st_size != len(content) or path.read_bytes() != content:
                raise PackageError('PACKAGE_STALE_OR_CHANGED')
    except OSError:
        raise PackageError('PACKAGE_UNAVAILABLE') from None
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        if args.check:
            verify_package(root, args.output, args.plugin_id)
            print('Plugin package matches the current source. No live Figma validation implied.')
        else:
            build_package(root, args.output, args.plugin_id)
            print('Plugin package created. Import manifest.json in Figma Desktop; inspect the generated reference page.')
    except (PackageError, OSError):
        print('Plugin package not created/verified. Check the assigned plugin ID, source files and output path; existing files are not overwritten.')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
