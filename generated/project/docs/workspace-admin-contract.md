# Workspace Admin API adapter

This is a client capability, not a grant of administrative permission and not a
quota-rotation mechanism. No live workspace write was performed during development.

## Contract and scope

`workspace_admin_api.fetch_contract()` reads the public JSON contract at
https://chatgpt.com/public/admin/api-reference/openapi.json without credentials.
Only the fixed `https://api.chatgpt.com/v1` server is accepted. Operations are
restricted to workspace users and invitations actually present in that contract:
list/retrieve, invite/resend/cancel, update member and remove membership.
Missing routes stay unavailable. A Compliance API or Platform organization route
cannot be used as a substitute.

Official sources checked on 2026-11-14:
- https://help.openai.com/en/articles/10128477-chatgpt-enterprise-and-edu-release-notes
  (August 20 entry: invitation and member administration APIs).
- https://help.openai.com/en/articles/20001407-managing-admin-keys-in-admin-console
- https://chatgpt.com/public/admin/api-reference

The retrieved JSON was an older 2.5.6 snapshot without the announced mutation
routes. Therefore no current mutation payload or Business eligibility is claimed.
At runtime the current published contract is authoritative; unsupported or absent
schemas disable operations. Roles/seat values come from the contract, not UI labels.
SCIM-managed memberships must remain managed through the identity provider.

## Safeguards

- No API key is stored in the client, settings or history.
- Every mutation requires `allow_write=True` for that call. The higher-level
  operator must review and approve its exact account, workspace and payload.
- Fixed HTTPS origin, redirects refused, bounded responses, validated identifiers,
  query/body schemas and response codes. Only local schema references are resolved.
- Unsupported validation constraints fail closed rather than being ignored.
- Transport failure or invalid success response after a write has an unknown
  outcome. Do not retry automatically: reconcile through a fresh read first.
- No mutation is connected to a quota warning or reset timer.

The client alone does not enforce last-owner checks, snapshot-before-removal,
SCIM policy, approvals, or readback reconciliation. Those belong to the operation
coordinator and the provider, and are required before enabling writes in the UI.

## Verification

24 new contract/transport-boundary tests passed locally. Fixtures explicitly use
synthetic endpoints and do not assert real provider support. The test was first
run against the absent module (RED), then against the implementation (GREEN).
The complete locally present suite was attempted: 98 tests, 12 import errors
because this environment initially contains an older partial overlay without
original profile/session/lock modules. That run is not a passed repository suite.
No native Windows, real Admin key, membership or billing operation was tested.
