from multicodex.codex_client import AccountIdentity, CodexError

class AuthFixture:
    def __init__(self): self.identities={};self.error=None;self.next_identity=AccountIdentity('new@example.invalid','plus',None)
    def describe(self,home,**kwargs):
        value=self.identities.get(str(home))
        if value is None: raise CodexError('NOT_AUTHENTICATED')
        return value
    def login(self,home,*,on_browser,cancel,expected=None):
        if cancel.is_set(): raise CodexError('CANCELLED')
        if self.error: raise CodexError(self.error)
        on_browser('https://auth.openai.com/authorize?fixture=1')
        identity=self.next_identity
        if expected is not None and not expected.same_account(identity): raise CodexError('ACCOUNT_MISMATCH')
        self.identities[str(home)]=identity
        return identity

class InstancesFixture:
    def __init__(self,store):
        self.store=store;self.live=set();self.actions=[];self.fail_session=None;self.stop_error=False
    def running(self,name): return name in self.live
    def stop(self,name,**kwargs):
        self.actions.append(('stop',name))
        if self.stop_error: raise RuntimeError('fixture stop failure')
        was=name in self.live;self.live.discard(name);return int(was)
    def launch(self,name):
        self.actions.append(('launch',name,self.store.get(name).session_id))
        if self.store.get(name).session_id==self.fail_session: raise RuntimeError('fixture launch failure')
        self.live.add(name);return 100
