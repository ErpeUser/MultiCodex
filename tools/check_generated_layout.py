"""Validate canonical generated directories and public-tree safety.

The checker is intentionally local and deterministic. It does not inspect
remote GitHub state or read user profile contents.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "generated"
ALLOWED_GENERATED_DIRS = {"project", "runtime", "local"}
PRIVATE_NAMES = {
    "auth.json",
    "openai-codex-accounts.json",
    "api-routes.json",
    "local-client-tokens.json",
    "usage_cache.json",
    "cookies",
    "cookies-journal",
}


def tracked_paths() -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return [path for path in result.stdout.decode("utf-8").split("\0") if path]


def violations() -> list[str]:
    problems: list[str] = []
    if not GENERATED.is_dir():
        return ["generated/ is missing"]

    for entry in GENERATED.iterdir():
        if entry.name not in ALLOWED_GENERATED_DIRS:
            problems.append(f"unexpected generated entry: {entry.relative_to(ROOT)}")
        elif entry.is_file():
            problems.append(f"generated category is a file: {entry.relative_to(ROOT)}")

    for path in tracked_paths():
        normalized = path.replace("\\", "/")
        parts = normalized.split("/")
        if parts[0] == "generated" and len(parts) == 2:
            problems.append(f"generated file must be categorized: {path}")
        if len(parts) >= 2 and parts[0] == "generated" and parts[1] in {"runtime", "local"}:
            problems.append(f"local/generated runtime file is tracked: {path}")
        if Path(parts[-1]).name.lower() in PRIVATE_NAMES:
            problems.append(f"private-state filename is tracked: {path}")
    return sorted(set(problems))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    problems = violations()
    if not args.quiet:
        for problem in problems:
            print(f"LAYOUT_ERROR {problem}")
        print(f"LAYOUT_ERROR_COUNT {len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
