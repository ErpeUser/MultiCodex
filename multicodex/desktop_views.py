"""Shared desktop views. All models are cached, and actions bind to stable IDs."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from .quota_ui import _label, _button, _table_style, _family
from .quota_view import window_text, display_windows, FRESHNESS_TEXT
from .ui_tokens import THEMES


def dashboard_metrics(view, quota, *, loaded):
    profiles=view.get('profiles',[]);processes=view.get('processes',{})
    running=None if not loaded or any(processes.get(p.name,{}).get('running') is None for p in profiles) else sum(processes[p.name]['running'] is True for p in profiles)
    summary=quota.get('summary',{});quota_ready=quota.get('updated_at') is not None
    return [('Profile',len(profiles) if loaded else None),('Instanzen aktiv',running),
        ('Anmeldungen gespeichert',sum(len(v) for v in view.get('sessions',{}).values()) if loaded else None),
        ('Quota-Konten',summary.get('accounts') if loaded and quota_ready else None),
        ('Limits kritisch',summary.get('critical') if loaded and quota_ready else None),
        ('Pr\u00fcfung offen',summary.get('needs_check') if loaded and quota_ready else None)]


def profile_records(view):
    rows=[]
    for profile in view.get('profiles',[]):
        process=view.get('processes',{}).get(profile.name,{});running=process.get('running')
        recovery=view.get('recovery',{}).get(profile.name)
        state='Wiederherstellung n\u00f6tig' if recovery else {True:'L\u00e4uft',False:'Gestoppt',None:'Unbekannt'}.get(running,'Unbekannt')
        actions=('recover',)+(('stop',) if running is True else ()) if recovery else ('stop','restart') if running is True else ('launch',) if running is False else ()
        account=profile.account_email or ('Anmeldung der Original-App' if profile.linked else 'Nicht verifiziert')
        rows.append({'id':profile.name,'profile':profile.name,'actions':actions,
            'cells':{'profile':profile.name,'account':account,'state':state,'kind':'Verkn\u00fcpft' if profile.linked else 'Verwaltet'},
            'detail':profile.name+' | '+account+' | '+state,
            'pids':process.get('pids',[])})
    return rows


def session_records(view, quota_rows):
    rows=[]
    for profile in view.get('profiles',[]):
        if profile.linked:continue
        sessions=view.get('sessions',{}).get(profile.name,[])
        if not sessions:
            rows.append({'id':profile.name+':unregistered','profile':profile.name,'session_id':None,
                'actions':('recover',) if view.get('recovery',{}).get(profile.name) else ('login',),
                'cells':{'profile':profile.name,'email':'Noch keine Anmeldung','state':'Nicht verifiziert','workspace':'Unbekannt','five':'Unbekannt','weekly':'Unbekannt','freshness':'Unbekannt'},
                'detail':profile.name+' | Erste Anmeldung \u00fcber den offiziellen Browser.'})
            continue
        for session in sessions:
            sid=session['id'];active=sid==profile.session_id
            matches=[q for q in quota_rows if q['account']['profile_id']==profile.name and q['account']['session_id']==sid
                and q['account']['email'].casefold()==session['email'].casefold()
                and (not session.get('account_id') or q['account'].get('account_id')==session['account_id'])]
            quota=matches[0] if len(matches)==1 else None
            windows=display_windows(quota['quota'].get('windows',[])) if quota else {}
            recovery=view.get('recovery',{}).get(profile.name)
            actions=('recover',) if recovery else (('login','reauth','inspect','rename') if active else ('login','switch','rename'))
            rows.append({'id':profile.name+':'+sid,'profile':profile.name,'session_id':sid,'actions':actions,
                'cells':{'profile':profile.name,'email':session.get('label') or session['email'],
                    'state':'Wiederherstellung n\u00f6tig' if recovery else 'Zugeordnet' if active else 'Gespeichert',
                    'workspace':(quota['account'].get('workspace_id') or 'Nicht gemeldet') if quota else 'Mehrere Kontexte' if matches else 'Unbekannt',
                    'five':window_text(windows.get('five_hour')),'weekly':window_text(windows.get('weekly')),
                    'freshness':FRESHNESS_TEXT.get(quota['quota']['freshness'],'Unbekannt') if quota else 'Unbekannt'},
                'detail':profile.name+' | '+session['email']+' | '+('Zugeordnete Anmeldung' if active else 'Gespeicherte Anmeldung')+'; gespeicherte Metadaten sind kein Online-Nachweis.'})
    return rows


class MetricStrip(tk.Frame):
    def __init__(self,master,values,*,theme='dark'):
        p=THEMES[theme];super().__init__(master,bg=p['canvas']);self.cells=[];self.values=[];self.columns=0
        for label,value in values:
            cell=tk.Frame(self,bg=p['panel'],highlightthickness=1,highlightbackground=p['border'])
            number=_label(cell,'\u2014' if value is None else str(value),p,size=24,bold=True)
            number.pack(anchor='w',padx=14,pady=(12,2));self.values.append(number)
            _label(cell,label,p,muted=True,size=9).pack(anchor='w',padx=14,pady=(0,12))
            self.cells.append(cell)
        self.bind('<Configure>',self._reflow)

    def set_values(self, values):
        for number,(_,value) in zip(self.values,values):
            number.configure(text='\u2014' if value is None else str(value))

    def _reflow(self,event):
        columns=3 if event.width>=650 else 2
        if columns==self.columns:return
        for c in range(3):self.grid_columnconfigure(c,weight=1 if c<columns else 0,uniform='metrics')
        for i,cell in enumerate(self.cells):cell.grid(row=i//columns,column=i%columns,sticky='ew',padx=4,pady=4)
        self.columns=columns


class ActionTable(tk.Frame):
    """Reusable paged table with identity-bound, explicitly invoked actions."""
    PAGE_SIZE=100
    def __init__(self,master,*,title,columns,actions,on_action,theme='dark'):
        p=THEMES[theme];super().__init__(master,bg=p['canvas'])
        self.p=p;self.rows={};self.busy=False;self.loaded=False;self.on_action=on_action;self.page=0;self.offset=0
        self._restoring=False;self.columns=columns;self.grid_columnconfigure(0,weight=1)
        prefix=_table_style(self,theme)
        _label(self,title,p,size=17,bold=True).grid(row=0,column=0,sticky='w',pady=(0,10))
        controls=tk.Frame(self,bg=p['canvas']);controls.grid(row=1,column=0,sticky='ew',pady=(0,9));controls.grid_columnconfigure(0,weight=1)
        self.query=tk.StringVar(self);self.filter=tk.StringVar(self,value='Alle');self.order=tk.StringVar(self,value=columns[0][1])
        self.search=tk.Entry(controls,textvariable=self.query,bg=p['panel'],fg=p['text'],insertbackground=p['text'],
            relief='flat',highlightthickness=1,highlightcolor=p['accent'],highlightbackground=p['border'],font=(_family(self),10),width=16)
        self.search.grid(row=1,column=0,sticky='ew',ipady=6,padx=(0,8))
        _label(controls,'Suchen',p,size=9,muted=True).grid(row=0,column=0,sticky='w')
        _label(controls,'Status',p,size=9,muted=True).grid(row=0,column=1,sticky='w')
        _label(controls,'Sortierung',p,size=9,muted=True).grid(row=0,column=2,sticky='w')
        self.filter_combo=ttk.Combobox(controls,textvariable=self.filter,state='readonly',values=['Alle'],width=18,style=prefix+'.TCombobox')
        self.filter_combo.grid(row=1,column=1,sticky='ew',ipady=4,padx=(0,8))
        ttk.Combobox(controls,textvariable=self.order,state='readonly',values=[c[1] for c in columns],width=18,
            style=prefix+'.TCombobox').grid(row=1,column=2,sticky='ew',ipady=4)
        box=tk.Frame(self,bg=p['canvas']);box.grid(row=2,column=0,sticky='nsew');box.grid_columnconfigure(0,weight=1)
        self.table=ttk.Treeview(box,columns=[c[0] for c in columns],show='headings',height=7,selectmode='browse',style=prefix+'.Treeview')
        for key,label,width in columns:self.table.heading(key,text=label);self.table.column(key,width=width,minwidth=90,stretch=True)
        self.table.grid(row=0,column=0,sticky='nsew')
        y=ttk.Scrollbar(box,orient='vertical',command=self.table.yview);y.grid(row=0,column=1,sticky='ns')
        x=ttk.Scrollbar(box,orient='horizontal',command=self.table.xview);x.grid(row=1,column=0,sticky='ew')
        self.table.configure(yscrollcommand=y.set,xscrollcommand=x.set)
        self.count_label=_label(self,'Daten werden geladen.',p,muted=True,size=9);self.count_label.grid(row=3,column=0,sticky='w',pady=6)
        paging=tk.Frame(self,bg=p['canvas']);paging.grid(row=4,column=0,sticky='w')
        self.prev_button=_button(paging,'Zur\u00fcck',lambda:self._page(-1),p);self.prev_button.pack(side='left',padx=(0,8))
        self.next_button=_button(paging,'Weiter',lambda:self._page(1),p);self.next_button.pack(side='left')
        self.detail=_label(self,'Zeile ausw\u00e4hlen, um die vollst\u00e4ndige Identit\u00e4t und Aktionen zu sehen.',p,muted=True,size=9)
        self.detail.grid(row=5,column=0,sticky='ew',pady=(10,6))
        buttons=tk.Frame(self,bg=p['canvas']);buttons.grid(row=6,column=0,sticky='ew')
        for c in (0,1):buttons.grid_columnconfigure(c,weight=1,uniform='actions')
        self.buttons={}
        for index,(action,label) in enumerate(actions):
            button=_button(buttons,label,lambda a=action:self._action(a),p);self.buttons[action]=button
            button.grid(row=index//2,column=index%2,sticky='ew',padx=(0,8) if index%2==0 else 0,pady=3)
        self.table.bind('<<TreeviewSelect>>',lambda _e:self._selection())
        for var in (self.query,self.filter,self.order):var.trace_add('write',lambda *_:self._changed())
        self.bind('<Configure>',lambda e:self.detail.configure(wraplength=max(200,e.width-10)))
        self.search.bind('<Escape>',lambda _e:self.query.set(''))
        self.table.bind('<Control-f>',lambda _e:self.search.focus_set())
        self._selection()

    def get_state(self):
        selected=self.table.selection()
        return {'query':self.query.get(),'filter':self.filter.get(),'order':self.order.get(),
                'offset':self.offset,'selected':selected[0] if selected else None}

    def set_rows(self,rows,*,loaded=True,state=None):
        state=self.get_state() if state is None else state
        self._restoring=True;self.rows={r['id']:r for r in rows};self.loaded=loaded
        states=sorted({r['cells'].get('state','Unbekannt') for r in rows})
        self.filter_combo.configure(values=['Alle',*states])
        self.query.set(state.get('query',''));self.filter.set(state.get('filter','Alle'))
        if self.filter.get() not in ['Alle',*states]:self.filter.set('Alle')
        self.order.set(state.get('order',self.columns[0][1]));self.offset=max(0,state.get('offset',0))
        self._restoring=False;self._refresh(state.get('selected'))

    def _changed(self):
        if not self._restoring:self.offset=0;self._refresh()

    def _filtered(self):
        q=self.query.get().strip().casefold();status=self.filter.get()
        key=next((c[0] for c in self.columns if c[1]==self.order.get()),self.columns[0][0])
        return sorted([r for r in self.rows.values() if
            (status=='Alle' or r['cells'].get('state')==status) and
            (not q or q in (' '.join(str(v) for v in r['cells'].values())+' '+r.get('detail','')).casefold())],
            key=lambda r:(str(r['cells'].get(key,'')).casefold(),r['id']))

    def _refresh(self,selected=None):
        if selected is None:
            old=self.table.selection();selected=old[0] if old else None
        rows=self._filtered();self.offset=min(self.offset,max(0,((len(rows)-1)//self.PAGE_SIZE)*self.PAGE_SIZE))
        self.table.delete(*self.table.get_children())
        visible=rows[self.offset:self.offset+self.PAGE_SIZE]
        for row in visible:self.table.insert('','end',iid=row['id'],values=[row['cells'].get(c[0],'Unbekannt') for c in self.columns])
        if selected and any(r['id']==selected for r in visible):self.table.selection_set(selected)
        self.count_label.configure(text=(f'{len(rows)} Treffer von {len(self.rows)} Eintr\u00e4gen | Seite {self.offset//self.PAGE_SIZE+1}' if self.loaded else 'Daten werden geladen.'))
        self.prev_button.configure(state='normal' if self.offset>0 else 'disabled')
        self.next_button.configure(state='normal' if self.offset+self.PAGE_SIZE<len(rows) else 'disabled')
        self._selection()

    def _selection(self):
        selected=self.table.selection();row=self.rows.get(selected[0]) if selected else None
        self.detail.configure(text=row.get('detail','') if row else 'Zeile ausw\u00e4hlen, um die vollst\u00e4ndige Identit\u00e4t und Aktionen zu sehen.')
        for action,button in self.buttons.items():button.configure(state='normal' if row and action in row.get('actions',()) and not self.busy else 'disabled')

    def _page(self,delta):self.offset=max(0,self.offset+delta*self.PAGE_SIZE);self._refresh()
    def set_busy(self,busy):self.busy=bool(busy);self._selection()
    def _action(self,action):
        selected=self.table.selection();row=self.rows.get(selected[0]) if selected else None
        if row and not self.busy and action in row.get('actions',()):self.on_action(action,row)
