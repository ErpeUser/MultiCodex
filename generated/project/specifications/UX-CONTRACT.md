# MultiCodex interaction contract - 0.2.0-dev

Implemented code is distinguished from executed native acceptance in generated/project/docs/verification.md.

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


## Responsive and focus acceptance (15 November 2026)

The shell and native views use semantic tokens for spacing and state. At compact content widths, action controls and activation forms stack to one column; quota metrics reflow from three to two to one columns, and long German copy wraps to the measured widget width. The selected row, query, sort order and keyboard focus must survive data refreshes.

Focus is visible in both themes. Return and Space invoke the focused action, Ctrl+R refreshes, Ctrl+F focuses table search and Escape requests login cancellation. Unknown, cached, removed and disabled states always include text and do not become a zero or a color-only badge. Release acceptance still requires native Windows 11 checks at 900x640 and 1180x760 with 100/125/150/200% DPI, dark/light themes and keyboard-only navigation.
