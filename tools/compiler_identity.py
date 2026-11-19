"""Read the actual Inno compiler version from its documented ISPP Ver value.

ISCC.exe can have a 0.0.0.0 PE file version. /O- disables installer output;
the probe contains no files, actions or account data.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import tempfile


def compiler_version(compiler: Path) -> str:
    script = '''#pragma message "MULTICODEX_INNO_VERSION=" + DecodeVer(Ver)
[Setup]
AppName=MultiCodex compiler identity probe
AppVersion=1
CreateAppDir=no
Uninstallable=no
'''
    temp_root = Path(__file__).resolve().parents[1] / 'generated/runtime/temp'
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='inno-identity-', dir=temp_root) as workspace:
        result = subprocess.run([str(compiler), '/O-', '-'], input=script,
                                capture_output=True, text=True, timeout=30, cwd=workspace)
    versions = re.findall(r'^(?:\s*Line \d+: )?MULTICODEX_INNO_VERSION=(\d+\.\d+\.\d+)\s*$',
                          result.stdout + '\n' + result.stderr, re.MULTILINE)
    if result.returncode != 0 or len(versions) != 1:
        raise ValueError('Compiler identity probe failed')
    return versions[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiler', type=Path)
    args = parser.parse_args()
    try:
        print(compiler_version(args.compiler))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
