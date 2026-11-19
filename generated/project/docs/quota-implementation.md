# Persistent quota history: implemented development slice

Base: `bd532520a29e0848676e2b864c0fd7a6b4a5d510`, public `ErpeUser/MultiCodex`, `main`.
The initial patch was published on `feature/quota-history-monitoring-20261114`.
This document includes the subsequent activation/directory extension; it is not a
release or the complete requested product. No production account was changed.

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
not modify existing profile metadata. The SQLite database uses schema version 2.
Existing version-1 databases with the required tables have their version marker
advanced to 2; added JSON fields have backward-compatible defaults. Snapshot
payloads retain their separate schema version 1. Unsupported database versions
fail closed instead of being silently reset. Rows and snapshots are validated on
read as well as write. Backups use SQLite's consistent backup API and replace the
backup only after integrity checks. There is no automatic destructive restore or
history pruning; the supported version-1-to-2 marker update is the only automatic
database migration.

Snapshots retain source, identity/context, plan/seat where known, actual window
durations, used percentages, reset timestamps, observation time and capture
reason. An explicit absent window differs from an unknown/malformed window.
History is append-only; an access event does not delete or zero old usage.
Context revisions prevent a response started before a known access/plan change
from overwriting the new context. Older observations cannot replace newer plan
metadata. Identity evidence from the provider is pinned without inventing a
workspace identifier or conflating account ID with workspace ID.

Observation and reset timestamps use UTC epoch seconds; display uses the operating
system's local timezone. The internal `captured_at` ordering field uses epoch
nanoseconds. At a reset boundary the UI retains the last measured consumption
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

A quota-monitor tick makes at most one provider observation. An explicitly
queued profile start additionally performs preflight and post-start checks. The host's existing worker
queue serializes quota work; per-profile and per-account OS locks avoid races
with login/switch and another manager process. Retries are bounded and persist
across manager restart. Authentication mismatches suspend polling. Explicit
manual refresh can retry after repair; it cannot re-enable removed access.

The backend can record known access events and enforce a stored snapshot before
an authorized removal via `prepare_removal`. **A read-only directory adapter is now available**, but it does not automatically map members to saved logins;
these remain prerequisites for separately verified membership management. A generic network/authentication failure is not proof of removal.
Automatic detection of every external membership change and GUI access-state
editing are not implemented. An authorized adapter must supply that evidence.

## Remaining requested scope

| Requirement | Actual status |
|---|---|
| Durable quota history/offline reset evaluation | Implemented, fixture-tested |
| Bounded monitoring of saved managed logins | Implemented, fixture-tested |
| Entire installed app integration | Source-wired; full app runtime unverified |
| Explicit exact-account profile starts/router | Implemented with durable queue; native Windows acceptance open |
| Persistent multi-step profile activation state machine | Implemented; recovery and CAS tested |
| Members/invites/roles/seats/SCIM execution | Directory GET adapter only; no mutations or SCIM writes |
| Account/workspace/role discovery beyond provider evidence | Unknown remains unknown |
| Outlook | Not added; deliberately optional |
| OS notifications | Not added; current status is shown in the UI |
| Full six-screen redesign | Partial: quota widgets plus host integration only |
| Figma update/editable frames | Installed integration has no callable action here |
| Existing account list search/filter | New quota account table only, not old Accounts page |
| Full native Windows/DPI/OAuth/installer acceptance | Not performed |
| Full original repository Python/Node regression suites | Not performed in this partial checkout |
| Git commit/push/new CI | Feature branch published; see continuation verification and GitHub status |

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

See [profile activation](profile-activation.md) and [continuation verification](continuation-verification.md) for the added development slice.
