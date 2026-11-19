"""Inspect and optionally integrate GitHub work before working on main.

The default mode is read-only. ``--apply`` integrates only remote branches
that are strictly ahead of the default branch and can be fast-forwarded.
Conflicting or ambiguous work is reported for a human decision.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class BranchStatus:
    name: str
    behind: int
    ahead: int
    status: str


def classify_branch(behind: int, ahead: int) -> str:
    if behind == 0 and ahead == 0:
        return "up_to_date"
    if behind > 0 and ahead == 0:
        return "behind"
    if behind == 0 and ahead > 0:
        return "ahead"
    return "diverged"


def command(args: list[str]) -> str:
    result = subprocess.run(
        args,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def default_branch() -> str:
    return command([
        "gh", "repo", "view", "--json", "defaultBranchRef",
        "--jq", ".defaultBranchRef.name",
    ])


def open_pull_requests() -> list[dict[str, object]]:
    raw = command([
        "gh", "pr", "list", "--state", "open", "--limit", "100",
        "--json", "number,title,headRefName,baseRefName,updatedAt,url",
    ])
    return json.loads(raw or "[]")


def branch_names() -> list[str]:
    raw = command([
        "git", "for-each-ref", "refs/remotes/origin",
        "--format=%(refname:strip=3)",
    ])
    return sorted({name for name in raw.splitlines() if name and name != "HEAD"})


def compare(default: str, branch: str) -> BranchStatus:
    raw = command([
        "git", "rev-list", "--left-right", "--count",
        f"origin/{default}...origin/{branch}",
    ])
    behind, ahead = (int(value) for value in raw.split())
    return BranchStatus(branch, behind, ahead, classify_branch(behind, ahead))


def inventory(default: str) -> tuple[list[BranchStatus], list[dict[str, object]]]:
    statuses = [compare(default, branch) for branch in branch_names() if branch != default]
    return statuses, open_pull_requests()


def integrate_ahead(default: str, statuses: list[BranchStatus]) -> list[str]:
    if command(["git", "branch", "--show-current"]) != default:
        raise RuntimeError(f"current branch is not {default}")
    if command(["git", "status", "--porcelain"]):
        raise RuntimeError("working tree must be clean before --apply")
    actions: list[str] = []
    for status in statuses:
        if status.status == "ahead":
            command(["git", "merge", "--ff-only", f"origin/{status.name}"])
            actions.append(f"fast-forwarded {status.name}")
        elif status.status == "diverged":
            raise RuntimeError(f"branch {status.name} diverged from {default}")
    return actions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="fast-forward strictly-ahead branches")
    parser.add_argument("--push", action="store_true", help="push applied changes to origin")
    args = parser.parse_args()

    command(["git", "fetch", "origin", "--prune"])
    default = default_branch()
    statuses, pull_requests = inventory(default)
    print(json.dumps({
        "default_branch": default,
        "branches": [asdict(status) for status in statuses],
        "open_pull_requests": pull_requests,
    }, ensure_ascii=False, indent=2))

    if args.push and not args.apply:
        parser.error("--push requires --apply")
    if args.apply:
        actions = integrate_ahead(default, statuses)
        for action in actions:
            print(f"SYNC_ACTION {action}")
        if args.push and actions:
            command(["git", "push", "origin", default])
    if any(status.status == "diverged" for status in statuses):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
