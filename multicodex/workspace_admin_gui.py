"""JobRunner boundary for administration; render never performs I/O."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import threading
from .workspace_admin_service import WorkspaceAdminService
from .workspace_admin_ui import WorkspaceAdminPanel


class WorkspaceAdminGuiController:
    def __init__(self, host, root, *, service_factory=None):
        self.host=host;self.root=Path(root);self.cancel=threading.Event()
        self.service=None;self.service_factory=service_factory
        self.panel=None;self.busy=False;self.ready=False
        self.model={'records':[],'capabilities':{},'workspace_id':None}

    def _get_service(self):
        if self.service is None:
            self.service=(self.service_factory() if self.service_factory else
                WorkspaceAdminService(self.root/'workspace-admin',self.host.quota._get_service().store,cancel=self.cancel))
        return self.service

    def _alive(self):
        return self.panel is not None and self.panel.winfo_exists()

    def sync_busy(self):
        if self._alive():self.panel.set_busy(self.busy or self.host.mutating or self.host.closing)

    def render(self):
        self.panel=WorkspaceAdminPanel(self.host.page_frame,theme=self.host.theme_name,on_event=self.event)
        self.panel.pack(fill='both',expand=True,padx=7,pady=(6,14))
        self.panel.set_model(self.model);self.sync_busy()
        if not self.ready:self.event('history',{})

    def event(self,event,data):
        if (self.host.closing or self.host.mutating or self.cancel.is_set() or self.busy or
            event not in {'history','connect','prepare','execute','cancel','recover','reconcile'}):return
        # Do not retain caller-owned mutable forms or a key on the controller.
        payload=deepcopy(data)
        def work():
            if self.cancel.is_set():return self.model
            service=self._get_service()
            if event=='history':return service.view()
            if event=='connect':return service.connect(payload['workspace_id'],payload['key'])
            if event=='prepare':
                return service.prepare(payload['action'],payload['workspace_id'],payload['key'],
                    target=payload.get('target'),body=payload.get('body'),account_key=payload.get('account_key'))
            if event=='execute':return service.execute(payload['identity'],payload['digest'],payload['key'])
            return service.action(payload['identity'],event,payload.get('key'))
        self.busy=True
        accepted=self.host._submit('workspace-admin',work,self._loaded,mutation=True,error_callback=self._failed)
        if not accepted:
            self.busy=False
            self.host._set_status('Eine andere Aktion l\u00e4uft. Admin-Anfrage wurde nicht gestartet.')
        self.sync_busy()

    def _loaded(self,model):
        self.busy=False
        if self.host.closing:return
        self.ready=True;self.model=model
        if self._alive():self.panel.set_model(model)
        row=model.get('selected')
        if row:
            from .workspace_admin_ui import STATE_TEXT
            self.host._set_status(STATE_TEXT.get(row['state'],'Ergebnis pr\u00fcfen.'))
        self.sync_busy()

    def _failed(self,error):
        self.busy=False
        if self.host.closing:return
        if self._alive():self.panel.set_error(getattr(error,'code','UNAVAILABLE'))
        self.host._set_status('Admin-Ergebnis nicht best\u00e4tigt. Verbindung und gespeicherten Vorgang pr\u00fcfen.')
        self.sync_busy()

    def close(self):
        self.cancel.set()
