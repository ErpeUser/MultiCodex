"""Conservatively prune *regenerable* MultiCodex build and cache artifacts.

Dry-run by default; call with --apply after reviewing the printed plan.
Never touches source, Git, protected outputs, evidence, rollback, installed
applications, user profiles, or the migration recovery archive.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {
    "cache": (
        "generated/runtime/cache/pip",
        "generated/runtime/cache/npm",
        "generated/runtime/cache/pycache",
        "generated/runtime/cache/ruff",
        "generated/runtime/cache/pyinstaller",
    ),
    "validation-build": (
        "generated/runtime/build/pyinstaller",
        "generated/runtime/dist/MultiCodex",
    ),
    "downloads": (
        "generated/runtime/downloads/PowerShell-7.7.0-win-x64.zip",
        "generated/runtime/downloads/actionlint_1.7.12_windows_amd64.zip",
    ),
}
ARCHIVES = {
    "PowerShell-7.7.0-win-x64.zip": (
        "7c74e03b20a75b59715847439d046a6214b1863ee79b187872980f139bb4a05f",
        "generated/runtime/dependencies/toolchains/powershell-7.7.0/pwsh.exe",
    ),
    "actionlint_1.7.12_windows_amd64.zip": (
        "6e7241b51e6817ea6a047693d8e6fed13b31819c9a0dd6c5a726e1592d22f6e9",
        "generated/runtime/dependencies/toolchains/actionlint-1.7.12/actionlint.exe",
    ),
}
PROTECTED = (
    "generated/runtime/output/Codex-Multi-Studio-Setup-v0.2.1-dev.exe",
    "generated/runtime/output/MultiCodex-0.2.1-dev-win-x64-portable.zip",
    "generated/runtime/evidence/build.json",
    "generated/runtime/build/rollback-MultiCodex-0.2.0-dev/MultiCodex.exe",
    "generated/project/docs/implementation-status.json",
)

def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()

def allowed(relative: str) -> bool:
    return relative in {name for names in CATEGORIES.values() for name in names}

def _is_link(path: Path) -> bool:
    try:
        data = path.lstat()
    except FileNotFoundError:
        return False
    return bool(stat.S_ISLNK(data.st_mode) or
                getattr(data, "st_file_attributes", 0) & 0x400)

def assert_plain(path: Path) -> None:
    if not path.is_relative_to(ROOT):
        raise ValueError("Path outside project root")
    for item in (path, *path.parents):
        if item == ROOT.parent:
            break
        if _is_link(item):
            raise ValueError("Linked/reparse path refused")

def inventory(relative: str) -> dict:
    if not allowed(relative):
        raise ValueError("Cleanup target not on allowlist")
    path = ROOT / relative
    assert_plain(path)
    if not path.exists():
        return {"path": relative, "files": 0, "bytes": 0, "exists": False}
    if path.is_file():
        return {"path": relative, "files": 1, "bytes": path.stat().st_size,
                "exists": True}
    files, size = 0, 0
    for here, directories, names in os.walk(path, followlinks=False):
        for name in directories + names:
            entry = Path(here) / name
            if _is_link(entry):
                raise ValueError("Linked member refused: " + relative)
            if entry.is_file():
                files += 1
                size += entry.stat().st_size
    return {"path": relative, "files": files, "bytes": size, "exists": True}

def protected_hashes() -> dict[str, str]:
    output = {}
    for name in PROTECTED:
        file = ROOT / name
        assert_plain(file)
        if not file.is_file():
            raise ValueError("Protected source missing: " + name)
        output[name] = digest(file)
    return output

def validate_category(name: str) -> None:
    if name == "downloads":
        for relative in CATEGORIES["downloads"]:
            zipfile = ROOT / relative
            if not zipfile.is_file():
                continue
            expected_sha, extracted = ARCHIVES[zipfile.name]
            if digest(zipfile) != expected_sha or not (ROOT / extracted).is_file():
                raise ValueError("Archive checksum or unpacked tool missing: " + zipfile.name)
    if name == "validation-build":
        intermediate = ROOT / "generated/runtime/build/pyinstaller/MultiCodex/MultiCodex.exe"
        bundled = ROOT / "generated/runtime/dist/MultiCodex/MultiCodex.exe"
        log = ROOT / "generated/runtime/reports/pyinstaller-migration-validation.log"
        if intermediate.exists() or bundled.exists():
            if not log.is_file():
                raise ValueError("Validation build report missing")
            raw = log.read_bytes()
            encoding = "utf-16" if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else "utf-8-sig"
            text = raw.decode(encoding, errors="replace")
            if (not intermediate.is_file() or not bundled.is_file()
                    or digest(intermediate) != digest(bundled)
                    or "Build complete!" not in text):
                raise ValueError("Validation build not verified; refusing to discard it")

def plan(categories: tuple[str, ...]) -> list[dict]:
    rows = []
    for category in categories:
        if category not in CATEGORIES:
            raise ValueError("Unknown cleanup category")
        validate_category(category)
        for relative in CATEGORIES[category]:
            item = inventory(relative)
            item["category"] = category
            rows.append(item)
    return rows

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--categories", default="cache,validation-build,downloads",
                        help="Comma-separated: cache,validation-build,downloads")
    parser.add_argument("--apply", action="store_true",
                        help="Actually remove reviewed allowlisted artifacts")
    args = parser.parse_args(argv)
    categories = tuple(dict.fromkeys(value.strip() for value in args.categories.split(",")))
    items = plan(categories)
    total = sum(item["bytes"] for item in items if item["exists"])
    for item in items:
        if item["exists"]:
            print(f"{'REMOVE' if args.apply else 'PLAN'} {item['path']}: "
                  f"{item['files']} files, {item['bytes']} bytes")
    print(f"RECLAIMABLE_BYTES={total}; MODE={'APPLY' if args.apply else 'DRY_RUN'}")
    if not args.apply:
        return 0
    report = (ROOT / 'generated/runtime/reports' /
              ('cleanup-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f') + '.json'))
    if report.exists():
        raise ValueError('Cleanup manifest collision; refusing deletion')
    before = protected_hashes()
    for item in items:
        if not item["exists"]:
            continue
        path = ROOT / item["path"]
        assert_plain(path)
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    after = protected_hashes()
    if before != after:
        raise RuntimeError("Protected artifact changed unexpectedly; investigate")
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps({
        "schema": 1, "completed_at": datetime.now(timezone.utc).isoformat(),
        "removed": [row for row in items if row["exists"]],
        "reclaimed_bytes": total, "protected_sha256": after,
        "policy": "Only allowlisted regenerable artifacts; no release or user data",
        }, indent=2) + "\n")
    print("PROTECTED_HASHES_UNCHANGED=True")
    print("REPORT=" + report.relative_to(ROOT).as_posix())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
