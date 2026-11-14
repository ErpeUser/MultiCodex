# Exact-account profile starts and workspace visibility

Continuation of `feature/quota-history-monitoring-20261114`, based on
`4e85660da8e6e4fd95ee52aaa4b6a3e783ded072`. This is a development feature,
not a completed Windows release or an unrestricted workspace-rotation system.

## Using the new controls

1. Keep/add official saved logins using the existing Accounts page.
2. Under Settings, explicitly select the profiles permitted for monitoring/start.
3. Under Usage, enable **Startauftraege ausfuehren**, select the exact saved
   login and choose **Profilstart vormerken**.
4. The persistent request checks official quota and identity. Insufficient
   capacity waits on that same account; it never selects a substitute account.
5. A stopped instance is bound to the selected saved authentication home and
   launched. An already running matching instance is reused. A running different
   login is never stopped or rebound automatically.
6. Interrupted cutovers remain visible. Close the affected window yourself before
   restoring changed metadata. Recovery never force-kills a process.

Turning start execution off pauses execution, not historical records. A cancelled
request stays in history. A stale or unknown quota never becomes available merely
because a countdown expires. The existing quota monitor remains read-only; a
requested start performs additional bounded preflight/post-start observations.

## Implemented boundaries

- `automation_state.py`: SQLite journal, explicit transitions, compare-and-swap,
  one pending request per profile, durable failure/recovery and idempotent enqueue.
- `profile_router.py`: deterministic eligibility/preview, explicit allowlist;
  no automatic account rotation or workspace membership mutation.
- `profile_activation.py`: existing profile locks and keyring authentication,
  identity refresh, context-revision checks, safe bind/start and rollback.
- `desktop_binding.py`: exactly one scoped root, PID/create-time/command checks,
  matching CODEX_HOME and Electron user-data environment, best-effort focus.
  This verifies launcher/process binding plus an independent official account
  read, not the internal account label of an uninstrumented Desktop window.
- `activation_ui.py`: queued starts, status, cancel/resume and recovery callbacks.
- `workspace_provider.py` and `workspace_ui.py`: explicit read-only member
  directory check, strict pagination and redacted failures in Diagnostics.

## Workspace directory

The adapter uses only the documented GET endpoint
`https://api.chatgpt.com/v1/manage/workspaces/{workspace_id}/users` with `limit`
and `after`, as demonstrated in OpenAI's official cookbook. A workspace-scoped
Admin key with appropriate read permission is required. API Platform keys are
not interchangeable. Workspace availability must be checked in Admin Console;
Business eligibility is not assumed.

The masked key is cleared from the input on submission, retained only by the
in-flight request, and never written to settings, history, logs or child-process
environments. It must be supplied again for a later directory read. A read
error keeps the previous visible directory with a stale warning; no missing
member, role, seat, or removal is inferred from an incomplete response.

This is visibility, not an administrator permission grant. Directory user IDs
are not equated to Codex account IDs. Roles/seats are not guessed. There is no
automatic email-based membership mapping and no invite/remove/role/seat write.
The public reference linked an OpenAPI document that returned 404 during this
session; mutation schemas could not be verified and are intentionally not
invented. Existing `prepare_removal`/access-event persistence remains available
for a separately verified management integration.

## Research and dependency choices

Consulted 2026-11-14:
- https://help.openai.com/en/articles/20001407-managing-admin-keys-in-admin-console
- https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/src/admin-api.mjs
  (observed blob `5673e5266c2ecde73733e15679035d9fa25c2a76`)
- https://chatgpt.com/public/admin/api-reference
- https://chatgpt.com/public/admin/openapi.json (404, no writable contract obtained)
- https://github.com/pytransitions/transitions
- https://github.com/ragardner/tksheet
- https://github.com/pywinauto/pywinauto/issues/270
- https://github.com/TomSchimansky/CustomTkinter/issues/2810

Retain CustomTkinter, ttk, SQLite and the existing worker/lock infrastructure.
`transitions` does not replace durable transactional journaling; no dependency
is needed for the small explicit state graph. `tksheet` is useful for editable
spreadsheets but these read-only lists fit existing ttk controls. Avoid title-
based desktop automation and foreground-lock workarounds; focus denial is an
explicit nonfatal result. No new runtime dependency or dependency-lock change.

## Remaining acceptance

Production Windows/PID/foreground/ACL/Keyring/OAuth behavior, full original
repository Python/Node suites, complete CustomTkinter shell, six-screen redesign,
Figma edits and installer acceptance remain open. No administrative account,
member, billing or mail action was performed. No claim of full spec completion.
