"""Explicit read-only directory checks; key exists only for the requested read."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from .quota_ui import _label, _button, _table_style
from .ui_tokens import THEMES

class WorkspacePanel(tk.Frame):
    def __init__(self, master, *, on_read, theme='dark'):
        p=THEMES[theme]
        super().__init__(master,bg=p['panel'])
        self.on_read=on_read;self.grid_columnconfigure(0,weight=1)
        _label(self,'Workspace-Mitglieder pr\u00fcfen',p,size=16,bold=True).grid(
            row=0,column=0,sticky='w',padx=16,pady=(16,5))
        note=_label(self,'Nur lesend. Erfordert einen berechtigten Workspace-Admin-Key.\n'
            'Der Schl\u00fcssel wird nicht gespeichert. Mitglieder, Rollen und Seats bleiben unver\u00e4ndert.',p,muted=True)
        note.grid(row=1,column=0,sticky='ew',padx=16,pady=(0,10))
        note.bind('<Configure>',lambda e:note.configure(wraplength=max(200,e.width)))
        form=tk.Frame(self,bg=p['panel']);form.grid(row=2,column=0,sticky='ew',padx=16)
        form.grid_columnconfigure(1,weight=1)
        _label(form,'Workspace-ID',p).grid(row=0,column=0,sticky='w',padx=(0,10))
        self.workspace=tk.Entry(form,bg=p['canvas'],fg=p['text'],insertbackground=p['text'],width=30)
        self.workspace.grid(row=0,column=1,sticky='ew',ipady=6,pady=4)
        _label(form,'Admin-Key (nur f\u00fcr diese Abfrage)',p).grid(row=1,column=0,sticky='w',padx=(0,10))
        self.key=tk.Entry(form,show='*',bg=p['canvas'],fg=p['text'],insertbackground=p['text'],width=30)
        self.key.grid(row=1,column=1,sticky='ew',ipady=6,pady=4)
        self.read_button=_button(form,'Mitglieder lesen',self.read,p,primary=True)
        self.read_button.grid(row=2,column=1,sticky='e',pady=(8,12))
        self.message=_label(self,'Noch keine Workspace-Mitglieder abgefragt.',p,muted=True)
        self.message.grid(row=3,column=0,sticky='ew',padx=16,pady=(0,8))
        prefix=_table_style(self,theme)
        self.tree=ttk.Treeview(self,columns=('email','id'),show='headings',height=4,style=prefix+'.Treeview')
        self.tree.heading('email',text='E-Mail',anchor='w');self.tree.heading('id',text='Workspace-Benutzer-ID',anchor='w')
        self.tree.column('email',width=260);self.tree.column('id',width=220)
        self.tree.grid(row=4,column=0,sticky='nsew',padx=(16,30),pady=(0,16))
        scroll=ttk.Scrollbar(self,orient='vertical',command=self.tree.yview)
        scroll.grid(row=4,column=0,sticky='nse',padx=(0,12),pady=(0,16))
        self.tree.configure(yscrollcommand=scroll.set)
        self.grid_rowconfigure(4,weight=1)

    def read(self):
        workspace,key=self.workspace.get().strip(),self.key.get()
        self.key.delete(0,'end')
        if not workspace or not key:
            self.message.configure(text='Workspace-ID und Admin-Key sind erforderlich.')
            return
        self.message.configure(text='Abfrage angefordert; vorhandene Daten sind noch nicht aktualisiert.')
        self.on_read(workspace,key)

    def set_model(self,model):
        self.tree.delete(*self.tree.get_children())
        for row in model.get('members',[]):
            self.tree.insert('','end',iid=row['id'],values=(row['email'] or 'Nicht gemeldet',row['id']))
        self.message.configure(text=str(len(model.get('members',[])))+' Mitglieder gelesen. Workspace: '+model['workspace_id'])

    def set_error(self,code):
        explanation={'PERMISSION_DENIED':'Berechtigung oder Workspace-Verf\u00fcgbarkeit pr\u00fcfen.',
            'AUTH_REQUIRED':'Admin-Key abgelaufen oder ung\u00fcltig.', 'RATE_LIMITED':'Abfragelimit erreicht.',
            'CANCELLED':'Abfrage abgebrochen.'}.get(code,'Verbindung und Konfiguration pr\u00fcfen.')
        self.message.configure(text='Abfrage fehlgeschlagen; Anzeige nicht aktuell. '+explanation)
