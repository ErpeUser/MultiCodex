"""Reviewed, persistent workspace mutations, independent of quota routing.

The operation journal contains only allowlisted metadata. An ambiguous write is
read back, never replayed. Actual permission/last-owner enforcement also remains
with the provider; a locally reviewed request does not grant server privileges.
"""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from .locks import BusyError, FileLock
from .workspace_admin_api import AdminAPIError, _identifier
from .quota_store import QuotaError, _safe_path

ACTIONS = frozenset({'create_invite', 'resend_invite', 'cancel_invite', 'update_user', 'remove_user'})
STATES = frozenset({'REVIEW_REQUIRED','READY','EXECUTING','VERIFYING','VERIFIED',
    'OUTCOME_UNKNOWN','AWAITING_ACCEPTANCE','REQUEST_ACCEPTED','FAILED','EXPIRED',
    'CANCELLED','LOCAL_SYNC_REQUIRED'})
TERMINAL = frozenset({'VERIFIED','FAILED','EXPIRED','CANCELLED'})
OWNER = frozenset({'account-owner','owner'})


class OperationError(RuntimeError):
    def __init__(self, code='INVALID_REQUEST'):
        allowed = {'INVALID_REQUEST','STORAGE','BUSY','NOT_FOUND','REVIEW_REQUIRED',
            'EXPIRED','SNAPSHOT_REQUIRED','ACCOUNT_MISMATCH','SCIM_MANAGED',
            'MANAGEMENT_UNKNOWN','LAST_OWNER','ALREADY_MEMBER','INVITATION_EXISTS',
            'PROTECTED_MEMBER','OUTCOME_UNKNOWN','PROVIDER_UNAVAILABLE'}
        self.code = code if code in allowed else 'PROVIDER_UNAVAILABLE'
        super().__init__('Workspace operation: ' + self.code)


def _dump(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def _digest(value):
    return hashlib.sha256(_dump(value).encode()).hexdigest()


def _payload(action, value):
    if action not in ACTIONS:
        raise OperationError()
    if action not in {'update_user','create_invite'}:
        if value is not None:
            raise OperationError()
        return None
    allowed = {'role','seat_type'} | ({'email'} if action == 'create_invite' else set())
    if not isinstance(value, dict) or not value or set(value) - allowed:
        raise OperationError()
    for v in value.values():
        if not isinstance(v, str) or not v or len(v) > 320 or re.search(r'[\x00-\x1f\x7f]', v):
            raise OperationError()
    if action == 'create_invite' and ('email' not in value or re.fullmatch(r'[^\s@]+@[^\s@]+',value['email']) is None):
        raise OperationError()
    return copy.deepcopy(value)


def _member(row):
    if not isinstance(row, dict):
        raise OperationError('PROVIDER_UNAVAILABLE')
    try:
        ident = _identifier(row.get('id'))
    except AdminAPIError:
        raise OperationError('PROVIDER_UNAVAILABLE') from None
    out = {'id': ident}
    for field in ('email','role','seat_type','status'):
        value = row.get(field)
        if value is not None and (not isinstance(value, str) or len(value)>320 or re.search(r'[\x00-\x1f\x7f]',value)):
            raise OperationError('PROVIDER_UNAVAILABLE')
        out[field] = value
    provider_account_id = row.get('account_id')
    if provider_account_id is not None:
        try:
            provider_account_id = _identifier(provider_account_id)
        except AdminAPIError:
            raise OperationError('PROVIDER_UNAVAILABLE') from None
    out['account_id'] = provider_account_id
    scim = row.get('is_scim_managed')
    if scim is not None and type(scim) is not bool:
        raise OperationError('PROVIDER_UNAVAILABLE')
    out['is_scim_managed'] = scim
    return out


class WorkspaceOperations:
    def __init__(self, root, api, quota, *, clock=time.time, protected_ids=()):
        self.root = Path(root).absolute()
        self.path = self.root/'workspace-operations.sqlite3'
        self.api, self.quota, self.clock = api, quota, clock
        self.protected_ids = frozenset(protected_ids)
        try:
            _safe_path(self.root)
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._check_path()
            try:
                fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
                os.close(fd)
            except FileExistsError:
                pass
            with self._db() as db:
                version=db.execute('PRAGMA user_version').fetchone()[0]
                if version==0:
                    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():raise OperationError('STORAGE')
                    db.execute('CREATE TABLE operations(id TEXT PRIMARY KEY,workspace TEXT NOT NULL,request_key TEXT NOT NULL,state TEXT NOT NULL,record TEXT NOT NULL)')
                    db.execute('CREATE TABLE leases(workspace TEXT PRIMARY KEY,owner TEXT NOT NULL,expires INTEGER NOT NULL)')
                    db.execute('CREATE INDEX operation_request ON operations(request_key,state)')
                    db.execute('PRAGMA user_version=1')
                elif version!=1:
                    raise OperationError('STORAGE')
        except (OSError, sqlite3.Error, QuotaError):
            raise OperationError('STORAGE') from None

    def _check_path(self):
        for suffix in ('','-journal','-wal','-shm'):
            _safe_path(Path(str(self.path)+suffix))

    @contextmanager
    def _db(self):
        db=None
        try:
            self._check_path()
            db=sqlite3.connect(self.path,timeout=5,isolation_level=None)
            db.execute('PRAGMA trusted_schema=OFF')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except (sqlite3.Error,OSError,ValueError,QuotaError):
            if db is not None:db.rollback()
            raise OperationError('STORAGE') from None
        except BaseException:
            if db is not None:db.rollback()
            raise
        finally:
            if db is not None:db.close()

    def _load(self, db, identity):
        if not isinstance(identity,str) or re.fullmatch('[0-9a-f]{32}',identity) is None:raise OperationError()
        row=db.execute('SELECT record,state FROM operations WHERE id=?',(identity,)).fetchone()
        if row is None:raise OperationError('NOT_FOUND')
        if len(row[0])>32768:raise OperationError('STORAGE')
        data=json.loads(row[0])
        if (not isinstance(data,dict) or data.get('operation_id')!=identity or
            data.get('state')!=row[1] or row[1] not in STATES):raise OperationError('STORAGE')
        if data.get('digest')!=_digest(data.get('review')):raise OperationError('STORAGE')
        return data

    def _save(self, db, data):
        db.execute('UPDATE operations SET state=?,record=? WHERE id=?',
            (data['state'],_dump(data),data['operation_id']))

    def get(self, identity):
        with self._db() as db:return self._load(db,identity)

    def list(self):
        with self._db() as db:
            return [self._load(db,row[0]) for row in db.execute('SELECT id FROM operations ORDER BY rowid DESC LIMIT 500')]

    def _state(self, identity, state, **fields):
        with self._db() as db:
            row=self._load(db,identity)
            row.update(fields,state=state,updated_at=int(self.clock()))
            self._save(db,row)
            return row

    @contextmanager
    def _execution_lock(self, workspace):
        # Lease expiry does not prove that its original executor has stopped.
        token=hashlib.sha256(workspace.encode('utf-8')).hexdigest()
        try:
            with FileLock(self.root/'.locks'/('workspace-'+token+'.lock')):
                yield
        except BusyError:
            raise OperationError('BUSY') from None

    def _all(self, operation, workspace, key):
        rows={};query={};deadline=time.monotonic()+60
        for _ in range(50):
            if time.monotonic()>deadline:raise OperationError('PROVIDER_UNAVAILABLE')
            page=self.api.call(operation,workspace,key,query=query)
            if (not isinstance(page,dict) or page.get('object')!='list' or
                not isinstance(page.get('data'),list) or type(page.get('has_more')) is not bool or
                len(page['data'])>1000):raise OperationError('PROVIDER_UNAVAILABLE')
            batch=page['data']
            for raw in batch:
                row=_member(raw)
                if row['id'] in rows or len(rows)>=10000:raise OperationError('PROVIDER_UNAVAILABLE')
                rows[row['id']]=row
            if (page.get('first_id')!=(batch[0]['id'] if batch else None) or
                page.get('last_id')!=(batch[-1]['id'] if batch else None)):
                raise OperationError('PROVIDER_UNAVAILABLE')
            if not page['has_more']:return rows
            if not batch or page['last_id']==query.get('after'):raise OperationError('PROVIDER_UNAVAILABLE')
            query={'after':page['last_id']}
        raise OperationError('PROVIDER_UNAVAILABLE')

    def _inspect(self, action, workspace, target, body, key):
        members=self._all('list_users',workspace,key)
        if action in {'update_user','remove_user'}:
            if target in self.protected_ids:raise OperationError('PROTECTED_MEMBER')
            if target not in members:raise OperationError('NOT_FOUND')
            member=_member(self.api.call('get_user',workspace,key,target=target))
            if member['id']!=target or member!=members[target]:raise OperationError('PROVIDER_UNAVAILABLE')
            if member['is_scim_managed'] is True:raise OperationError('SCIM_MANAGED')
            if member['is_scim_managed'] is not False:raise OperationError('MANAGEMENT_UNKNOWN')
            if not member['role']:raise OperationError('MANAGEMENT_UNKNOWN')
            owners=sorted(row['id'] for row in members.values() if row['role'] in OWNER)
            demotion=action=='remove_user' or ('role' in body and body['role'] not in OWNER)
            if member['role'] in OWNER and demotion and len(owners)<=1:raise OperationError('LAST_OWNER')
            return {'target':member,'owners':owners}
        invitations=self._all('list_invites',workspace,key)
        if action=='create_invite':
            email=body['email'].casefold()
            if any((r['email'] or '').casefold()==email for r in members.values()):raise OperationError('ALREADY_MEMBER')
            if any((r['email'] or '').casefold()==email for r in invitations.values()):raise OperationError('INVITATION_EXISTS')
            return {'email':email,'absent':True}
        if target not in invitations:raise OperationError('NOT_FOUND')
        invitation=_member(self.api.call('get_invite',workspace,key,target=target))
        if invitation['id']!=target or invitation!=invitations[target]:raise OperationError('PROVIDER_UNAVAILABLE')
        return {'target':invitation}

    def _snapshot(self, action, workspace, body, preflight, account_key):
        required=(action=='remove_user' or
                  action=='update_user' and bool({'seat_type', 'role'} & set(body or {})))
        if not required:return None
        if account_key is None:raise OperationError('SNAPSHOT_REQUIRED')
        try:
            account=self.quota.account(account_key)
            member=preflight['target']
            if (not member['email'] or account['email'].casefold()!=member['email'].casefold() or
                account['workspace_id'] not in (None,workspace) or
                (member.get('account_id') is not None and account.get('account_id') is not None and
                 member['account_id'] != account['account_id'])):
                raise OperationError('ACCOUNT_MISMATCH')
            return self.quota.prepare_removal(account_key)['snapshot_id']
        except QuotaError:
            raise OperationError('SNAPSHOT_REQUIRED') from None

    def prepare(self, action, workspace_id, key, *, target=None, body=None, account_key=None):
        body=_payload(action,body)
        if account_key is not None and (not isinstance(account_key,str) or re.fullmatch('[0-9a-f]{64}',account_key) is None):
            raise OperationError()
        try:
            self.api.contract.request(action,workspace_id,target=target,body=body)
            preflight=self._inspect(action,workspace_id,target,body,key)
            snapshot=self._snapshot(action,workspace_id,body,preflight,account_key)
        except AdminAPIError:
            raise OperationError('PROVIDER_UNAVAILABLE') from None
        now=int(self.clock())
        review={'action':action,'workspace_id':workspace_id,'target':target,'body':body,
                'account_key':account_key,'preflight':preflight,'snapshot_id':snapshot,
                'contract_version':self.api.contract.version,'contract_fingerprint':self.api.contract.fingerprint}
        fingerprint=_digest({k:review[k] for k in ('action','workspace_id','target','body','account_key')})
        with self._db() as db:
            for old in db.execute('SELECT id FROM operations WHERE request_key=?',(fingerprint,)):
                row=self._load(db,old[0])
                if row['state'] in {'REVIEW_REQUIRED','READY'} and now>=row['expires_at']:
                    row.update(state='EXPIRED',updated_at=now);self._save(db,row)
                elif row['state'] not in TERMINAL:return row
            row={'operation_id':uuid.uuid4().hex,'review':review,'digest':_digest(review),
                'state':'REVIEW_REQUIRED','snapshot_id':snapshot,'created_at':now,'updated_at':now,
                'expires_at':now+300,'result_id':None,'error_code':None}
            db.execute('INSERT INTO operations VALUES(?,?,?,?,?)',
                (row['operation_id'],workspace_id,fingerprint,row['state'],_dump(row)))
        return row

    def approve(self, identity, digest):
        with self._db() as db:
            row=self._load(db,identity)
            if row['state']!='REVIEW_REQUIRED' or row['digest']!=digest:raise OperationError('REVIEW_REQUIRED')
            if int(self.clock())>=row['expires_at']:raise OperationError('EXPIRED')
            row.update(state='READY',updated_at=int(self.clock()))
            self._save(db,row)
        return row

    def cancel(self, identity):
        with self._db() as db:
            row=self._load(db,identity)
            if row['state'] not in {'REVIEW_REQUIRED','READY'}:raise OperationError('OUTCOME_UNKNOWN')
            row.update(state='CANCELLED',updated_at=int(self.clock()))
            self._save(db,row)
        return row

    def execute(self, identity, key):
        row=self.get(identity)
        if row['state']=='VERIFIED':return row
        with self._execution_lock(row['review']['workspace_id']):
            return self._execute(identity,key)

    def _execute(self, identity, key):
        owner=uuid.uuid4().hex;now=int(self.clock())
        with self._db() as db:
            row=self._load(db,identity)
            if row['state']=='VERIFIED':return row
            if row['state']!='READY':raise OperationError('REVIEW_REQUIRED')
            if now>=row['expires_at']:
                row.update(state='EXPIRED',updated_at=now);self._save(db,row);return row
            workspace=row['review']['workspace_id']
            db.execute('DELETE FROM leases WHERE expires<=?',(now,))
            if db.execute('SELECT 1 FROM leases WHERE workspace=?',(workspace,)).fetchone():raise OperationError('BUSY')
            db.execute('INSERT INTO leases VALUES(?,?,?)',(workspace,owner,now+300))
            row.update(state='EXECUTING',updated_at=now);self._save(db,row)
        r=row['review'];write_started=False
        try:
            current=self._inspect(r['action'],workspace,r['target'],r['body'],key)
            if current!=r['preflight'] or r['contract_fingerprint']!=self.api.contract.fingerprint:
                # Old authorization cannot be reused after an external change.
                self._state(identity,'FAILED',error_code='PRECONDITION_CHANGED')
                return self.prepare(r['action'],workspace,key,target=r['target'],body=r['body'],account_key=r['account_key'])
            self._snapshot(r['action'],workspace,r['body'],current,r['account_key'])
            if int(self.clock())>=row['expires_at']:return self._state(identity,'EXPIRED')
            write_started=True
            result=self.api.call(r['action'],workspace,key,target=r['target'],body=r['body'],allow_write=True)
            result_id=result.get('id') if isinstance(result,dict) else None
            if result_id is not None:
                _identifier(result_id)
                if r['target'] is not None and result_id!=r['target']:
                    raise AdminAPIError('RESPONSE_INVALID',outcome_unknown=True)
            self._state(identity,'VERIFYING',result_id=result_id)
            if r['action']=='resend_invite':return self._state(identity,'REQUEST_ACCEPTED')
            return self.reconcile(identity,key)
        except AdminAPIError as exc:
            return self._state(identity,'OUTCOME_UNKNOWN' if write_started and exc.outcome_unknown else 'FAILED',error_code=exc.code)
        except OperationError as exc:
            return self._state(identity,'OUTCOME_UNKNOWN' if write_started else 'FAILED',error_code=exc.code)
        except Exception:
            # No raw provider/filesystem error is written to the operation record.
            return self._state(identity,'OUTCOME_UNKNOWN' if write_started else 'FAILED',error_code='UNAVAILABLE')
        finally:
            with self._db() as db:db.execute('DELETE FROM leases WHERE workspace=? AND owner=?',(workspace,owner))

    def reconcile(self, identity, key):
        row=self.get(identity);r=row['review'];workspace=r['workspace_id']
        if row['state']=='VERIFIED':return row
        if row['state'] not in {'OUTCOME_UNKNOWN','VERIFYING','AWAITING_ACCEPTANCE','REQUEST_ACCEPTED','LOCAL_SYNC_REQUIRED'}:
            raise OperationError('OUTCOME_UNKNOWN')
        try:
            members=self._all('list_users',workspace,key)
            if r['action']=='remove_user':
                verified=r['target'] not in members
            elif r['action']=='update_user':
                item=members.get(r['target'])
                verified=bool(item and item['email']==r['preflight']['target']['email'] and
                    all(item.get(k)==v for k,v in r['body'].items()))
            else:
                invitations=self._all('list_invites',workspace,key)
                if r['action']=='cancel_invite':verified=r['target'] not in invitations
                elif r['action']=='resend_invite':return self._state(identity,row['state'])
                else:
                    email=r['body']['email'].casefold()
                    matching=[item for item in invitations.values() if (item['email'] or '').casefold()==email and
                        all(item.get(k)==v for k,v in r['body'].items() if k!='email')]
                    if len(matching)==1:return self._state(identity,'AWAITING_ACCEPTANCE',result_id=matching[0]['id'])
                    verified=any((item['email'] or '').casefold()==email and
                        all(item.get(k)==v for k,v in r['body'].items() if k!='email') for item in members.values())
            if not verified:return self._state(identity,'OUTCOME_UNKNOWN',error_code='READBACK_MISMATCH')
            if r['account_key'] and r['action'] in {'remove_user','update_user'}:
                account=self.quota.account(r['account_key'])
                # Unknown quota workspace scope stays unknown, rather than
                # marking all of an email's unrelated entitlements removed.
                if account['workspace_id']==workspace:
                    self.quota.record_access(r['account_key'],
                        'ACCESS_REMOVED' if r['action']=='remove_user' else 'WORKSPACE_ACCESS_UNKNOWN',now=int(self.clock()))
            return self._state(identity,'VERIFIED',error_code=None)
        except QuotaError:
            return self._state(identity,'LOCAL_SYNC_REQUIRED',error_code='STORAGE')
        except (AdminAPIError,OperationError):
            return self._state(identity,'OUTCOME_UNKNOWN',error_code='READBACK_UNAVAILABLE')

    def recover(self, identity):
        """After a crashed write, expire its lease and permit only readback."""
        row=self.get(identity)
        with self._execution_lock(row['review']['workspace_id']):
            return self._recover(identity)

    def _recover(self, identity):
        with self._db() as db:
            row=self._load(db,identity)
            if row['state'] not in {'EXECUTING','VERIFYING'}:raise OperationError()
            if int(self.clock())<row['updated_at']+300:raise OperationError('BUSY')
            row.update(state='OUTCOME_UNKNOWN',updated_at=int(self.clock()))
            self._save(db,row)
            db.execute('DELETE FROM leases WHERE workspace=? AND expires<=?',
                       (row['review']['workspace_id'],int(self.clock())))
        return row
