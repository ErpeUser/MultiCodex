# Public GitHub and Generated-File Workflow

## Intent

Make the repository safe and predictable for a public GitHub checkout. Generated project material stays in its canonical project area, local build products and private state stay outside version control, and every agent works directly on the default branch.

## Goals

- Keep versioned generated project material under `generated/project/`.
- Keep builds, evidence, caches, dependencies, migrations, backups and user state under ignored `generated/runtime/` or `generated/local/`.
- Publish only the reviewed source tree to a public `ErpeUser/MultiCodex` repository.
- Document a direct-commit workflow on the repository default branch `main`.
- Provide a repeatable pull/sync check that inventories remote branches and pull requests before integrating newer work.

## Non-goals

- Committing local build outputs or personal credentials.
- Creating feature branches or pull requests for agent work.
- Automatically resolving an ambiguous or conflicting change without a reviewable local merge.

## Constraints

- GitHub CLI is the supported remote-management interface.
- The existing source layout and test suite remain the application entry points.
- Public history must not contain authentication files, tokens, cookies, local profiles, audit paths or generated runtime data.

## Approaches

1. Documentation and `.gitignore` only. This is small but cannot detect a misplaced generated file.
2. Local and CI layout checks plus agent instructions. This is the selected approach because it catches mistakes before commit and keeps the workflow portable.
3. Git hooks as the primary enforcement. This is weaker for cloud agents and fresh clones, so hooks are not the source of truth.

## Selected design

`AGENTS.md` is the repository-level workflow contract. `tools/check_generated_layout.py` fails when files are placed directly below `generated/` or when generated runtime/local data is staged. `tools/github_sync.py` fetches the default branch, inventories remote branches and open pull requests, classifies ahead/behind/diverged work, and applies only an unambiguous fast-forward or clean merge when requested. GitHub is created as a public repository with `main` as its default branch after the local tree passes the publication checks.
