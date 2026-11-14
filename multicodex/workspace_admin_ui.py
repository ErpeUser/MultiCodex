"""Administration widgets: cached models in, explicit worker commands out."""
from __future__ import annotations
from copy import deepcopy
import time
import tkinter as tk
from tkinter import ttk
from .quota_ui import _label, _button, _table_style, _family
from .ui_tokens import THEMES

ACTION_TEXT = {
    'create_invite': 'Mitglied einladen', 'resend_invite': 'Einladung erneut senden',
    'cancel_invite': 'Einladung widerrufen', 'update_user': 'Rolle / Seat \u00e4ndern',
    'remove_user': 'Mitglied entfernen',
}
STATE_TEXT = {
    'REVIEW_REQUIRED': 'Freigabe erforderlich', 'READY': 'Freigegeben',
    'EXECUTING': 'Wird ausgef\u00fchrt', 'VERIFYING': 'Ergebnis wird gepr\u00fcft',
    'VERIFIED': 'Ergebnis best\u00e4tigt', 'OUTCOME_UNKNOWN': 'Ergebnis unklar: nur erneut pr\u00fcfen',
    'AWAITING_ACCEPTANCE': 'Einladung offen: Annahme ausstehend',
    'REQUEST_ACCEPTED': 'Versand angefordert, Zustellung nicht best\u00e4tigt',
    'FAILED': 'Nicht abgeschlossen', 'EXPIRED': 'Freigabe abgelaufen',
    'CANCELLED': 'Vorgang abgebrochen', 'LOCAL_SYNC_REQUIRED': 'Lokalen Status erneut abgleichen',
}
ERROR_TEXT = {
    'LAST_OWNER': 'Der letzte Owner darf nicht entfernt oder herabgestuft werden.',
    'SCIM_MANAGED': 'Dieses Mitglied wird durch den Identit\u00e4tsanbieter verwaltet.',
    'MANAGEMENT_UNKNOWN': 'Die Verwaltungszust\u00e4ndigkeit ist nicht best\u00e4tigt.',
    'SNAPSHOT_REQUIRED': 'Ein gespeicherter Quota-Snapshot ist vor diesem Schritt erforderlich.',
    'ACCOUNT_MISMATCH': 'Workspace oder Quota-Konto passt nicht zum ausgew\u00e4hlten Mitglied.',
    'PERMISSION_DENIED': 'Der Admin-Key hat nicht die erforderliche Berechtigung.',
    'AUTH_REQUIRED': 'Ein g\u00fcltiger Admin-Key ist erforderlich.',
    'BUSY': 'Eine andere Aktion l\u00e4uft. Den aktuellen Vorgang zuerst pr\u00fcfen.',
    'EXPIRED': 'Die Vorschau ist abgelaufen. Eine neue Vorschau erstellen.',
    'ALREADY_MEMBER': 'Dieses Konto ist bereits Mitglied.',
    'INVITATION_EXISTS': 'F\u00fcr dieses Konto besteht bereits eine Einladung.',
}
READBACK = {'OUTCOME_UNKNOWN', 'VERIFYING', 'AWAITING_ACCEPTANCE', 'REQUEST_ACCEPTED', 'LOCAL_SYNC_REQUIRED'}


def review_description(record):
    r = record['review']; target = r.get('preflight', {}).get('target', {})
    body = r.get('body') or {}
    fields = [('Aktion', ACTION_TEXT.get(r['action'], 'Unbekannt')),
              ('Workspace', r['workspace_id']), ('Ziel-ID', r.get('target') or 'Neue Einladung'),
              ('Konto', target.get('email') or body.get('email') or 'Nicht gemeldet'),
              ('Rolle', body.get('role') or 'Unver\u00e4ndert / Standard laut Anbieter'),
              ('Seat', body.get('seat_type') or 'Unver\u00e4ndert / Standard laut Anbieter'),
              ('Gesicherter Snapshot', str(record.get('snapshot_id') or 'Nicht erforderlich')),
              ('Status', STATE_TEXT.get(record['state'], 'Unbekannt'))]
    return '\n'.join(f'{name}: {value}' for name, value in fields)


class WorkspaceAdminPanel(tk.Frame):
    def __init__(self, master, *, theme='dark', on_event):
        p = THEMES[theme]
        super().__init__(master, bg=p['canvas'])
        self.p = p; self.on_event = on_event; self.busy = False; self.connected = False
        self.model = {}; self.current_review = None; self.action_choices = []; self.quota_choices = {}
        self.directory_rows = {}; self.record_rows = {}; self.target = None
        self.grid_columnconfigure(0, weight=1)
        prefix = _table_style(self, theme)
        _label(self, 'Workspace verwalten', p, size=19, bold=True).grid(row=0, column=0, sticky='w', pady=(0,6))
        note = _label(self, '1. Verbindung pr\u00fcfen  \u00b7  2. Aktion vorbereiten  \u00b7  3. Genau diese Vorschau freigeben', p, muted=True)
        note.grid(row=1, column=0, sticky='ew', pady=(0,12))
        connection = tk.Frame(self, bg=p['canvas']); connection.grid(row=2,column=0,sticky='ew')
        for col in (0,1): connection.grid_columnconfigure(col,weight=1,uniform='connection')
        self.workspace = tk.StringVar(self); self.action = tk.StringVar(self)
        self.email = tk.StringVar(self); self.role = tk.StringVar(self); self.seat = tk.StringVar(self)
        self.quota = tk.StringVar(self); self.confirmed = tk.BooleanVar(self)
        self.workspace_entry = self._entry(connection,'Workspace-ID',self.workspace,0,0)
        self.key = self._entry(connection,'Admin-Key (nur f\u00fcr diese Anfrage)',None,0,1,secret=True)
        self.connect_button = _button(connection,'Verbindung pr\u00fcfen',lambda:self._send('connect',{'workspace_id':self.workspace.get().strip()},key=True),p)
        self.connect_button.grid(row=2,column=0,columnspan=2,sticky='w',pady=(8,12))
        self.status = _label(self,'Keine Verbindung. Aktionen werden aus dem offiziellen API-Vertrag geladen.',p,muted=True)
        self.status.grid(row=3,column=0,sticky='ew',pady=(0,10))
        self.directory = self._table(4, ('kind','email','role','seat'),
            ('Art','Konto / ID','Rolle','Seat'), (100,260,160,140), height=5)
        self.directory.bind('<<TreeviewSelect>>',self._directory_selected)
        form = tk.Frame(self,bg=p['panel']);form.grid(row=5,column=0,sticky='ew',pady=12)
        for col in (0,1):form.grid_columnconfigure(col,weight=1,uniform='form')
        self.action_combo=self._combo(form,'Aktion',self.action,0,0,prefix)
        self.email_entry=self._entry(form,'E-Mail (f\u00fcr neue Einladung)',self.email,0,1)
        self.role_combo=self._combo(form,'Neue Rolle (optional)',self.role,2,0,prefix)
        self.seat_combo=self._combo(form,'Neuer Seat (optional, kann Kosten \u00e4ndern)',self.seat,2,1,prefix)
        self.quota_combo=self._combo(form,'Quota-Konto vor Entfernung / Seat-Wechsel',self.quota,4,0,prefix)
        self.prepare_button=_button(form,'Vorschau erstellen',self._prepare,p,primary=True)
        self.prepare_button.grid(row=5,column=1,sticky='ew',padx=10,pady=(3,10))
        _label(self,'Gespeicherte Vorg\u00e4nge',p,size=12,bold=True).grid(row=6,column=0,sticky='w',pady=(4,6))
        self.records=self._table(7,('action','workspace','state'),('Aktion','Workspace','Status'),(180,160,300),height=4)
        self.records.bind('<<TreeviewSelect>>',self._record_selected)
        self.review_text=tk.Text(self,height=9,wrap='word',bg=p['panel'],fg=p['text'],relief='flat',
            font=(_family(self),10),padx=12,pady=10,takefocus=True)
        self.review_text.grid(row=8,column=0,sticky='ew',pady=(12,6));self.review_text.configure(state='disabled')
        self.confirm_box=tk.Checkbutton(self,text='Ich best\u00e4tige genau diese Aktion, den Workspace und m\u00f6gliche Zugriffs-/Kosten\u00e4nderungen.',
            variable=self.confirmed,bg=p['canvas'],fg=p['text'],selectcolor=p['panel'],activebackground=p['canvas'],
            activeforeground=p['text'],anchor='w',justify='left',takefocus=True)
        self.confirm_box.grid(row=9,column=0,sticky='ew',pady=(2,8))
        actions=tk.Frame(self,bg=p['canvas']);actions.grid(row=10,column=0,sticky='ew')
        for col in (0,1):actions.grid_columnconfigure(col,weight=1,uniform='actions')
        self.execute_button=_button(actions,'Freigeben und ausf\u00fchren',self._execute,p,primary=True)
        self.reconcile_button=_button(actions,'Nur Ergebnis pr\u00fcfen',lambda:self._record_action('reconcile',True),p)
        self.cancel_button=_button(actions,'Vorgang abbrechen',lambda:self._record_action('cancel'),p)
        self.recover_button=_button(actions,'Absturzstatus pr\u00fcfen',lambda:self._record_action('recover'),p)
        for index,button in enumerate((self.execute_button,self.reconcile_button,self.cancel_button,self.recover_button)):
            button.grid(row=index//2,column=index%2,sticky='ew',padx=(0,8) if index%2==0 else 0,pady=3)
        self.confirmed.trace_add('write',lambda *_:self._controls())
        for variable in (self.workspace,self.email,self.role,self.seat,self.quota):
            variable.trace_add('write',lambda *_:self._invalidate())
        self.action.trace_add('write',lambda *_:self._change_action())
        self.bind('<Configure>',lambda e:(note.configure(wraplength=max(200,e.width-20)),
            self.status.configure(wraplength=max(200,e.width-20)),self.confirm_box.configure(wraplength=max(200,e.width-40))))
        self._controls()

    def _entry(self,parent,label,variable,row,col,secret=False):
        _label(parent,label,self.p,size=9,muted=True).grid(row=row,column=col,sticky='w',padx=10,pady=(8,3))
        widget=tk.Entry(parent,textvariable=variable,show='*' if secret else '',bg=self.p['panel'],fg=self.p['text'],
            insertbackground=self.p['text'],relief='flat',highlightthickness=1,highlightbackground=self.p['border'],
            highlightcolor=self.p['accent'],font=(_family(self),10),width=18)
        widget.grid(row=row+1,column=col,sticky='ew',padx=10,ipady=6,pady=(0,5))
        return widget

    def _combo(self,parent,label,variable,row,col,prefix):
        _label(parent,label,self.p,size=9,muted=True).grid(row=row,column=col,sticky='w',padx=10,pady=(8,3))
        combo=ttk.Combobox(parent,textvariable=variable,state='readonly',style=prefix+'.TCombobox',width=18)
        combo.grid(row=row+1,column=col,sticky='ew',padx=10,ipady=5,pady=(0,5))
        return combo

    def _table(self,row,columns,labels,widths,height):
        box=tk.Frame(self,bg=self.p['canvas']);box.grid(row=row,column=0,sticky='nsew');box.grid_columnconfigure(0,weight=1)
        table=ttk.Treeview(box,columns=columns,show='headings',height=height,selectmode='browse',
                           style=_table_style(self,'dark' if self.p is THEMES['dark'] else 'light')+'.Treeview')
        for key,label,width in zip(columns,labels,widths):
            table.heading(key,text=label);table.column(key,width=width,minwidth=70,stretch=True)
        table.grid(row=0,column=0,sticky='nsew')
        y=ttk.Scrollbar(box,orient='vertical',command=table.yview);y.grid(row=0,column=1,sticky='ns')
        x=ttk.Scrollbar(box,orient='horizontal',command=table.xview);x.grid(row=1,column=0,sticky='ew')
        table.configure(yscrollcommand=y.set,xscrollcommand=x.set)
        return table

    def _invalidate(self):
        self.confirmed.set(False)
        self._controls()

    def _action_id(self):
        return next((key for key in self.action_choices if ACTION_TEXT[key]==self.action.get()),None)

    def choose_action(self,action):
        self.action.set(ACTION_TEXT.get(action,''))

    def _change_action(self):
        capability=self.model.get('capabilities',{}).get(self._action_id(),{})
        for combo,var,key in ((self.role_combo,self.role,'roles'),(self.seat_combo,self.seat,'seats')):
            combo.configure(values=('',*capability.get(key,())))
            var.set('')
        self._invalidate()

    def _connected_workspace(self):
        return self.connected and self.workspace.get().strip()==self.model.get('workspace_id')

    def _controls(self):
        if not hasattr(self,'execute_button'):return
        row=self.current_review;state=row['state'] if row else None
        available=self._connected_workspace() and not self.busy
        review_valid=bool(row and row['review']['workspace_id']==self.workspace.get().strip() and
                          row.get('expires_at',0)>time.time())
        for button,enabled in ((self.connect_button,not self.busy),
            (self.prepare_button,available and self._action_id() is not None),
            (self.execute_button,available and review_valid and state in {'REVIEW_REQUIRED','READY'} and self.confirmed.get()),
            (self.reconcile_button,available and bool(row) and state in READBACK),
            (self.cancel_button,not self.busy and state in {'REVIEW_REQUIRED','READY'}),
            (self.recover_button,not self.busy and state in {'EXECUTING','VERIFYING'})):
            button.configure(state='normal' if enabled else 'disabled')
            if button in (self.prepare_button,self.execute_button):
                button.configure(bg=self.p['accent'] if enabled else self.p['selected'])

    def set_busy(self,busy):
        self.busy=bool(busy);self._controls()

    def set_error(self,code):
        self.connected=False;self.busy=False;self.confirmed.set(False)
        self.status.configure(text=ERROR_TEXT.get(code,'Ergebnis nicht best\u00e4tigt. Verbindung und gespeicherten Vorgang pr\u00fcfen; nicht blind erneut ausf\u00fchren.'))
        self._controls()

    def _send(self,event,data,key=False):
        if self.busy:return
        if key:
            secret=self.key.get();self.key.delete(0,'end')
            if not secret:
                self.status.configure(text='Admin-Key f\u00fcr diese Anfrage eingeben. Er wird nicht gespeichert.');return
            data={**data,'key':secret}
        self.on_event(event,data)

    def _directory_selected(self,_event=None):
        selected=self.directory.selection()
        self.target=self.directory_rows.get(selected[0]) if selected else None
        self.quota_choices={}
        if self.target:
            _,row=self.target;self.email.set(row.get('email') or '')
            for account in self.model.get('quota_accounts',[]):
                if (account['email'].casefold()==(row.get('email') or '').casefold() and
                    account['workspace_id'] in (None,self.model.get('workspace_id'))):
                    label=account['profile_id']+' | '+account['email']+' | '+account['account_key'][:8]
                    self.quota_choices[label]=account['account_key']
        self.quota_combo.configure(values=('',*self.quota_choices))
        self.quota.set(next(iter(self.quota_choices)) if len(self.quota_choices)==1 else '')
        self._invalidate()

    def _prepare(self):
        if not self._connected_workspace() or self.busy:return
        action=self._action_id()
        if action is None:return
        data={'action':action,'workspace_id':self.workspace.get().strip()}
        if action=='create_invite':
            body={'email':self.email.get().strip()}
        else:
            wanted='member' if action in {'update_user','remove_user'} else 'invitation'
            if not self.target or self.target[0]!=wanted:
                self.status.configure(text='Zuerst das passende Mitglied oder die Einladung ausw\u00e4hlen.');return
            data['target']=self.target[1]['id'];body={} if action=='update_user' else None
        if body is not None:
            if self.role.get():body['role']=self.role.get()
            if self.seat.get():body['seat_type']=self.seat.get()
            data['body']=body
        if self.quota.get() in self.quota_choices:data['account_key']=self.quota_choices[self.quota.get()]
        self._send('prepare',data,key=True)

    def _record_selected(self,_event=None):
        selected=self.records.selection()
        self.current_review=deepcopy(self.record_rows.get(selected[0])) if selected else None
        self.review_text.configure(state='normal');self.review_text.delete('1.0','end')
        self.review_text.insert('1.0',review_description(self.current_review) if self.current_review else 'Vorgang ausw\u00e4hlen. Ohne Vorschau keine \u00c4nderung.')
        self.review_text.configure(state='disabled');self._invalidate()

    def _execute(self):
        self._controls()
        if str(self.execute_button.cget('state'))=='disabled':return
        row=self.current_review
        self._send('execute',{'identity':row['operation_id'],'digest':row['digest']},key=True)
        self.confirmed.set(False)

    def _record_action(self,action,key=False):
        self._controls()
        button={'reconcile':self.reconcile_button,'cancel':self.cancel_button,'recover':self.recover_button}[action]
        if self.current_review and str(button.cget('state'))!='disabled':
            self._send(action,{'identity':self.current_review['operation_id']},key=key)

    def set_model(self,model):
        self.model=deepcopy(model);self.connected=bool(model.get('workspace_id'));self.busy=False
        self.workspace.set(model.get('workspace_id') or self.workspace.get())
        self.action_choices=[a for a in ACTION_TEXT if model.get('capabilities',{}).get(a,{}).get('enabled')]
        previous=self._action_id()
        self.action_combo.configure(values=[ACTION_TEXT[a] for a in self.action_choices],state='readonly' if self.action_choices else 'disabled')
        self.choose_action(previous if previous in self.action_choices else self.action_choices[0] if self.action_choices else '')
        self.directory.delete(*self.directory.get_children());self.directory_rows={};self.target=None
        self.quota_choices={};self.quota_combo.configure(values=('',));self.quota.set('')
        for kind,source in (('member','members'),('invitation','invitations')):
            for row in model.get(source,[]):
                iid=kind+':'+row['id'];self.directory_rows[iid]=(kind,row)
                self.directory.insert('', 'end',iid=iid,values=('Mitglied' if kind=='member' else 'Einladung',
                    row.get('email') or row['id'],row.get('role') or 'Nicht gemeldet',row.get('seat_type') or 'Nicht gemeldet'))
        self.records.delete(*self.records.get_children());self.record_rows={}
        for row in model.get('records',[]):
            self.record_rows[row['operation_id']]=row;r=row['review']
            self.records.insert('','end',iid=row['operation_id'],values=(ACTION_TEXT.get(r['action'],'Unbekannt'),
                r['workspace_id'],STATE_TEXT.get(row['state'],'Unbekannt')))
        selected=model.get('selected')
        if selected and selected['operation_id'] in self.record_rows:
            self.records.selection_set(selected['operation_id'])
        self._record_selected()
        count=len(self.action_choices)
        self.status.configure(text=(f'API-Vertrag {model.get("contract_version") or "nicht geladen"}: {count} Verwaltungsaktionen verf\u00fcgbar. '
            + ('Verzeichnis muss nach \u00c4nderungen neu geladen werden.' if model.get('observed_at') is None else 'Berechtigungen werden bei jeder Aktion serverseitig gepr\u00fcft.')))
        self._controls()
