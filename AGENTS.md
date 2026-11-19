# MultiCodex agent rules

This repository is public. Work in the existing checkout and use the repository default branch `main`.

## Branch and commit workflow

- Before any change, run `git status --short --branch`, `git fetch origin --prune`, and `py -3.12 tools/github_sync.py`.
- Work directly on `main`. Do not create or switch to feature, codex, topic or temporary branches.
- Do not create pull requests for agent work. Commit reviewed changes directly to `main`, then push with `git push origin main`.
- Never force-push. If the local branch is behind or diverged, resolve it on `main` after inspecting the remote and any open pull requests.
- After every pull or fetch, inspect remote branches and open pull requests. Use the newest compatible fix, combine independent compatible changes, and stop for a conflict that needs a human choice.
- Use `tools/pull_and_regenerate.ps1` for the pull path. It records the pre-pull commit, performs the fast-forward pull, classifies changed files, regenerates an affected Figma extension when `-FigmaPluginId` is supplied, and rebuilds/tests the Windows EXE, installer and shortcut definition when desktop inputs changed.
- Documentation-only pulls finish without regeneration. A changed Figma renderer or token file requires a real assigned numeric plugin ID. A changed application, packaging or installer input runs the existing Windows build and its packaged runtime, GUI, installation, upgrade and uninstall checks.
- Keep commits focused and describe the behavior changed. Run the relevant tests before committing.

## Generated and private data

- Versioned project material belongs under `generated/project/`.
- Builds, installers, evidence, caches, downloaded tools, virtual environments, migration backups, Git backups and local tool state belong under ignored `generated/runtime/` or `generated/local/`.
- Do not create files directly below `generated/`. Run `py -3.12 tools/check_generated_layout.py` before committing.
- Never commit credentials, cookies, profiles, browser state, local databases, API keys, tokens, raw provider responses or private audit paths.
- Use synthetic fixtures and temporary directories for tests.

## GitHub publication

- The canonical public repository is `ErpeUser/MultiCodex`.
- Keep the default branch named `main`.
- Do not use `gh pr create` for agent changes. Existing branches or pull requests found by the sync check must be reviewed and integrated or explicitly left for a human decision.
- Do not publish generated runtime/local content or release evidence from a personal machine. GitHub Actions artifacts are temporary outputs and are not source files.

Read [generated/project/governance/AGENTS.md](generated/project/governance/AGENTS.md) for application-specific safety rules.
