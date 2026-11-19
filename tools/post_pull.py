"""Decide and run generated artifacts affected by a completed Git pull.

The decision is based on changed source paths. The default mode only reports
the impact. ``--run`` executes the existing Figma and Windows build entry
points when their inputs changed.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Impact:
    extension: bool = False
    desktop_exe: bool = False
    desktop_shortcut: bool = False
    desktop_installer: bool = False
    reasons: list[str] = field(default_factory=list)


def classify_paths(paths: list[str]) -> Impact:
    impact = Impact()
    for raw_path in paths:
        path = raw_path.replace("\\", "/")
        if (
            path.startswith("plugins/figma/")
            or path == "tools/build_figma_plugin.py"
            or path == "multicodex/ui_tokens.py"
        ):
            impact.extension = True
            impact.reasons.append(f"extension source changed: {path}")
        if (
            path.startswith("multicodex/")
            or path.startswith("bridge/")
            or path in {"run.py", "packaging/MultiCodex.spec", "tools/build_windows.ps1"}
            or path.startswith("generated/project/config/python/")
            or path.startswith("generated/project/config/build/")
        ):
            impact.desktop_exe = True
            impact.desktop_installer = True
            impact.reasons.append(f"desktop application source changed: {path}")
        if path in {"packaging/MultiCodex.iss", "tools/installer_smoke.ps1"}:
            impact.desktop_shortcut = True
            impact.desktop_installer = True
            impact.reasons.append(f"desktop installer or shortcut changed: {path}")
    impact.reasons = sorted(set(impact.reasons))
    return impact


def changed_paths(base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", base, head],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [path for path in result.stdout.splitlines() if path]


def run_checked(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def run_extension(plugin_id: str | None, output: Path) -> list[str]:
    if not plugin_id:
        raise RuntimeError(
            "Figma source changed. Set MULTICODEX_FIGMA_PLUGIN_ID to the assigned numeric ID before --run."
        )
    output = output.resolve()
    run_checked([
        sys.executable,
        "tools/build_figma_plugin.py",
        "--plugin-id",
        plugin_id,
        "--output",
        str(output),
    ])
    run_checked([
        sys.executable,
        "tools/build_figma_plugin.py",
        "--plugin-id",
        plugin_id,
        "--output",
        str(output),
        "--check",
    ])
    node = shutil.which("node")
    if node:
        run_checked([node, "--test", "tests/figma/renderer.test.cjs"])
    return [f"extension package generated at {output}", "extension package verified"]


def run_desktop() -> list[str]:
    if platform.system() != "Windows":
        raise RuntimeError("Windows EXE and shortcut regeneration requires Windows")
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell:
        raise RuntimeError("PowerShell is required for Windows EXE and shortcut regeneration")
    run_checked([powershell, "-NoProfile", "-File", "tools/build_windows.ps1"])
    return ["Windows EXE, installer, shortcut definition and smoke checks completed"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="base", required=True, help="commit before the pull")
    parser.add_argument("--to", dest="head", default="HEAD", help="commit after the pull")
    parser.add_argument("--run", action="store_true", help="regenerate affected artifacts")
    parser.add_argument("--figma-plugin-id", default=os.environ.get("MULTICODEX_FIGMA_PLUGIN_ID"))
    parser.add_argument("--extension-output", type=Path)
    args = parser.parse_args()

    paths = changed_paths(args.base, args.head)
    impact = classify_paths(paths)
    report = {"base": args.base, "head": args.head, "changed_paths": paths, **asdict(impact)}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.run:
        return 0

    actions: list[str] = []
    if impact.extension:
        output = args.extension_output or ROOT / "generated/runtime/output" / f"figma-reference-{args.head[:12]}"
        actions.extend(run_extension(args.figma_plugin_id, output))
    if impact.desktop_installer:
        actions.extend(run_desktop())
    for action in actions:
        print(f"POST_PULL_ACTION {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
