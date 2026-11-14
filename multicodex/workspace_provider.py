"""Read-only ChatGPT workspace directory using the published Admin API contract.

Source: OpenAI Help article 20001407 and openai-cookbook's
examples/chatgpt/daily_usage_limits/src/admin-api.mjs (listMemberDirectory).
No Platform organization endpoint, inferred mutation route, or browser cookie.
"""
from __future__ import annotations
import json
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

BASE = 'https://api.chatgpt.com/v1/manage/workspaces/'

class WorkspaceError(RuntimeError):
    def __init__(self, code='INVALID_RESPONSE'):
        self.code = code if code in {'INVALID_REQUEST','INVALID_RESPONSE','PERMISSION_DENIED',
            'AUTH_REQUIRED','RATE_LIMITED','UNAVAILABLE','CANCELLED','BOUND_EXCEEDED','REDIRECT'} else 'UNAVAILABLE'
        super().__init__('Workspace directory: '+self.code)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise WorkspaceError('REDIRECT')


def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',value):
        raise WorkspaceError('INVALID_REQUEST')
    return value


def _get(url, key, timeout):
    # Fixed origin plus validated IDs. Redirects never receive the Admin key.
    request = Request(url, headers={'Authorization':'Bearer '+key, 'Accept':'application/json'}, method='GET')
    with build_opener(NoRedirect()).open(request,timeout=timeout) as response:
        if response.status != 200: raise WorkspaceError('UNAVAILABLE')
        raw=response.read(1024*1024+1)
        if len(raw)>1024*1024: raise WorkspaceError('BOUND_EXCEEDED')
        return json.loads(raw.decode('utf-8'))


class WorkspaceDirectory:
    def __init__(self, *, request=_get, max_pages=20, clock=time.monotonic):
        if type(max_pages) is not int or not 1<=max_pages<=100: raise WorkspaceError('INVALID_REQUEST')
        self.request,self.max_pages,self.clock=request,max_pages,clock

    def read_members(self, workspace_id, key, *, cancel=None):
        identifier(workspace_id)
        if not isinstance(key,str) or not re.fullmatch(r'[\x21-\x7e]{1,2048}',key):
            raise WorkspaceError('INVALID_REQUEST')
        cancel=cancel if cancel is not None else threading.Event()
        deadline=self.clock()+30
        members={};after=None
        try:
            for _ in range(self.max_pages):
                if cancel.is_set(): raise WorkspaceError('CANCELLED')
                remaining=deadline-self.clock()
                if remaining<=0: raise WorkspaceError('BOUND_EXCEEDED')
                query={'limit':'1000'}
                if after is not None:query['after']=after
                page=self.request(BASE+workspace_id+'/users?'+urlencode(query),key,min(15,remaining))
                if cancel.is_set():raise WorkspaceError('CANCELLED')
                if not isinstance(page,dict) or page.get('object')!='list':raise WorkspaceError()
                rows=page.get('data')
                if not isinstance(rows,list) or len(rows)>1000 or type(page.get('has_more')) is not bool:
                    raise WorkspaceError()
                for row in rows:
                    if not isinstance(row,dict) or row.get('object')!='workspace.user':raise WorkspaceError()
                    ident=identifier(row.get('id'))
                    if ident in members or 'email' not in row:raise WorkspaceError()
                    email=row['email']
                    if email is not None and (not isinstance(email,str) or len(email)>320 or
                        re.fullmatch(r'[^\s@]+@[^\s@]+',email) is None or re.search(r'[\x00-\x1f\x7f]',email)):raise WorkspaceError()
                    # Roles/seats are not inferred from undocumented fields.
                    members[ident]={'id':ident,'email':email}
                if page.get('first_id')!=(rows[0]['id'] if rows else None) or \
                    page.get('last_id')!=(rows[-1]['id'] if rows else None):raise WorkspaceError()
                if not page['has_more']:
                    return {'workspace_id':workspace_id,'members':sorted(members.values(),key=lambda r:r['id']),
                        'observed_at':int(time.time()),'source':'official-workspace-admin-api',
                        'complete':True,'writes_supported':False}
                if not rows or page['last_id']==after:raise WorkspaceError()
                after=page['last_id']
            raise WorkspaceError('BOUND_EXCEEDED')
        except WorkspaceError:
            raise
        except HTTPError as exc:
            code={401:'AUTH_REQUIRED',403:'PERMISSION_DENIED',429:'RATE_LIMITED'}.get(exc.code,'UNAVAILABLE')
            raise WorkspaceError(code) from None
        except (URLError,OSError,ValueError,TypeError,KeyError,RuntimeError):
            raise WorkspaceError('UNAVAILABLE') from None
