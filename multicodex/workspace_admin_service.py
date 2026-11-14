"""Worker-only administration facade. Keys are arguments, never service state.

The public contract controls capabilities; the coordinator controls authorization,
quota snapshots and readback. No operation is scheduled by a quota event.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import time
from .workspace_admin_api import AdminAPI, AdminAPIError, fetch_contract, _identifier
from .workspace_operations import WorkspaceOperations, OperationError

REQUIRES = {
    'create_invite': {'create_invite', 'list_users', 'list_invites'},
    'resend_invite': {'resend_invite', 'list_users', 'list_invites', 'get_invite'},
    'cancel_invite': {'cancel_invite', 'list_users', 'list_invites', 'get_invite'},
    'update_user': {'update_user', 'list_users', 'get_user'},
    'remove_user': {'remove_user', 'list_users', 'get_user'},
}


class WorkspaceAdminService:
    def __init__(self, root, quota, *, contract_loader=fetch_contract,
                 api_factory=AdminAPI, clock=time.time, cancel=None):
        self.root = Path(root)
        self.quota = quota
        self.contract_loader = contract_loader
        self.api_factory = api_factory
        self.clock = clock
        self.cancel = cancel
        self.workspace = None
        self.api = None
        self.directory = {'members': [], 'invitations': [], 'observed_at': None}

    def _check(self, workspace=None):
        if self.cancel is not None and self.cancel.is_set():
            raise OperationError('PROVIDER_UNAVAILABLE')
        if workspace is not None and (self.workspace != workspace or self.api is None):
            raise OperationError('ACCOUNT_MISMATCH')

    def _operations(self):
        return WorkspaceOperations(self.root, self.api, self.quota, clock=self.clock)

    def history(self):
        return self._operations().list()

    def capabilities(self):
        if self.api is None:
            return {}
        contract = self.api.contract
        result = {}
        for action, requires in REQUIRES.items():
            missing = sorted(requires - set(contract.operations))
            roles = seats = ()
            reason = 'CONTRACT_MISSING' if missing else None
            if not missing and action in {'create_invite', 'update_user'}:
                try:
                    roles = contract.choices(action, 'role')
                    seats = contract.choices(action, 'seat_type')
                except AdminAPIError:
                    reason = 'UNSUPPORTED_SCHEMA'
                if action == 'update_user' and not roles and not seats:
                    reason = 'UNSUPPORTED_SCHEMA'
            result[action] = {'enabled': reason is None, 'reason': reason,
                              'missing': missing, 'roles': roles, 'seats': seats}
        return result

    def _model(self, selected=None):
        accounts = [{'account_key': r['account_key'], 'email': r['email'],
                     'profile_id': r['profile_id'], 'workspace_id': r['workspace_id']}
                    for r in self.quota.accounts()]
        return {'workspace_id': self.workspace,
                'contract_version': self.api.contract.version if self.api else None,
                'capabilities': self.capabilities(), 'records': self.history(),
                'quota_accounts': accounts, 'selected': selected, **deepcopy(self.directory)}

    def view(self):
        """Read local journal and quota metadata without network access."""
        return self._model()

    def connect(self, workspace_id, key):
        self._check()
        _identifier(workspace_id)
        # A failed reconnect cannot leave old write capabilities usable.
        self.workspace = None
        self.api = None
        api = self.api_factory(self.contract_loader())
        ops = WorkspaceOperations(self.root, api, self.quota, clock=self.clock)
        members = list(ops._all('list_users', workspace_id, key).values())
        invites = (list(ops._all('list_invites', workspace_id, key).values())
                   if 'list_invites' in api.contract.operations else [])
        self._check()
        self.workspace, self.api = workspace_id, api
        self.directory = {'members': members, 'invitations': invites,
                          'observed_at': int(self.clock())}
        return self._model()

    def prepare(self, action, workspace_id, key, *, target=None, body=None, account_key=None):
        self._check(workspace_id)
        if not self.capabilities().get(action, {}).get('enabled'):
            raise OperationError('PROVIDER_UNAVAILABLE')
        row = self._operations().prepare(action, workspace_id, key, target=target,
                                         body=body, account_key=account_key)
        return self._model(row)

    def execute(self, identity, digest, key):
        ops = self._operations()
        row = ops.get(identity)
        self._check(row['review']['workspace_id'])
        if row['digest'] != digest or row['state'] not in {'REVIEW_REQUIRED', 'READY'}:
            raise OperationError('REVIEW_REQUIRED')
        # Refresh public schemas before a write, without sending a credential.
        self.api = self.api_factory(self.contract_loader())
        self._check(row['review']['workspace_id'])
        ops = self._operations()
        if row['state'] == 'REVIEW_REQUIRED':
            ops.approve(identity, digest)
        result = ops.execute(identity, key)
        self.directory['observed_at'] = None
        return self._model(result)

    def action(self, identity, action, key=None):
        self._check()
        ops = self._operations()
        row = ops.get(identity)
        if action == 'cancel':
            result = ops.cancel(identity)
        elif action == 'recover':
            result = ops.recover(identity)
        elif action == 'reconcile':
            self._check(row['review']['workspace_id'])
            result = ops.reconcile(identity, key)
        else:
            raise OperationError()
        return self._model(result)
