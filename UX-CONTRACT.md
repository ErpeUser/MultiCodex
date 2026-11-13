# MultiCodex interaction contract - 0.2.0-dev

Implemented code is distinguished from executed native acceptance in docs/verification.md.

| Action | Pending state | Commit point | Failure behavior |
|---|---|---|---|
| Create profile | Bounded worker; duplicate mutation disabled | Atomic metadata creation under catalogue lock | No overwrite; partial data preserved and reported |
| Link existing profile | Explicit source-path confirmation | Metadata-only external reference | Original files never copied/moved; invalid/duplicate targets rejected |
| Launch | Worker checks supported executable and scoped process | Scoped root observed | Timeout or unsafe state is an error, not success |
| Stop | Unsaved-work confirmation; graceful close | Actual owned tree exits | No automatic force-kill; unknown visibility blocks guessing |
| Force stop | Separate diagnostic action and explicit warning | Only verified selected tree is stopped | No name-wide termination |
| Switch saved login | Restart confirmation; per-profile lock | Journaled stop / auth-home binding / launch | Old binding restored, or journal retained for explicit recovery |
| Add login / Re-Login | Official browser; cancellable before cutover | Persisted identity read by fresh server; selected profile restarts | Cancel/wrong identity does not replace active credentials; saved homes retained |
| Rename saved login | Worker and profile lock | Metadata label update | No token or provider account mutation |
| Recover | Explicit restart warning | Old binding and prior running state restored | Failure leaves journal; never delete credentials |
| Usage | Worker queries official app-server for selected home | Sanitized numeric windows | Unknown is not 0%; no raw provider JSON |
| Upstream pool | Read-only worker | Redacted known-v3 metadata | Not imported, not globally switched, not called healthy |
| Theme | Atomic persisted setting, then Tk-thread rebuild | New appearance visible | Corrupt settings retained; no silent overwrite |
| Close manager | Cancel login request, wait bounded operations | Workers drained, callbacks cancelled, animation stopped | Desktop instances remain open |

All widget changes occur on the Tk thread. Rendering consumes cached snapshots only. Refresh uses one process scan for all profiles. Keyboard Return/Space activate buttons; Ctrl+R refreshes; Escape requests login cancellation.

Only an operation's confirmed backend result may report completion. A running process and local identity metadata do not prove the desktop's live account or quota. Figma sample records are not application data.

Open release requirements: safe existing-pool credential adoption, real Windows GUI/DPI/keyboard validation, real OAuth and multi-window identity validation, complete dependency locks, installer acceptance and private GitHub publication.
