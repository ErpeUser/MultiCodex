# Public GitHub Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Publish a clean public repository and enforce canonical generated-file and default-branch workflows.

**Architecture:** Keep versioned project artifacts in `generated/project`, ignore runtime/local artifacts, and add small repository tools for layout and GitHub synchronization checks. Root `AGENTS.md` defines direct work on `main`.

**Tech Stack:** Git, GitHub CLI, Python 3.12, PowerShell, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-19-public-github-workflow-design.md`

## Global Constraints

- Public repository: `ErpeUser/MultiCodex`.
- Default branch: `main`.
- Agent changes are committed and pushed directly to `main`.
- No agent-created feature branches or pull requests.
- `generated/project/` is versioned project material. `generated/runtime/` and `generated/local/` are ignored.
- Credentials, cookies, profiles, local databases, audit paths and generated runtime data remain unpublished.

## Review Focus

- A file directly under `generated/` must fail the layout check.
- A tracked candidate under `generated/runtime/` or `generated/local/` must fail publication checks.
- A sync against a missing or inaccessible GitHub repository must fail clearly.
- A remote branch that is ahead, behind or diverged must be classified before integration.
- A public tree must not contain known credential or local-state filenames.

### Task 1: Canonical generated layout and publication safety

**Files:**
- Modify: `.gitignore`
- Create: `tools/check_generated_layout.py`
- Modify: `tests/test_generated_layout.py`
- Create: `README.md`
- Create: `AGENTS.md`
- Modify: `generated/project/governance/AGENTS.md`
- Modify: `generated/project/docs/LAYOUT.md`

- [ ] Add ignore rules and canonical root documentation.
- [ ] Implement the layout/publication checker with a nonzero exit for misplaced or staged private artifacts.
- [ ] Add tests for the canonical directories and representative ignored paths.
- [ ] Run the focused layout tests.

### Task 2: Pull/sync inventory for agents

**Files:**
- Create: `tools/github_sync.py`
- Modify: `tests/test_generated_layout.py` or a focused new test module
- Modify: `generated/project/governance/AGENTS.md`

- [ ] Implement default-branch discovery, fetch/prune, branch inventory, open-PR inventory and ahead/behind classification.
- [ ] Add a dry-run default and an explicit apply mode for clean integrations.
- [ ] Test classification without network access using pure helper functions.

### Task 3: Public GitHub migration and verification

**Files:**
- Modify: `.github/workflows/feature-checks.yml`
- Modify: `.github/workflows/windows.yml`
- Modify: public-history documentation that still says the repository is private

- [ ] Move any root-level generated recovery note into ignored local storage.
- [ ] Update stale private-repository statements and branch triggers.
- [ ] Run layout, reference, unit and Node checks.
- [ ] Create `ErpeUser/MultiCodex` as public with `main` as the default branch and push only the reviewed `main` history.
- [ ] Verify repository visibility, default branch, branches, open PRs, and tracked-file safety with fresh commands.
