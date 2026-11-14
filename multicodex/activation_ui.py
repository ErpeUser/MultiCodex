"""Render exact-account start requests; callbacks own all I/O and mutations."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from .quota_ui import _label, _button, _table_style
from .ui_tokens import THEMES

STATE_TEXT = {
    'QUEUED': 'Start vorgemerkt', 'CHECKING_TARGET': 'Anmeldung wird gepr\u00fcft',
    'WAITING_FOR_RESET': 'Wartet auf best\u00e4tigte Kapazit\u00e4t',
    'VERIFICATION_REQUIRED': 'Neue Quota-Pr\u00fcfung erforderlich',
    'AUTHENTICATION_REQUIRED': 'Erneute Anmeldung erforderlich',
    'ACTIVATING_TARGET': 'Profil wird gestartet', 'VERIFYING_INSTANCE': 'Start wird gepr\u00fcft',
    'PAUSED': 'Pausiert', 'FAILED': 'Fehlgeschlagen', 'CANCELLED': 'Abgebrochen',
    'ROLLBACK_REQUIRED': 'Wiederherstellung erforderlich', 'COMPLETED': 'Start und Zuordnung gepr\u00fcft',
}

class ActivationPanel(tk.Frame):
    def __init__(self, master, *, on_enqueue, on_action, on_enabled, theme='dark'):
        p = THEMES[theme]
        super().__init__(master, bg=p['panel'])
        self.on_enqueue, self.on_action, self.on_enabled = on_enqueue, on_action, on_enabled
        self.keys, self.runs = [], {}
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)
        _label(self, 'Geplanter Profilstart', p, size=16, bold=True).grid(
            row=0, column=0, sticky='w', padx=16, pady=(16, 4))
        self.enabled = tk.BooleanVar(self, value=False)
        self.toggle = tk.Checkbutton(self, text='Startauftr\u00e4ge ausf\u00fchren', variable=self.enabled,
            command=lambda: self.on_enabled(bool(self.enabled.get())), bg=p['panel'], fg=p['text'],
            activebackground=p['panel'], activeforeground=p['text'], selectcolor=p['selected'])
        self.toggle.grid(row=1, column=0, sticky='w', padx=12)
        note = _label(self, 'Nur das ausgew\u00e4hlte Konto wird gestartet. Laufende Fenster bleiben offen.\n'
            'Fehlt Kapazit\u00e4t, wartet derselbe Auftrag auf eine erneute offizielle Pr\u00fcfung.', p, muted=True)
        note.grid(row=2, column=0, sticky='ew', padx=16, pady=(4, 10))
        note.bind('<Configure>', lambda e: note.configure(wraplength=max(180, e.width)))
        controls = tk.Frame(self, bg=p['panel'])
        controls.grid(row=3, column=0, sticky='ew', padx=16, pady=(0, 12))
        controls.grid_columnconfigure(0, weight=1)
        prefix = _table_style(self, theme)
        self.target = ttk.Combobox(controls, state='readonly', style=prefix+'.TCombobox')
        self.target.grid(row=0, column=0, sticky='ew', padx=(0, 8), ipady=5)
        self.enqueue_button = _button(controls, 'Profilstart vormerken', self.enqueue, p, primary=True)
        self.enqueue_button.grid(row=0, column=1)
        self.tree = ttk.Treeview(self, columns=('profile', 'state'), show='headings',
            height=4, selectmode='browse', style=prefix+'.Treeview')
        self.tree.heading('profile', text='Profil / Anmeldung', anchor='w')
        self.tree.heading('state', text='Auftragsstatus', anchor='w')
        self.tree.column('profile', width=190, minwidth=100)
        self.tree.column('state', width=320, minwidth=140)
        self.tree.grid(row=4, column=0, sticky='nsew', padx=(16, 30))
        scroll = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        scroll.grid(row=4, column=0, sticky='nse', padx=(0, 12))
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<<TreeviewSelect>>', lambda e: self.selected())
        self.detail = _label(self, 'Auftrag ausw\u00e4hlen.', p, muted=True)
        self.detail.grid(row=5, column=0, sticky='ew', padx=16, pady=(8, 0))
        self.detail.bind('<Configure>', lambda e: self.detail.configure(wraplength=max(200,e.width)))
        actions = tk.Frame(self, bg=p['panel'])
        actions.grid(row=6, column=0, sticky='ew', padx=16, pady=12)
        self.cancel_button = _button(actions, 'Auftrag abbrechen', lambda: self.action('cancel'), p)
        self.resume_button = _button(actions, 'Erneut pr\u00fcfen', lambda: self.action('resume'), p)
        self.recover_button = _button(actions, 'Zuordnung wiederherstellen', lambda: self.action('recover'), p)
        for i, button in enumerate((self.cancel_button, self.resume_button, self.recover_button)):
            button.grid(row=i//2, column=i%2, sticky='ew', padx=(0, 8), pady=3)
        actions.grid_columnconfigure((0, 1), weight=1)
        self.selected()

    def enqueue(self):
        index = self.target.current()
        if self.enabled.get() and 0 <= index < len(self.keys):
            self.on_enqueue(self.keys[index])

    def action(self, action):
        ids = self.tree.selection()
        button = {'cancel': self.cancel_button, 'resume': self.resume_button, 'recover': self.recover_button}[action]
        if ids and str(button['state']) != 'disabled': self.on_action(ids[0], action)

    def selected(self):
        ids = self.tree.selection()
        run = self.runs.get(ids[0], {}) if ids else {}
        state = run.get('state')
        safe = run.get('old_session') is None
        self.cancel_button.configure(state='normal' if safe and state in {
            'QUEUED', 'WAITING_FOR_RESET', 'VERIFICATION_REQUIRED', 'AUTHENTICATION_REQUIRED', 'PAUSED'} else 'disabled')
        self.resume_button.configure(state='normal' if safe and state in {
            'PAUSED', 'AUTHENTICATION_REQUIRED', 'FAILED'} else 'disabled')
        self.recover_button.configure(state='normal' if state == 'ROLLBACK_REQUIRED' else 'disabled')
        details = {'BUSY': 'Die laufende Instanz bleibt offen. Vor einem Wechsel selbst schlie\u00dfen.',
            'AUTH_REQUIRED': 'Unter Konten regul\u00e4r erneut anmelden.',
            'NOT_ALLOWLISTED': 'Profil zuerst in den Einstellungen freigeben.',
            'QUOTA_UNAVAILABLE': 'Derselbe Account wartet auf eine neue offizielle Quota-Pr\u00fcfung.',
            'PROCESS_UNVERIFIED': 'Prozesszuordnung nicht best\u00e4tigt. Unter Diagnose pr\u00fcfen.',
            'CONTEXT_CHANGED': 'Kontokontext ge\u00e4ndert. Anmeldung und Zugang erneut pr\u00fcfen.',
            'RETRY_LIMIT': 'Wiederholungsgrenze erreicht. Verbindung pr\u00fcfen und erneut versuchen.',
            'INTERRUPTED': 'Vorgang unterbrochen. Ge\u00e4nderte Zuordnung erst nach Fensterabschluss wiederherstellen.'}
        self.detail.configure(text=details.get(run.get('error_code'),
            'Startzuordnung gepr\u00fcft; Fensterfokus nicht best\u00e4tigt.' if state=='COMPLETED' and not run.get('foreground') else
            'Auftrag ausw\u00e4hlen.' if not run else 'Historische Quotas und Anmeldedaten bleiben erhalten.'))

    def set_model(self, model):
        config = model.get('settings', {})
        active = config.get('automatic_activation_enabled') is True
        self.enabled.set(active)
        index = self.target.current()
        old_key = self.keys[index] if 0 <= index < len(self.keys) else None
        allowed = config.get('allowed_profiles', [])
        rows = [r for r in model.get('rows', []) if r.get('binding_available') is True
                and r['account']['profile_id'] in allowed]
        self.keys = [r['account']['account_key'] for r in rows]
        self.target.configure(values=[r['account']['profile_id']+' | '+r['account']['email']+
            ' | '+r['account']['session_id'][:8] for r in rows])
        if self.keys: self.target.current(self.keys.index(old_key) if old_key in self.keys else 0)
        else: self.target.set('')
        self.enqueue_button.configure(state='normal' if active and self.keys else 'disabled')
        selection = self.tree.selection()
        self.runs = {r['run_id']: r for r in model.get('activation_runs', [])}
        self.tree.delete(*self.tree.get_children())
        for ident, row in self.runs.items():
            self.tree.insert('', 'end', iid=ident, values=(row['profile']+' / '+row['session_id'][:8],
                STATE_TEXT.get(row['state'], 'Unbekannt')))
        if selection and selection[0] in self.runs: self.tree.selection_set(selection[0])
        self.selected()
