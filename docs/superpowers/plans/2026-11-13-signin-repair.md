# Sign-in repair implementation plan

Goal: make the existing official browser sign-in discoverable, recoverable and cancellable, correct misleading activity, and update the installed Windows executable. The user explicitly requested direct implementation.

Architecture: retain Tk, the bounded worker queue, official app-server authentication and keyring-only storage. Pass browser state to Tk through an in-memory queue; keep OAuth URLs out of files and logs. Browser activation runs in a bounded daemon helper holding no Tk references. No global account switching or source-session copying.

Approaches: changing only the idle progress value would leave failed browser activation opaque; replacing authentication would violate the existing security contract. Repair the current GUI/auth boundary and retain the official client.

- [x] Reproduce idle activity, missing entry point, failed-browser recovery and unresponsive-request cancellation with failing native/transport tests.
- [x] Add the persistent Anmelden entry, explicit browser-wait/reopen state, cancellable requests and hidden idle activity. Ignore stale sign-in events and preserve previous assignments.
- [x] Run full Python/Node tests, native GUI probes and an official-client start/cancel probe without signing into test accounts; review the change.
- [x] Build 0.2.1-dev, check the packaged application, preserve existing program rollback and profile hashes, upgrade the exact installed application and verify its new executable/runtime/GUI. Keep release acceptance blocked.

Review focus: late browser results after cancellation; browser launch exceptions/stalls; background refresh vs foreground activity; encrypted credential policy; preserving existing profile data during upgrade.
