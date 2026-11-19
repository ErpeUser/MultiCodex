# Reviewed workspace operations

`WorkspaceOperations` adds a persistent SQLite operation journal to the
schema-gated Admin client. It is independent of quota-monitor triggers.

1. Prepare an exact workspace/action/target/payload with a temporary key.
2. Inspect members/invitations using complete, bounded pages. SCIM-managed,
   protected and unverifiable members are not changed; the last owner is protected.
3. Bind removals and seat changes to a matching local quota record with an existing
   snapshot. Unknown workspace scope is retained, never silently relabelled.
4. Review the returned operation and approve its digest. Approval binds the full
   API contract fingerprint and before-state and expires after five minutes.
5. Execute once. A lock held by the operating system for each workspace excludes
   competing local execution and recovery until the active call finishes. The
   journal lease and atomic state claim remain additional safeguards.
6. Verify the resulting directory state. Invitations await acceptance; resend
   acknowledges a server request, not email delivery. No onboarding is automated.

Changed preconditions invalidate the review. An ambiguous write is never replayed;
`reconcile` performs reads only. After a crashed operation, `recover` requires the
execution lock to be free and the five-minute lease to expire. It enables readback,
not another mutation. Cancel is allowed before execution. Keys and raw provider
responses are not persisted.

Confirmed removals retain all quota values. Known matching quota contexts are
marked removed; unrelated or unknown contexts are not. A seat/role update makes
that context require verification again. Local synchronization errors are separate
from remote write outcomes.

Capability availability is conditional on the current official contract and the
workspace's entitlement. The client does not grant owner/admin permissions. No
real account, seat, invitation, membership or billing action was executed here.

Verification: 60 new API/coordinator tests passed against real SQLite and quota
storage with a synthetic HTTP provider. RED/GREEN tests additionally caught missing
contract binding, expired-review reuse, read-only fields and account-key validation.
Original-repository/native Windows acceptance is separate; see the implementation
report rather than interpreting these fixture tests as a production API test.
