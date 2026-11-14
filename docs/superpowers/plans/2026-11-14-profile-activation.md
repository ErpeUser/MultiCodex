# Profile activation and workspace visibility implementation plan

Goal: extend the existing quota branch without rebuilding quota storage.
Architecture: explicit per-account start requests, durable run journal, existing
profile locks and keyring sessions; no automatic account rotation. Workspace
membership is independently read through the documented ChatGPT Admin API.
Spec: the user's 2026-11-14 MultiCodex brief; newer branch instruction supersedes main.
Base: 4e85660da8e6e4fd95ee52aaa4b6a3e783ded072.

## Global constraints
- Keep existing credentials, open instances, quota history and private repository.
- No network/process calls on Tk; no widget calls from workers.
- Never infer membership from login, quota percentage or an expired timer.
- All production writes require verified API contracts; do not invent endpoints.
- Only push this feature branch, no main merge, tag or release.

## Tasks
1. Test durable activation runs, state transitions, corruption/locking and duplicate
   requests; implement automation_state.py. Expected: RED then green unit tests.
2. Test explicit candidate routing and idle-only activation using real temporary
   profile/session stores and simulated external providers/processes. Implement
   profile_router.py and profile_activation.py with crash-safe bind/restore.
3. Test production process verification/focus adapter and refusal of PID reuse,
   ambiguous roots, mismatched CODEX_HOME and inaccessible processes.
4. Test official directory pagination, identity matching, redacted failures and
   no removal inference after partial reads. Implement workspace_provider.py.
5. Integrate queue/settings/history and workspace status in existing worker GUI.
   Test widgets under Xvfb and screenshot both themes.
6. Re-run all locally available suites, compile, review diff and push by an
   expected-SHA Git ref update. Record unexecuted native tests and CI billing block.

## Review focus
- A session re-login after enqueue must not silently change the selected identity.
- A crash after binding must not spawn another process or delete credentials.
- Unknown membership/seat data cannot be silently changed into admin authorization.
- An unreachable directory page cannot mark omitted users removed.
- A focus attempt must not activate a recycled PID or send input to another app.
