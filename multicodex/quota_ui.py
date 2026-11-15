"""Native Tk quota components embedded in the existing CustomTkinter shell.

These widgets render supplied models only. All callbacks are dispatched by the
host's worker bridge; no filesystem, network or process access happens here.
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, font
from .automation_settings import validate_settings, SettingsError
from .quota import format_reset, format_countdown
from .quota_view import (STATUS_TEXT, FRESHNESS_TEXT, ACCESS_TEXT, ERROR_TEXT,
                         REMOVED, filter_rows, summarize_rows, window_text, display_windows)
from .ui_tokens import THEMES, BREAKPOINTS


def _family(widget):
    return 'Segoe UI' if 'Segoe UI' in font.families(widget) else font.nametofont('TkDefaultFont').actual('family')


def _label(master, text, palette, *, size=10, bold=False, muted=False, **kwargs):
    return tk.Label(master,text=text,bg=master.cget('background'),fg=palette['muted' if muted else 'text'],
        font=(_family(master),size,'bold' if bold else 'normal'),anchor='w',justify='left',**kwargs)


def _button(master, text, command, palette, *, primary=False):
    button=tk.Button(master,text=text,command=command,relief='flat',bd=0,padx=12,pady=7,
        bg=palette['accent' if primary else 'selected'],fg=palette['accent_text' if primary else 'text'],
        activebackground=palette['selected'],activeforeground=palette['text'],
        disabledforeground=palette['muted'],highlightthickness=1,
        highlightbackground=palette['border'],highlightcolor=palette['accent'],
        font=(_family(master),10),takefocus=True,cursor='hand2',
        height=1)
    button.bind('<Return>',lambda event:button.invoke())
    button.bind('<space>',lambda event:button.invoke())
    button.bind('<FocusIn>',lambda event:button.configure(highlightthickness=2))
    button.bind('<FocusOut>',lambda event:button.configure(highlightthickness=1))
    return button


def _table_style(master,theme):
    p=THEMES[theme];style=ttk.Style(master);prefix='Quota'+theme.title()
    style.configure(prefix+'.Treeview',background=p['panel'],fieldbackground=p['panel'],foreground=p['text'],
        borderwidth=0,rowheight=36,font=(_family(master),10),padding=(0, 2))
    style.map(prefix+'.Treeview',background=[('selected',p['selected'])],foreground=[('selected',p['text'])])
    style.configure(prefix+'.Treeview.Heading',background=p['rail'],foreground=p['muted'],
        font=(_family(master),9,'bold'),relief='flat',padding=(8,8))
    style.map(prefix+'.Treeview.Heading',background=[('active',p['selected'])])
    style.configure(prefix+'.TCombobox',fieldbackground=p['panel'],background=p['panel'],
        foreground=p['text'],arrowcolor=p['text'],padding=(8, 5))
    style.map(prefix+'.TCombobox',fieldbackground=[('readonly',p['panel'])],foreground=[('readonly',p['text'])])
    return prefix


class QuotaWindow(tk.Frame):
    def __init__(self,master,title,palette):
        super().__init__(master,bg=palette['panel'],highlightbackground=palette['border'],highlightthickness=1)
        self.palette=palette;self.value=None;self.cached=True
        _label(self,title,palette,size=10,bold=True).pack(fill='x',padx=14,pady=(12,2))
        self.value_label=_label(self,'Unbekannt',palette,size=19,bold=True)
        self.value_label.pack(fill='x',padx=14,pady=(0,7))
        self.bar=tk.Canvas(self,height=5,bg=palette['border'],bd=0,highlightthickness=0)
        self.bar.pack(fill='x',padx=14);self.bar.bind('<Configure>',lambda event:self._draw_bar())
        self.reset_label=_label(self,'Reset nicht gemeldet',palette,size=9,muted=True)
        self.reset_label.pack(fill='x',padx=14,pady=(9,12))
        self.bind('<Configure>',lambda event:self.reset_label.configure(wraplength=max(100,event.width-28)))

    def set_window(self,window,*,freshness='UNKNOWN'):
        self.cached=freshness!='LIVE_VERIFIED'
        self.value=window.get('used_percent') if isinstance(window,dict) else None
        self.value_label.configure(text=window_text(window,compact=True))
        if not isinstance(window,dict) or window.get('reset_at') is None:
            reset='Reset nicht gemeldet'
        elif window.get('state')=='RESET_TIME_REACHED':
            reset='Resetzeit erreicht. Neue Kapazit\u00e4t nicht best\u00e4tigt.'
        else:
            reset='Reset: '+format_reset(window['reset_at'])+'\n'+format_countdown(window.get('reset_in_seconds'))
        self.reset_label.configure(text=reset)
        self._draw_bar()

    def _draw_bar(self):
        self.bar.delete('all')
        if type(self.value) in (int,float):
            width=self.bar.winfo_width()*min(100,max(0,self.value))/100
            self.bar.create_rectangle(0,0,width,5,fill=self.palette['muted' if self.cached else 'accent'],outline='')


class QuotaPanel(tk.Frame):
    def __init__(self,master,*,theme='dark',on_refresh,on_history):
        self.palette=THEMES[theme];p=self.palette
        super().__init__(master,bg=p['canvas'])
        self.on_refresh=on_refresh;self.on_history=on_history;self.model={'rows':[],'settings':{}}
        self.theme=theme;self.history_window=None;self.sort_by='account';self.selected_key=None
        self.grid_columnconfigure(0,weight=1);self.grid_rowconfigure(3,weight=1)
        prefix=_table_style(self,theme)
        header=tk.Frame(self,bg=p['canvas']);header.grid(row=0,column=0,sticky='ew',pady=(0,12));header.grid_columnconfigure(0,weight=1)
        _label(header,'Konten & Quota-Historie',p,size=19,bold=True).grid(row=0,column=0,sticky='w')
        self.monitor_label=_label(header,'Monitoring pausiert',p,size=9,muted=True)
        self.monitor_label.grid(row=0,column=1,sticky='e',padx=(10,0))
        self.metrics=tk.Frame(self,bg=p['canvas']);self.metrics.grid(row=1,column=0,sticky='ew',pady=(0,14))
        self.metric_cells=[]
        self.metric_labels=[]
        for index,title in enumerate(('Gespeicherte Konten','Live abgefragt','Pr\u00fcfung erforderlich')):
            self.metrics.grid_columnconfigure(index,weight=1,uniform='metrics')
            cell=tk.Frame(self.metrics,bg=p['panel']);cell.grid(row=0,column=index,sticky='ew',padx=(0,10 if index<2 else 0))
            value=_label(cell,'0',p,size=21,bold=True);value.pack(anchor='w',padx=14,pady=(9,0))
            _label(cell,title,p,size=9,muted=True).pack(anchor='w',padx=14,pady=(0,10))
            self.metric_cells.append(cell)
            self.metric_labels.append(value)
        toolbar=tk.Frame(self,bg=p['canvas']);toolbar.grid(row=2,column=0,sticky='ew',pady=(0,9));toolbar.grid_columnconfigure(0,weight=1)
        self.query=tk.StringVar(self);self.status=tk.StringVar(self,value='Alle Konten')
        self.search_entry=tk.Entry(toolbar,textvariable=self.query,bg=p['panel'],fg=p['text'],insertbackground=p['text'],
            relief='flat',highlightthickness=1,highlightbackground=p['border'],highlightcolor=p['accent'],
            font=(_family(self),11),width=16)
        self.search_entry.grid(row=1,column=0,sticky='ew',ipady=7,padx=(0,10))
        _label(toolbar,'Konto, Profil oder Workspace suchen',p,size=9,muted=True).grid(row=0,column=0,sticky='w',pady=(0,4))
        self.filter=ttk.Combobox(toolbar,textvariable=self.status,values=['Alle Konten','Warnung','Zugang entfernt','Pr\u00fcfung n\u00f6tig'],
            state='readonly',width=21,style=prefix+'.TCombobox')
        self.filter.grid(row=1,column=1,sticky='e',ipady=6)
        tablebox=tk.Frame(self,bg=p['panel']);tablebox.grid(row=3,column=0,sticky='nsew')
        tablebox.grid_columnconfigure(0,weight=1);tablebox.grid_rowconfigure(0,weight=1)
        self.table=ttk.Treeview(tablebox,columns=('account','five','week','status','data'),show='headings',height=5,
                                selectmode='browse',style=prefix+'.Treeview')
        for name,title,width in (('account','Konto / Profil',225),('five','5h genutzt',85),('week','7d genutzt',85),
                                 ('status','Status',190),('data','Datenstand',125)):
            self.table.column(name,width=width,minwidth=65,stretch=name=='account',anchor='w')
            self.table.heading(name,text=title,anchor='w',command=lambda n=name:self._sort(n))
        self.table.grid(row=0,column=0,sticky='nsew')
        vertical=ttk.Scrollbar(tablebox,orient='vertical',command=self.table.yview);vertical.grid(row=0,column=1,sticky='ns')
        horizontal=ttk.Scrollbar(tablebox,orient='horizontal',command=self.table.xview);horizontal.grid(row=1,column=0,sticky='ew')
        self.table.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        self.detail=tk.Frame(self,bg=p['canvas']);self.detail.grid(row=4,column=0,sticky='ew',pady=(12,0));self.detail.grid_columnconfigure((0,1),weight=1,uniform='limits')
        self.account_label=_label(self.detail,'Konto ausw\u00e4hlen',p,size=11,bold=True)
        self.account_label.grid(row=0,column=0,columnspan=2,sticky='ew',pady=(0,3))
        self.provenance=_label(self.detail,'Unbekannte Werte sind keine freie Kapazit\u00e4t.',p,size=9,muted=True)
        self.provenance.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(0,9))
        self.primary=QuotaWindow(self.detail,'5-Stunden-Verbrauch',p);self.primary.grid(row=2,column=0,sticky='nsew',padx=(0,5))
        self.secondary=QuotaWindow(self.detail,'Wochenverbrauch',p);self.secondary.grid(row=2,column=1,sticky='nsew',padx=(5,0))
        actions=tk.Frame(self,bg=p['canvas']);actions.grid(row=5,column=0,sticky='ew',pady=(10,0));actions.grid_columnconfigure(0,weight=1)
        self.message=_label(actions,'',p,size=9,muted=True);self.message.grid(row=0,column=0,sticky='w',padx=(0,10))
        self.history_button=_button(actions,'Historie',self._history,p);self.history_button.grid(row=0,column=1,padx=(0,8))
        self.refresh_button=_button(actions,'Jetzt pr\u00fcfen',self._refresh,p,primary=True);self.refresh_button.grid(row=0,column=2)
        self._set_refresh_enabled(False);self.history_button.configure(state='disabled')
        self.query.trace_add('write',lambda *args:self.refresh_rows())
        self.filter.bind('<<ComboboxSelected>>',lambda event:self.refresh_rows())
        self.table.bind('<<TreeviewSelect>>',lambda event:self.select_row())
        self.bind('<Configure>',self._resize)
        self._compact = None
        self._metric_columns = None

    def _resize(self,event):
        if event.widget is self:
            width=max(160,event.width-10)
            self.account_label.configure(wraplength=width);self.provenance.configure(wraplength=width)
            self.message.configure(wraplength=max(90,width-250))
            compact = width < BREAKPOINTS['stack']
            if compact != self._compact:
                self._compact = compact
                self.primary.grid_forget();self.secondary.grid_forget()
                if compact:
                    self.primary.grid(row=2,column=0,columnspan=2,sticky='nsew',padx=0,pady=(0,6))
                    self.secondary.grid(row=3,column=0,columnspan=2,sticky='nsew',padx=0)
                else:
                    self.primary.grid(row=2,column=0,sticky='nsew',padx=(0,5))
                    self.secondary.grid(row=2,column=1,sticky='nsew',padx=(5,0))
            columns = 1 if width < BREAKPOINTS['compact'] else 2 if width < BREAKPOINTS['wide'] else 3
            if columns != self._metric_columns:
                self._metric_columns = columns
                for cell in self.metric_cells:cell.grid_forget()
                for index,cell in enumerate(self.metric_cells):
                    cell.grid(row=index//columns,column=index%columns,sticky='ew',padx=(0,10 if index%columns<columns-1 else 0),pady=(0,6))
                for index in range(3):self.metrics.grid_columnconfigure(index,weight=1 if index<columns else 0,uniform='metrics')

    def _sort(self,column):
        self.sort_by='usage' if column in ('five','week') else 'account'
        self.refresh_rows()

    def set_model(self,model):
        self.model=model
        summary=summarize_rows(model.get('rows',[]))
        for label,key in zip(self.metric_labels,('accounts','live','needs_check')):label.configure(text=str(summary[key]))
        enabled=model.get('settings',{}).get('enabled',False)
        self.monitor_label.configure(text='Monitoring aktiv' if enabled else 'Monitoring pausiert')
        self.refresh_rows()

    def refresh_rows(self):
        selected=self.table.selection();key=selected[0] if selected else self.selected_key
        status={'Alle Konten':'all','Warnung':'warning','Zugang entfernt':'removed','Pr\u00fcfung n\u00f6tig':'check'}.get(self.status.get(),'all')
        rows=filter_rows(self.model.get('rows',[]),query=self.query.get(),status=status,sort_by=self.sort_by)
        self.table.delete(*self.table.get_children())
        for row in rows:
            a,q=row['account'],row['quota'];windows=display_windows(q['windows'])
            self.table.insert('', 'end',iid=a['account_key'],values=(a['profile_id']+' / '+a['email'],
                window_text(windows.get('five_hour'),compact=True),window_text(windows.get('weekly'),compact=True),
                STATUS_TEXT.get(q['status'],'Unbekannt'),FRESHNESS_TEXT.get(q['freshness'],'Unbekannt')))
        if key and self.table.exists(key):self.table.selection_set(key)
        elif rows:self.table.selection_set(rows[0]['account']['account_key'])
        self.select_row()
        if self.selected_key:self.table.see(self.selected_key)

    def _set_refresh_enabled(self,enabled):
        self.refresh_button.configure(state='normal' if enabled else 'disabled',
            bg=self.palette['accent' if enabled else 'selected'])

    def select_row(self):
        selected=self.table.selection();self.selected_key=selected[0] if selected else None
        row=next((r for r in self.model.get('rows',[]) if r['account']['account_key']==self.selected_key),None)
        if row is None:
            self.account_label.configure(text='Keine passenden Konten' if self.model.get('rows') else 'Noch keine gespeicherten Anmeldungen')
            self.provenance.configure(text='Unter Konten eine offizielle Anmeldung hinzuf\u00fcgen; die Historie bleibt danach lokal erhalten.')
            self.primary.set_window(None);self.secondary.set_window(None)
            self._set_refresh_enabled(False);self.history_button.configure(state='disabled');return
        a,q=row['account'],row['quota'];windows=display_windows(q['windows'])
        self.account_label.configure(text=a['email']+'  /  '+a['profile_id'])
        access=ACCESS_TEXT.get(a.get('membership_state'),'Zugang unbekannt')
        observed=format_reset(q.get('observed_at'))
        self.provenance.configure(text=f'{access}  |  {FRESHNESS_TEXT.get(q["freshness"],"Unbekannt")}  |  Letzte Messung: {observed}')
        self.primary.set_window(windows.get('five_hour'),freshness=q['freshness'])
        self.secondary.set_window(windows.get('weekly'),freshness=q['freshness'])
        refresh=row.get('binding_available',False) and a.get('membership_state') not in REMOVED
        self._set_refresh_enabled(refresh);self.history_button.configure(state='normal')
        error=a.get('last_error_code')
        message=ERROR_TEXT.get(error,'Abfrage fehlgeschlagen.') if error else ('Profil nicht mehr vorhanden; Historie erhalten.' if not row.get('binding_available',False) else 'Historische Werte werden nicht zur\u00fcckgesetzt.')
        if row.get('polling',{}).get('suspended'):message='Abfragen pausiert. Mit Jetzt pr\u00fcfen erneut versuchen.'
        self.message.configure(text=message)

    def _refresh(self):
        if self.selected_key:self.on_refresh(self.selected_key)

    def _history(self):
        if self.selected_key:self.on_history(self.selected_key,0)

    def show_history(self,key,rows,offset=0):
        if self.history_window is not None and self.history_window.winfo_exists():self.history_window.destroy()
        p=self.palette;window=tk.Toplevel(self);self.history_window=window
        window.title('MultiCodex / gespeicherte Quota-Messungen');window.geometry('880x480');window.minsize(620,360);window.configure(bg=p['canvas'])
        window.grid_columnconfigure(0,weight=1);window.grid_rowconfigure(2,weight=1)
        _label(window,'Quota-Historie',p,size=20,bold=True).grid(row=0,column=0,sticky='w',padx=20,pady=(18,4))
        caption=_label(window,'Unver\u00e4nderte Messungen. Ein Reset-Countdown ist keine neue Messung.',p,muted=True)
        caption.grid(row=1,column=0,sticky='ew',padx=20,pady=(0,14))
        window.bind('<Configure>',lambda event:caption.configure(wraplength=max(180,event.width-40)) if event.widget is window else None)
        box=tk.Frame(window,bg=p['canvas']);box.grid(row=2,column=0,sticky='nsew',padx=20)
        box.grid_columnconfigure(0,weight=1);box.grid_rowconfigure(0,weight=1)
        tree=ttk.Treeview(box,columns=('time','primary','secondary','plan','access'),show='headings',style=_table_style(self,self.theme)+'.Treeview')
        for name,title,width in (('time','Gemessen',195),('primary','Prim\u00e4res Fenster',130),('secondary','Sekund\u00e4res Fenster',145),('plan','Plan',100),('access','Zugang bei Messung',180)):
            tree.heading(name,text=title);tree.column(name,width=width,minwidth=80)
        tree.grid(row=0,column=0,sticky='nsew')
        scroll=ttk.Scrollbar(box,command=tree.yview);scroll.grid(row=0,column=1,sticky='ns');tree.configure(yscrollcommand=scroll.set)
        horizontal=ttk.Scrollbar(box,orient='horizontal',command=tree.xview);horizontal.grid(row=1,column=0,sticky='ew');tree.configure(xscrollcommand=horizontal.set)
        for row in rows:
            def value(slot):
                used=row.get(slot+'_used_percent');duration=row.get(slot+'_duration_minutes')
                return 'Unbekannt' if used is None else f'{used:g} % / {duration or "?"} min'
            tree.insert('','end',values=(format_reset(row['observed_at']),value('primary'),value('secondary'),row.get('plan_type') or 'Unbekannt',ACCESS_TEXT.get(row.get('access_state'),'Unbekannt')))
        actions=tk.Frame(window,bg=p['canvas']);actions.grid(row=3,column=0,sticky='ew',padx=20,pady=15)
        _label(actions,f'Messungen {offset+1 if rows else 0}\u2013{offset+len(rows)}',p,muted=True).pack(side='left')
        next_button=_button(actions,'\u00c4ltere',lambda:self.on_history(key,offset+100),p);next_button.pack(side='right')
        prev_button=_button(actions,'Neuere',lambda:self.on_history(key,max(0,offset-100)),p);prev_button.pack(side='right',padx=8)
        if len(rows)<100:next_button.configure(state='disabled')
        if offset==0:prev_button.configure(state='disabled')

    def destroy(self):
        if self.history_window is not None and self.history_window.winfo_exists():self.history_window.destroy()
        super().destroy()


class QuotaSettingsPanel(tk.Frame):
    def __init__(self,master,*,theme='dark',model,on_save):
        p=THEMES[theme];self.palette=p;self.model=model;self.on_save=on_save
        super().__init__(master,bg=p['panel'],padx=20,pady=18)
        self.grid_columnconfigure(1,weight=1)
        _label(self,'Quota-Monitoring',p,size=17,bold=True).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,12))
        data=model.get('settings',{})
        self.enabled=tk.BooleanVar(self,value=data.get('enabled',False))
        toggle=tk.Checkbutton(self,text='Automatisch im Hintergrund aktualisieren',variable=self.enabled,
            bg=p['panel'],fg=p['text'],activebackground=p['panel'],activeforeground=p['text'],
            selectcolor=p['canvas'],highlightcolor=p['accent'],font=(_family(self),11))
        toggle.grid(row=1,column=0,columnspan=2,sticky='w',pady=(0,12))
        self.interval=tk.StringVar(self,value=str(data.get('poll_interval_seconds',60)))
        self.threshold=tk.StringVar(self,value=str(data.get('warning_threshold_percent',90)))
        self.retries=tk.StringVar(self,value=str(data.get('maximum_retries',3)))
        self.cooldown=tk.StringVar(self,value=str(data.get('cooldown_seconds',300)))
        for row,(title,var) in enumerate((('Abfrageintervall (Sekunden)',self.interval),('Warnschwelle (% verwendet)',self.threshold),('Fehler bis zur Pause',self.retries),('Maximale Retry-Pause (Sekunden)',self.cooldown)),start=2):
            _label(self,title,p).grid(row=row,column=0,sticky='w',pady=5,padx=(0,15))
            entry=tk.Entry(self,textvariable=var,bg=p['canvas'],fg=p['text'],insertbackground=p['text'],
                relief='flat',highlightthickness=1,highlightcolor=p['accent'],highlightbackground=p['border'],width=12,font=(_family(self),11))
            entry.grid(row=row,column=1,sticky='w',ipady=5,pady=5)
        _label(self,'Freigegebene Profile',p,bold=True).grid(row=6,column=0,columnspan=2,sticky='w',pady=(14,5))
        allowed=data.get('allowed_profiles',[]);self.profile_names=sorted(set(model.get('profiles',[]))|set(allowed),key=str.casefold)
        self.profile_list=tk.Listbox(self,selectmode='multiple',exportselection=False,height=4,
            bg=p['canvas'],fg=p['text'],selectbackground=p['selected'],selectforeground=p['text'],
            highlightbackground=p['border'],highlightcolor=p['accent'],font=(_family(self),10))
        self.profile_list.grid(row=7,column=0,columnspan=2,sticky='ew')
        for i,name in enumerate(self.profile_names):
            self.profile_list.insert('end',name)
            if name in allowed:self.profile_list.selection_set(i)
        note='Kein automatischer Konto- oder Seat-Wechsel: Workspace- und Desktop-Verifikation sind noch nicht angebunden. Laufende Instanzen bleiben offen.'
        self.note=_label(self,note,p,size=9,muted=True,wraplength=550)
        self.note.grid(row=8,column=0,columnspan=2,sticky='ew',pady=(12,10))
        self.save_button=_button(self,'Monitoring speichern',self.save,p,primary=True);self.save_button.grid(row=9,column=0,sticky='w')
        self.message=_label(self,'',p,size=9,muted=True,wraplength=300);self.message.grid(row=9,column=1,sticky='w',padx=12)
        self.bind('<Configure>',lambda e:self.note.configure(wraplength=max(200,e.width-40)) if e.widget is self else None)

    def save(self):
        try:
            data=validate_settings({**self.model.get('settings',{}),'enabled':self.enabled.get(),
                'poll_interval_seconds':int(self.interval.get()),'warning_threshold_percent':float(self.threshold.get()),
                'maximum_retries':int(self.retries.get()),'cooldown_seconds':int(self.cooldown.get()),
                'allowed_profiles':[self.profile_names[i] for i in self.profile_list.curselection()]})
        except (ValueError,SettingsError):
            self.message.configure(text='Werte pr\u00fcfen: Intervall 30\u20133600, Schwelle > 0 bis 100, Versuche 1\u201310.');return
        self.message.configure(text='Speichern angefordert; Best\u00e4tigung folgt vom Backend.')
        self.on_save(data)

