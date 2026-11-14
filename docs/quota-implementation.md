# Persistent quota history: implemented development slice

Base: `bd532520a29e0848676e2b864c0fd7a6b4a5d510`, private `ErpeUser/MultiCodex`, `main`.
This is a locally tested patch, not a published release or the complete requested
workspace/profile automation product. No remote file, commit or account changed.

## Implemented

- `quota_store.py`: versioned SQLite history, account/context records, access
  events, persistent poll schedules, validated reads/writes and explicit backup.
- `quota.py`: pure interpretation of real window durations, freshness, historical
  reset boundaries, provider permission and denied usage. No synthesized reset.
- `quota_provider.py`: subclass of the existing official client; read identity,
  read rate limits, read identity again, then allowlist non-secret values.
- `quota_monitor.py`: one bounded observation per worker tick, profile/key locks,
  cancellation, persisted interval/backoff/retry suspension and manual refresh.
- `automation_settings.py`: separate validated preferences, preserving theme
  settings. Monitoring is initially off; permitted profiles must be selected.
- `quota_service.py`: worker-only integration with real ProfileStore/SessionStore.
- `quota_view.py`, `quota_ui.py`, `quota_gui.py`: German dark/light quota table,
  search/filter/sort, selected-record details, reset labels, paginated history,
  monitoring controls, diagnostics and backup action.
- `gui.py`: connects these components to Usage, Settings, Overview and Diagnostics.
  Existing login, cancellation, GC/thread and process actions are preserved.

## Storage and reset semantics

The application's data root gets `quota-history/quota.sqlite3`; credentials stay
in their existing official keyring/authentication homes. The new database does
not modify existing profile metadata. Schema version 1 is accepted; future or
corrupt schemas fail closed instead of being silently rewritten. Rows and
snapshots are validated on read as well as write. Backups use SQLite's consistent
backup API and replace the backup only after integrity checks. There is no
automatic destructive restore, history pruning or cross-version migration.

Snapshots retain source, identity/context, plan/seat where known, actual window
durations, used percentages, reset timestamps, observation time and capture
reason. An explicit absent window differs from an unknown/malformed window.
History is append-only; an access event does not delete or zero old usage.
Context revisions prevent a response started before a known access/plan change
from overwriting the new context. Older observations cannot replace newer plan
metadata. Identity evidence from the provider is pinned without inventing a
workspace identifier or conflating account ID with workspace ID.

All stored timestamps are UTC epoch seconds; display uses the operating system's
local timezone. At a reset boundary the UI retains the last measured consumption
and reports that new capacity is unconfirmed. It never adds five hours/seven days
to removal time or repeatedly rolls a deadline forward without new evidence.

A fresh successful response is not automatically authorization. In the current
protocol, `ordinaryUsageAllowed` must be explicitly true before this evaluator
confirms capacity; missing permission stays verification-required. Exhaustion,
spend controls, changed context, an additional unresolved bucket, authentication
failure or removed access prevents capacity confirmation. Older CLI versions
can still supply visible measurements without being declared available.

## Monitoring and account scope

Monitoring uses saved managed profile sessions, including inactive saved login
slots, without activating them. The global multi-auth pool is not imported and
linked legacy profiles retain the old manual Usage path. Deleted or unavailable
local bindings retain existing history but cannot be probed automatically.

A worker tick makes at most one provider observation. The host's existing worker
queue serializes quota work; per-profile and per-account OS locks avoid races
with login/switch and another manager process. Retries are bounded and persist
across manager restart. Authentication mismatches suspend polling. Explicit
manual refresh can retry after repair; it cannot re-enable removed access.

The backend can record known access events and enforce a stored snapshot before
an authorized removal via `prepare_removal`. **No workspace API is connected**,
so these are prerequisites for future integration, not executed membership
management. A generic network/authentication failure is not proof of removal.
Automatic detection of every external membership change and GUI access-state
editing are not implemented. An authorized adapter must supply that evidence.

## Remaining requested scope

| Requirement | Actual status |
|---|---|
| Durable quota history/offline reset evaluation | Implemented, fixture-tested |
| Bounded monitoring of saved managed logins | Implemented, fixture-tested |
| Entire installed app integration | Source-wired; full app runtime unverified |
| Automatic profile activation/router | Not implemented; setting rejects activation |
| Persistent multi-step profile activation state machine | Not implemented |
| Members/invites/roles/seats/SCIM execution | No configured verified adapter; no actions |
| Account/workspace/role discovery beyond provider evidence | Unknown remains unknown |
| Outlook | Not added; deliberately optional |
| OS notifications | Not added; current status is shown in the UI |
| Full six-screen redesign | Partial: quota widgets plus host integration only |
| Figma update/editable frames | Installed integration has no callable action here |
| Existing account list search/filter | New quota account table only, not old Accounts page |
| Full native Windows/DPI/OAuth/installer acceptance | Not performed |
| Full original repository Python/Node regression suites | Not performed in this partial checkout |
| Git commit/push/new CI | Not performed; connector exposes reads only |

The local history is not encrypted; it contains account metadata but no intended
credentials. OS user permissions still matter. Unknown workspace data cannot be
used to infer authorization. History growth is unbounded until an explicit,
reviewed retention/export feature exists. No independent code review occurred.

## Protocol sources consulted

- https://learn.chatgpt.com/docs/app-server
- https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/schema/typescript/v2/GetAccountRateLimitsResponse.ts
  (observed blob `73762064eb9dedb5a0b4e8e55cd46c37c8a83c2b`)
- https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/schema/typescript/v2/RateLimitSnapshot.ts
  (observed blob `4740f38da0089b8d8a0070c0bb5792714eab71bc`)

These source contracts do not prove compatibility with the user's installed CLI;
that integration must be exercised during native acceptance.
