# MultiCodex application safety rules

These rules complement the repository workflow in the root `AGENTS.md`.

1. Preserve source sessions. Profile adoption is link-only unless a separately reviewed, backup-first migration is designed.
2. Never commit `auth.json`, `openai-codex-accounts.json`, cookies, API keys, refresh tokens or raw provider responses.
3. A GUI-visible success must be confirmed by a backend operation. “Requested” is not “verified running”.
4. Processes may only be stopped after an exact per-profile identity check. Do not use name-wide termination.
5. Global `codex-multi-auth switch` must not be labeled instance account mapping.
6. New desktop product layouts require verification on real Windows builds.
7. Keep profile user data under `%LOCALAPPDATA%`, not in the installation directory.
8. Run full tests, bundle checks and Windows installer checks before release tags.
9. Retain third-party license information. Never redistribute official desktop binaries.
10. Separate Figma mockups from actual application screenshots in docs.
11. New managed logins use the official app-server and keyring mode. Do not synthesize OAuth tokens or ID tokens.
12. Never make process or network calls from Tk rendering or invoke widgets from worker threads.
13. A copied source ZIP, a Figma frame and a synthetic test are not Windows installer evidence.
14. Keep complete dependency locks and native acceptance as release blockers until actually verified. Never fabricate a lockfile, screenshot, test pass or release URL.
