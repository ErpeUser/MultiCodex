"""Native desktop interface. Worker services own I/O; Tk owns every widget."""
from __future__ import annotations

import gc
import os
import queue
import threading
import time
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .account_bridge import AccountBridge
from .application import ApplicationServices, user_error, usage_lines
from .codex_client import CodexAccountService, validate_login_url
from .discovery import default_legacy_roots, discover_legacy_profiles
from .jobs import JobRunner, JobBusy
from .profiles import ProfileStore
from .runtime import LocalInstances
from .settings import SettingsStore
from .ui_tokens import (THEMES, PADDING, RADIUS, NAV_WIDTH, BREAKPOINTS, CONTROL_HEIGHT,
                         SPACING, TEXT_SIZE)
from . import __version__
from .quota_gui import QuotaGuiController
from .workspace_admin_gui import WorkspaceAdminGuiController
from .desktop_views import ActionTable, MetricStrip, dashboard_metrics, profile_records, session_records

PAGES = ['Overview', 'Accounts', 'Instances', 'Usage', 'Diagnostics', 'Settings']
LABELS = dict(zip(PAGES, ['\u00dcbersicht', 'Konten', 'Instanzen', 'Nutzung', 'Diagnose', 'Einstellungen']))
FIGMA_URL = 'https://www.figma.com/design/iKeNG6k7TfG5U98yfqKFxI'


class MultiCodexApp(ctk.CTk):
    def __init__(self, *, data_dir: Path | None = None, auto_start: bool = True):
        local = os.environ.get('LOCALAPPDATA') or str(Path.home()/'.local'/'share')
        root = data_dir or Path(local)/'MultiCodex'
        self.settings = SettingsStore(root)
        self.theme_name = self.settings.load()['theme']
        ctk.set_appearance_mode(self.theme_name)
        super().__init__()
        self.title('MultiCodex ' + __version__)
        self.geometry('1180x760')
        self.minsize(900, 640)
        self.palette = THEMES[self.theme_name]
        self.store = ProfileStore(root/'profiles')
        self.services = ApplicationServices(self.store, LocalInstances(self.store), CodexAccountService())
        self.accounts = AccountBridge()
        self.view = {'profiles': [], 'processes': {}, 'sessions': {}, 'recovery': {}, 'issues': []}
        self.pool_rows = None
        self.pool_error = None
        self.health_data = None
        self.legacy_rows = None
        self.usage_data = None
        self.usage_profile = None
        self.jobs = JobRunner()
        self.callbacks = {}
        self.mutating = False
        self.closing = False
        self.login_cancel = None
        self.login_events = queue.Queue(maxsize=16)
        self.login_url = None
        self.login_profile = None
        self.login_browser_opened = False
        self._browser_lock = threading.Lock()
        self.page = 'Overview'
        self._poll_id = None
        self._refresh_id = None
        self._progress_running = False
        self.quota = QuotaGuiController(self, root)
        self.admin = WorkspaceAdminGuiController(self, root)
        self.account_section = 'profiles'
        self.usage_section = 'history'
        self.settings_section = 'general'
        self.diagnostics_section = 'runtime'
        self.snapshot_ready = False
        self.table_states = {}
        self.data_tables = {}
        self.metrics = None
        self._build_shell()
        self.bind('<Configure>', self._resize_shell)
        self._render()
        self.protocol('WM_DELETE_WINDOW', self._close)
        self.bind('<Control-r>', lambda event: self._refresh(include_pool=True))
        self.bind('<Escape>', lambda event: self._cancel_login())
        for index, page in enumerate(PAGES, 1):
            self.bind('<Control-Key-' + str(index) + '>', lambda event, page=page: self._set_page(page))
        # Tk font/widget cycles can otherwise be collected during a worker's
        # allocations; their finalizers call Tcl and must stay on this thread.
        self._gc_was_enabled = gc.isenabled()
        gc.disable()
        self._gc_id = self.after(1000, self._collect_garbage)
        self._poll_id = self.after(100, self._poll_results)
        if auto_start:
            self._refresh(include_pool=True)
            self._discover()
            self._refresh_id = self.after(3000, self._periodic_refresh)

    def _collect_garbage(self):
        self._gc_id = None
        gc.collect()
        if not self.closing:
            self._gc_id = self.after(1000, self._collect_garbage)

    def destroy(self):
        admin = self.__dict__.get('admin')
        if admin is not None:
            admin.close()
        quota = self.__dict__.get('quota')
        if quota is not None:
            quota.close()
        identity = self.__dict__.get('_gc_id')
        if identity is not None:
            self.after_cancel(identity)
            self._gc_id = None
        try:
            super().destroy()
        finally:
            gc.collect()
            if self.__dict__.pop('_gc_was_enabled', False):
                gc.enable()

    def _build_shell(self):
        p = self.palette
        self.nav_buttons = {}
        self.action_buttons = []
        self.configure(fg_color=p['canvas'])
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.rail = ctk.CTkFrame(self, width=NAV_WIDTH, corner_radius=0, fg_color=p['rail'])
        self.rail.grid(row=0, column=0, sticky='nsew')
        self.rail.grid_propagate(False)
        ctk.CTkLabel(self.rail, text='MultiCodex', text_color=p['text'],
                     font=ctk.CTkFont(family='Segoe UI', size=21, weight='bold')).pack(anchor='w', padx=SPACING['xl'], pady=(28, 5))
        ctk.CTkLabel(self.rail, text='Lokale Kontoverwaltung', text_color=p['muted']).pack(anchor='w', padx=SPACING['xl'], pady=(0, 30))
        for key in PAGES:
            button = ctk.CTkButton(self.rail, text=LABELS[key], anchor='w', height=CONTROL_HEIGHT['default'],
                fg_color='transparent', hover_color=p['selected'], text_color=p['text'],
                command=lambda key=key: self._set_page(key))
            button.pack(fill='x', padx=14, pady=4)
            self._keyboard_button(button)
            self.nav_buttons[key] = button
        ctk.CTkLabel(self.rail, text='Entwicklungsstand\nKeine Cloud-Synchronisierung', text_color=p['muted'],
                     justify='left', font=ctk.CTkFont(size=TEXT_SIZE['label'])).pack(side='bottom', padx=SPACING['xl'], pady=SPACING['xl'])
        self.right = ctk.CTkFrame(self, fg_color=p['canvas'], corner_radius=0)
        self.right.grid(row=0, column=1, sticky='nsew')
        self.right.grid_columnconfigure(0, weight=1)
        self.right.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self.right, fg_color='transparent')
        header.grid(row=0, column=0, sticky='ew', padx=SPACING['xxl'], pady=(25, 12))
        header.grid_columnconfigure(0, weight=1)
        self.header_title = ctk.CTkLabel(header, text='', text_color=p['text'],
            font=ctk.CTkFont(family='Segoe UI', size=TEXT_SIZE['title'], weight='bold'), anchor='w')
        self.header_title.grid(row=0, column=0, sticky='w')
        self.header_subtitle = ctk.CTkLabel(header, text='', text_color=p['muted'],
            justify='left', wraplength=420, anchor='w')
        self.header_subtitle.grid(row=1, column=0, sticky='w', pady=(5, 0))
        self.primary = ctk.CTkButton(header, text='Neue Instanz', width=140, height=CONTROL_HEIGHT['primary'],
            fg_color=p['accent'], hover_color=p['selected'], text_color=p['accent_text'], command=self._new_profile)
        self.primary.grid(row=0, column=1, rowspan=2, padx=(12, 0))
        self._keyboard_button(self.primary)
        self.sign_in_button = ctk.CTkButton(header, text='Anmelden', width=110, height=34,
            fg_color=p['selected'], text_color=p['text'], hover_color=p['border'],
            command=lambda: self._set_account_section('profiles'))
        self.sign_in_button.grid(row=2, column=1, sticky='e', pady=(8, 0))
        self._keyboard_button(self.sign_in_button)
        self.page_frame = ctk.CTkScrollableFrame(self.right, fg_color='transparent')
        self.page_frame.grid(row=1, column=0, sticky='nsew', padx=SPACING['xl'], pady=4)
        footer = ctk.CTkFrame(self.right, fg_color='transparent')
        footer.grid(row=2, column=0, sticky='ew', padx=SPACING['xxl'], pady=(5, 14))
        footer.grid_columnconfigure(0, weight=1)
        self.progress = ctk.CTkProgressBar(footer, height=3, mode='indeterminate', progress_color=p['accent'])
        self.progress.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 9))
        self.progress.set(0)
        self.progress.grid_remove()
        self.status_bar = ctk.CTkLabel(footer, text='Bereit', text_color=p['muted'],
            anchor='w', justify='left', wraplength=530)
        self.status_bar.grid(row=1, column=0, sticky='w')
        self.cancel_button = ctk.CTkButton(footer, text='Anmeldung abbrechen', width=150,
            fg_color=p['selected'], text_color=p['text'], command=self._cancel_login, state='disabled')
        self.cancel_button.grid(row=1, column=1, padx=(10, 0))
        self.cancel_button.grid_remove()
        self._keyboard_button(self.cancel_button)

    def _resize_shell(self, event):
        """Keep German copy and the primary action legible at compact widths."""
        if event.widget is not self or not hasattr(self, 'header_subtitle'):
            return
        available=max(260,event.width-NAV_WIDTH-SPACING['xxl']*2)
        self.header_subtitle.configure(wraplength=max(260,min(520,available-170)))
        self.status_bar.configure(wraplength=max(220,min(560,available-170)))
        inset=SPACING['lg'] if event.width < 1000 else SPACING['xl']
        self.page_frame.grid_configure(padx=inset)

    def _keyboard_button(self, button):
        button.bind('<Return>', lambda event: button.invoke())
        button.bind('<space>', lambda event: button.invoke())
        # CTkButton has no native Tk highlight ring.  A temporary accent
        # border keeps keyboard focus visible in both themes and disappears
        # when focus leaves the control.
        button.bind('<FocusIn>', lambda event: button.configure(
            border_width=2, border_color=self.palette['accent']))
        button.bind('<FocusOut>', lambda event: button.configure(border_width=0))

    def _set_page(self, page):
        if not self.closing:
            self.page = page
            self._render()

    def _render(self):
        self._remember_tables()
        self.data_tables = {}
        self.metrics = None
        self.action_buttons = []
        titles = {**LABELS, 'Overview': 'Konten und Instanzen', 'Usage': 'Nutzungslimits'}
        subtitles = {
            'Overview': 'Getrennte Profile. Nur die ausgew\u00e4hlte Instanz wird neu gestartet.',
            'Accounts': 'Gespeicherte Anmeldungen je Profil; der vorhandene globale Pool bleibt unver\u00e4ndert.',
            'Instances': 'Start und Ende werden anhand des konkreten Profilpfads gepr\u00fcft.',
            'Usage': 'Live-Messungen, gespeicherte Historie und getrennte Reset-Zeiten.',
            'Diagnostics': 'Fehlerzust\u00e4nde und offene Wiederherstellungen, ohne Zugangsdaten.',
            'Settings': 'Darstellung, Monitoring und lokaler Speicher. Keine Zugangsdaten in Einstellungen.',
        }
        self.header_title.configure(text=titles[self.page])
        self.header_subtitle.configure(text=subtitles[self.page])
        create = self.page in ('Overview', 'Instances')
        self.primary.configure(text='Neue Instanz' if create else 'Aktualisieren',
            command=self._new_profile if create else lambda: self._refresh(include_pool=True))
        for key, button in self.nav_buttons.items():
            button.configure(fg_color=self.palette['selected'] if key == self.page else 'transparent')
        for child in self.page_frame.winfo_children():
            child.destroy()
        getattr(self, '_page_' + self.page.lower())()
        self._busy_state()

    def _panel(self, title, subtitle=None):
        card = ctk.CTkFrame(self.page_frame, fg_color=self.palette['panel'], corner_radius=RADIUS)
        card.pack(fill='x', padx=7, pady=(6, 14))
        ctk.CTkLabel(card, text=title, text_color=self.palette['text'],
            font=ctk.CTkFont(size=17, weight='bold')).pack(anchor='w', padx=PADDING, pady=(16, 7))
        if subtitle:
            self._line(card, subtitle, muted=True)
        return card

    def _line(self, parent, text, *, muted=False):
        label = ctk.CTkLabel(parent, text=text, text_color=self.palette['muted' if muted else 'text'],
            wraplength=max(260, self.winfo_width()-NAV_WIDTH-140), justify='left', anchor='w')
        label.pack(fill='x', padx=PADDING, pady=(2, 10))
        label.bind('<Configure>', lambda event: label.configure(wraplength=max(240,event.width-4)))
        return label

    def _actions(self, parent, items):
        """Wrap controls naturally at two columns instead of squeezing long labels."""
        row = ctk.CTkFrame(parent, fg_color='transparent')
        row.pack(fill='x', padx=PADDING, pady=(5, 14))
        row.grid_columnconfigure((0, 1), weight=1)
        buttons=[]
        for index, (text, command) in enumerate(items):
            button = ctk.CTkButton(row, text=text, height=34,
                fg_color=self.palette['selected'], text_color=self.palette['text'],
                hover_color=self.palette['border'], command=command)
            button.grid(row=index//2, column=index%2, sticky='ew', padx=(0, 8), pady=4)
            self._keyboard_button(button)
            self.action_buttons.append(button)
            buttons.append(button)
        row._multicodex_action_columns=2
        def reflow(event):
            columns=1 if event.width < BREAKPOINTS['compact'] else 2
            if columns == row._multicodex_action_columns:
                return
            row._multicodex_action_columns=columns
            for column in range(2):row.grid_columnconfigure(column,weight=1 if column<columns else 0)
            for index,button in enumerate(buttons):
                button.grid_forget()
                button.grid(row=index//columns,column=index%columns,sticky='ew',padx=(0,8) if index%columns==0 else 0,pady=4)
        row.bind('<Configure>', reflow)

    def _page_overview(self):
        self.metrics = MetricStrip(self.page_frame,
            dashboard_metrics(self.view, self.quota.model, loaded=self.snapshot_ready), theme=self.theme_name)
        self.metrics.pack(fill='x', padx=7, pady=(6, 4))
        if os.name != 'nt':
            card = self._panel('Desktop-Plattform')
            self._line(card, 'Desktop-Instanzen ben\u00f6tigen Windows. Diese Umgebung best\u00e4tigt nur die Verwaltungsoberfl\u00e4che.', muted=True)
        self.quota.summary()
        self._draw_profiles()
        if self.view['issues']:
            card = self._panel('Pr\u00fcfung erforderlich')
            self._line(card, 'Profil- oder Prozessdaten sind teilweise nicht lesbar. Bestehende Daten bleiben erhalten.')
            self._actions(card, [('Diagnose \u00f6ffnen', lambda: self._set_page('Diagnostics'))])
        if self.snapshot_ready and not self.view['profiles']:
            card = self._panel('Erste Instanz einrichten', 'Bestehende Anmeldungen werden weder kopiert noch gel\u00f6scht.')
            self._actions(card, [('Neue Instanz', self._new_profile), ('Profil verkn\u00fcpfen', self._link_profile)])

    def _draw_profiles(self):
        self._data_table('profiles', 'Profilstatus',
            [('profile', 'Profil', 200), ('account', 'Gespeichertes Konto', 250),
             ('state', 'Status', 150), ('kind', 'Speicherart', 130)],
            [('launch', 'Starten'), ('stop', 'Stoppen'), ('restart', 'Neu starten'), ('recover', 'Wiederherstellen')],
            profile_records(self.view))

    def _remember_tables(self):
        for key, table in self.data_tables.items():
            if table.winfo_exists():
                self.table_states[key] = table.get_state()

    def _data_table(self, key, title, columns, actions, rows):
        table = ActionTable(self.page_frame, title=title, columns=columns, actions=actions,
            on_action=self._data_action, theme=self.theme_name)
        table.pack(fill='both', expand=True, padx=7, pady=(6, 16))
        table.set_rows(rows, loaded=self.snapshot_ready, state=self.table_states.get(key))
        self.data_tables[key] = table
        return table

    def _data_action(self, action, row):
        if self.closing or self.mutating or action not in row.get('actions', ()):
            return
        name = row['profile']
        if action in {'launch', 'stop', 'restart'}:
            self._instance_action(name, action)
        elif action == 'recover':
            self._recover(name)
        elif action == 'login':
            self._login(name)
        elif action == 'reauth':
            self._login(name, reauthenticate=True)
        elif action == 'inspect':
            self._inspect_account(name)
        elif action == 'switch':
            self._switch(name, row['session_id'])
        elif action == 'rename':
            self._rename(name, row['session_id'])

    def _sync_desktop_data(self):
        if self.metrics is not None and self.metrics.winfo_exists():
            self.metrics.set_values(dashboard_metrics(self.view, self.quota.model, loaded=self.snapshot_ready))
        for key, table in self.data_tables.items():
            if table.winfo_exists():
                rows = profile_records(self.view) if key == 'profiles' else session_records(self.view, self.quota.model.get('rows', []))
                table.set_rows(rows, loaded=self.snapshot_ready)

    def _page_instances(self):
        self._draw_profiles()
        card = self._panel('Bestehende Profile', 'Eine Verkn\u00fcpfung registriert nur den Pfad. Die Originaldaten bleiben an ihrem Ort.')
        if self.legacy_rows is not None:
            if not self.legacy_rows:
                self._line(card, 'An den bekannten Speicherorten keine Profile gefunden.', muted=True)
            for found in self.legacy_rows:
                self._line(card, f'{found.name}: {found.path}', muted=True)
        self._actions(card, [('Speicherorte pr\u00fcfen', self._discover), ('Profil verkn\u00fcpfen', self._link_profile)])

    def _set_account_section(self, section):
        if not self.closing and section in {'profiles', 'workspace'}:
            self.account_section = section
            self._set_page('Accounts')

    def _page_accounts(self):
        tabs = self._panel('Kontoverwaltung')
        self._actions(tabs, [('Anmeldungen', lambda: self._set_account_section('profiles')),
            ('Workspace verwalten', lambda: self._set_account_section('workspace'))])
        if self.account_section == 'workspace':
            self.admin.render()
            return
        if self.login_cancel is not None:
            card = self._panel('Anmeldung: ' + (self.login_profile or 'OpenAI'),
                'Im offiziellen Browser mit OpenAI anmelden. Die Anmeldung kann hier abgebrochen werden.')
            if self.login_url is not None:
                self._line(card, 'Warte auf die Browser-Anmeldung (maximal 10 Minuten).')
                row = ctk.CTkFrame(card, fg_color='transparent')
                row.pack(fill='x', padx=20, pady=(5, 14))
                retry = ctk.CTkButton(row, text='Browser erneut öffnen', command=self._reopen_login)
                retry.pack(anchor='w')
                self._keyboard_button(retry)
            else:
                self._line(card, 'Die offizielle Anmeldeseite wird vorbereitet ...')
        managed = [p for p in self.view['profiles'] if not p.linked]
        if self.snapshot_ready and not managed:
            card = self._panel('Noch kein verwaltetes Profil')
            self._line(card, 'Eine Instanz erstellen, bevor eine isolierte Anmeldung hinzugef\u00fcgt wird.')
            self._actions(card, [('Neue Instanz', self._new_profile)])
        self._data_table('sessions', 'Gespeicherte Anmeldungen',
            [('profile', 'Profil', 150), ('email', 'Anmeldung', 230), ('state', 'Zuordnung', 125),
             ('workspace', 'Workspace', 160), ('five', '5h verwendet', 140),
             ('weekly', 'Woche verwendet', 140), ('freshness', 'Messstand', 130)],
            [('login', 'Anmeldung hinzuf\u00fcgen'), ('switch', 'Konto wechseln'),
             ('reauth', 'Erneut anmelden'), ('inspect', 'Anmeldung pr\u00fcfen'),
             ('rename', 'Umbenennen'), ('recover', 'Wiederherstellen')],
            session_records(self.view, self.quota.model.get('rows', [])))
        card = self._panel('Vorhandener Multi-Auth-Pool', 'Nur Bestandsanzeige. Die verschl\u00fcsselte \u00dcbernahme dieser Pool-Konten in einzelne Instanzen ist noch nicht implementiert.')
        if self.pool_rows is None:
            self._line(card, self.pool_error or 'Noch nicht geladen.', muted=True)
        elif not self.pool_rows:
            self._line(card, 'Keine gespeicherten Konten gefunden.', muted=True)
        else:
            for row in self.pool_rows:
                status = 'Ung\u00fcltig markiert' if row.get('invalidated') else 'Deaktiviert' if row.get('enabled') is False else 'Gespeichert, nicht live gepr\u00fcft'
                self._line(card, f'{row.get("label") or row.get("email") or "Konto"}  |  {status}')

    def _set_usage_section(self, section):
        if not self.closing and section in {'history', 'queue'}:
            self.usage_section = section
            self._set_page('Usage')

    def _page_usage(self):
        card = self._panel('Nutzungsverwaltung')
        self._actions(card, [('Quota und Verlauf', lambda: self._set_usage_section('history')),
            ('Startwarteschlange', lambda: self._set_usage_section('queue'))])
        self.quota.render()
        if self.quota.ready:
            hidden = self.quota.activation_panel if self.usage_section == 'history' else self.quota.panel
            if hidden is not None and hidden.winfo_exists():
                hidden.pack_forget()
        if self.usage_section == 'history' and any(p.linked for p in self.view['profiles']):
            self._page_legacy_usage()

    def _page_legacy_usage(self):
        card = self._panel('Profil ausw\u00e4hlen', 'Die offizielle Codex-Anwendung fragt die Limits des gew\u00e4hlten Profils ab.')
        self._actions(card, [(p.name, lambda n=p.name: self._load_usage(n)) for p in self.view['profiles'] if p.linked])
        if self.usage_data is None:
            self._line(card, 'Noch keine Nutzungswerte abgefragt.', muted=True)
        else:
            card = self._panel(self.usage_profile or 'Nutzungswerte')
            for text in usage_lines(self.usage_data):
                self._line(card, text)

    def _set_diagnostics_section(self, section):
        if not self.closing and section in {'runtime', 'recovery', 'quota'}:
            self.diagnostics_section = section
            self._set_page('Diagnostics')

    def _page_diagnostics(self):
        card = self._panel('Pr\u00fcfbereiche', 'Status lesen, gespeicherte Vorg\u00e4nge wiederherstellen oder Quota-Daten sichern.')
        self._actions(card, [('Runtime', lambda: self._set_diagnostics_section('runtime')),
            ('Wiederherstellung', lambda: self._set_diagnostics_section('recovery')),
            ('Quota und Workspace', lambda: self._set_diagnostics_section('quota'))])
        if self.diagnostics_section == 'quota':
            self.quota.diagnostics()
            card = self._panel('Workspace-Aktionen', 'Einladungen und Mitgliedschafts\u00e4nderungen ben\u00f6tigen eine konkrete Vorschau und Freigabe.')
            self._actions(card, [('Workspace verwalten', lambda: self._set_account_section('workspace'))])
            return
        if self.diagnostics_section == 'runtime':
            card = self._panel('Laufzeit und Abh\u00e4ngigkeiten')
            if self.health_data is None:
                self._line(card, 'Noch nicht gepr\u00fcft.', muted=True)
            else:
                for key, label in [('serviceReady', 'Lokale Schnittstelle'), ('nodeCompatible', 'Node-Version'), ('upstreamReady', 'Multi-Auth-Modul')]:
                    value = self.health_data.get(key)
                    state = 'Bereit' if value is True else 'Nicht bereit' if value is False else 'Unbekannt'
                    self._line(card, label + ': ' + state)
            self._actions(card, [('Abh\u00e4ngigkeiten pr\u00fcfen', self._health)])
            card = self._panel('Kompatibilit\u00e4t')
            self._line(card, 'Unterst\u00fctzter Erkennungspfad: OpenAI.Codex MSIX, app/ChatGPT.exe. Andere Builds werden nicht erraten. Native Windows-/OAuth-Abnahme ist ein gesonderter Nachweis.', muted=True)
            return
        card = self._panel('Profile und Wiederherstellung')
        if not self.snapshot_ready:
            self._line(card, 'Profilstatus wird geladen.', muted=True)
        elif not self.view['issues'] and not any(self.view['recovery'].values()):
            self._line(card, 'Keine lokalen Metadatenfehler gemeldet. Das ist kein Nachweis g\u00fcltiger Online-Anmeldungen.', muted=True)
        for issue in self.view['issues']:
            self._line(card, f'{issue["name"]}: {issue["error"]}')
        for profile in self.view['profiles']:
            if self.view['recovery'].get(profile.name):
                self._actions(card, [(profile.name + ': wiederherstellen', lambda n=profile.name: self._recover(n))])
            if self.view['processes'].get(profile.name, {}).get('running') is True:
                self._actions(card, [(profile.name + ': Beenden erzwingen', lambda n=profile.name: self._instance_action(n, 'stop', force=True))])

    def _set_settings_section(self, section):
        if not self.closing and section in {'general', 'monitoring'}:
            self.settings_section = section
            self._set_page('Settings')

    def _page_settings(self):
        tabs = self._panel('Einstellungsbereiche')
        self._actions(tabs, [('Allgemein', lambda: self._set_settings_section('general')),
            ('Monitoring und Automatik', lambda: self._set_settings_section('monitoring'))])
        if self.settings_section == 'monitoring':
            self.quota.settings_view()
            return
        card = self._panel('Darstellung', 'Die Auswahl bleibt nach dem Neustart erhalten.')
        self._actions(card, [('Dunkel', lambda: self._set_theme('dark')), ('Hell', lambda: self._set_theme('light'))])
        if self.settings.problem:
            self._line(card, 'Die vorhandenen Einstellungen sind besch\u00e4digt und wurden nicht \u00fcberschrieben.')
        card = self._panel('Bedienung und Datensicherheit')
        self._line(card, 'Strg+1 bis Strg+6: Ansicht wechseln. Strg+R: aktualisieren. Strg+F in Tabellen: suchen. Escape: Anmeldung abbrechen.', muted=True)
        self._line(card, 'Workspace-Admin-Schl\u00fcssel gelten nur f\u00fcr die jeweilige Aktion. Die Quota-Historie bleibt von Credentials getrennt.', muted=True)
        card = self._panel('Profilspeicher')
        self._line(card, str(self.store.root), muted=True)
        self._line(card, 'Neue Anmeldungen verwenden den Windows-Anmeldespeicher. Bestehende verkn\u00fcpfte Profile behalten ihr urspr\u00fcngliches Speicherformat.', muted=True)
        self._actions(card, [('Figma-Entwurf \u00f6ffnen', lambda: webbrowser.open(FIGMA_URL))])

    def _submit(self, key, work, callback, *, mutation=False, error_callback=None):
        if self.closing or (mutation and self.mutating):
            return False
        try:
            self.jobs.submit(key, work)
        except JobBusy:
            return False
        self.callbacks[key] = (callback, mutation, error_callback)
        if mutation:
            self.mutating = True
            self._set_status('Aktion l\u00e4uft. Andere Profile bleiben unver\u00e4ndert.')
        self._busy_state()
        return True

    def _busy_state(self):
        if hasattr(self, 'admin'):
            self.admin.sync_busy()
        busy = self.mutating or self.closing
        for table in self.data_tables.values():
            if table.winfo_exists():
                table.set_busy(busy)
        for button in [self.primary] + self.action_buttons:
            button.configure(state='disabled' if busy else 'normal')
        if self.login_cancel is not None:
            self.cancel_button.grid()
            self.cancel_button.configure(state='normal' if not self.login_cancel.is_set() else 'disabled')
        else:
            self.cancel_button.grid_remove()
        foreground = busy or self.quota.foreground or any(key not in {'snapshot', 'pool', 'discovery', 'quota-monitor'} for key in self.callbacks)
        if foreground and not self._progress_running:
            self.progress.grid()
            self.progress.start(); self._progress_running = True
        elif not foreground:
            self.progress.stop(); self.progress.set(0); self._progress_running = False
            self.progress.grid_remove()

    def _poll_results(self):
        self._poll_id = None
        while True:
            try:
                cancel, url, opened = self.login_events.get_nowait()
            except queue.Empty:
                break
            if cancel is self.login_cancel and not cancel.is_set():
                self.login_url = url
                self.login_browser_opened = opened
                self._set_status('Browser wird geöffnet. Anmeldung kann hier abgebrochen werden.' if opened is None else
                    'Im Browser mit OpenAI anmelden. Browser bei Bedarf erneut öffnen.' if opened else
                    'Der Browser konnte nicht geöffnet werden. Unter Konten auf Browser erneut öffnen klicken.')
                if self.page == 'Accounts':
                    self._render()
        for result in self.jobs.drain():
            callback, mutation, error_callback = self.callbacks.pop(result.key, (None, False, None))
            if mutation:
                self.mutating = False
                was_login = self.login_cancel is not None
                self.login_cancel = None
                self.login_url = None
                self.login_profile = None
                if was_login and self.page == 'Accounts' and not self.closing:
                    self._render()
            if not self.closing:
                try:
                    if result.error is not None:
                        if error_callback:
                            error_callback(result.error)
                        else:
                            self._set_status(user_error(result.error))
                    elif callback:
                        callback(result.value)
                    if mutation:
                        self._refresh()
                except Exception as error:
                    self._set_status(user_error(error))
        if self.closing and not self.jobs.pending:
            self._shutdown()
            return
        self._busy_state()
        self._poll_id = self.after(100, self._poll_results)

    def _refresh(self, *, include_pool=False):
        if self.closing or self.mutating:
            return
        self._submit('snapshot', self.services.snapshot, self._snapshot_loaded)
        self.quota.refresh()
        if include_pool:
            self._submit('pool', self.accounts.list_accounts, self._pool_loaded, error_callback=self._pool_failed)

    def _periodic_refresh(self):
        self._refresh_id = None
        if not self.closing:
            self._refresh()
            self._refresh_id = self.after(3000, self._periodic_refresh)

    @staticmethod
    def _snapshot_structure(snapshot):
        profiles = tuple((row.get('name'), row.get('linked'))
                         for row in snapshot.get('profiles', []))
        sessions = tuple(sorted(snapshot.get('sessions', {}).keys()))
        recovery = tuple(sorted(snapshot.get('recovery', {}).keys()))
        issues = tuple(sorted((row.get('profile'), row.get('code'))
                              for row in snapshot.get('issues', [])))
        return profiles, sessions, recovery, issues

    def _snapshot_loaded(self, snapshot):
        structure_changed = (not self.snapshot_ready or
                             self._snapshot_structure(snapshot) != self._snapshot_structure(self.view))
        self.snapshot_ready = True
        self.view = snapshot
        if structure_changed:
            self._render()
        else:
            # Keep the existing widget tree, selection, scroll and focus while
            # refreshing process/metric values in place.
            self._sync_desktop_data()

    def _pool_loaded(self, rows):
        self.pool_rows, self.pool_error = rows, None
        if self.page == 'Accounts':
            self._render()

    def _pool_failed(self, error):
        self.pool_rows = None
        self.pool_error = user_error(error)
        if self.page == 'Accounts':
            self._render()

    def _completed(self, _value):
        self._set_status('Aktion abgeschlossen. Prozessstatus wird aktualisiert.')

    def _new_profile(self):
        name = ctk.CTkInputDialog(text='Name der isolierten Instanz', title='Neue Instanz').get_input()
        if name:
            self._submit('mutation', lambda: self.store.create(name), self._completed, mutation=True)

    def _link_profile(self):
        directory = filedialog.askdirectory(parent=self, title='Bestehendes einzelnes Codex-Profil ausw\u00e4hlen')
        if not directory:
            return
        name = ctk.CTkInputDialog(text='Name f\u00fcr das verkn\u00fcpfte Profil', title='Profil verkn\u00fcpfen').get_input()
        if name and messagebox.askyesno('Originalprofil verkn\u00fcpfen', 'Die Verkn\u00fcpfung kopiert keine Daten. Beim Start schreibt die offizielle App weiterhin in diesen Originalordner. Fortfahren?', parent=self):
            self._submit('mutation', lambda: self.store.adopt(name, Path(directory)), self._completed, mutation=True)

    def _confirm_restart(self, name):
        return messagebox.askyesno('Nur dieses Profil neu starten', f'{name}: Nach erfolgreicher Kontoaktion wird diese Instanz geschlossen und neu gestartet. Ungespeicherte Arbeit kann verloren gehen. Fortfahren?', parent=self)

    def _instance_action(self, name, action, *, force=False):
        if action != 'launch':
            prompt = ('Erzwungenes Beenden kann ungespeicherte Arbeit verlieren. ' if force else '') + f'Nur {name} {"stoppen" if action == "stop" else "neu starten"}?'
            if not messagebox.askyesno('Prozessaktion best\u00e4tigen', prompt, parent=self):
                return
        self._submit('mutation', lambda: self.services.operations.operate(name, action, confirmed=True, force=force), self._completed, mutation=True)

    def _switch(self, name, sid):
        if self._confirm_restart(name):
            self._submit('mutation', lambda: self.services.operations.switch(name, sid, confirmed=True), self._completed, mutation=True)

    def _login(self, name, *, reauthenticate=False):
        if self.mutating or not self._confirm_restart(name):
            return
        cancel = threading.Event()
        self.login_cancel = cancel
        self.login_profile = name
        self.login_url = None
        self.login_browser_opened = False
        def open_login(url):
            self._open_login_browser(cancel, validate_login_url(url))
        accepted = self._submit('mutation', lambda: self.services.operations.login(name,
            confirmed=True, reauthenticate=reauthenticate, on_browser=open_login, cancel=cancel),
            self._completed, mutation=True)
        if not accepted:
            self.login_cancel = None
            self.login_profile = None
        else:
            self._set_page('Accounts')
            self._set_status('OpenAI-Anmeldung wird vorbereitet. Der Browser öffnet sich anschließend.')
        self._busy_state()

    def _open_login_browser(self, cancel, url):
        if cancel.is_set():
            return
        url = validate_login_url(url)
        events, browser_lock = self.login_events, self._browser_lock
        events.put_nowait((cancel, url, None))
        if not browser_lock.acquire(blocking=False):
            events.put_nowait((cancel, url, False))
            return False
        done, result = threading.Event(), []
        # Shell browser activation can stall. This helper holds no Tk objects
        # and cannot hold the auth worker or application shutdown indefinitely.
        def activate():
            try:
                opened = False if cancel.is_set() else bool(webbrowser.open(url, new=2))
            except Exception:
                opened = False
            finally:
                browser_lock.release()
            result.append(opened)
            try:
                events.put_nowait((cancel, url, opened))
            except queue.Full:
                pass
            done.set()
        threading.Thread(target=activate, name='multicodex-browser', daemon=True).start()
        deadline = time.monotonic() + 5
        while not done.is_set() and time.monotonic() < deadline:
            if cancel.wait(.05):
                return False
        if not done.is_set():
            events.put_nowait((cancel, url, False))
            return False
        return result[0]

    def _reopen_login(self):
        if self.login_cancel is None or self.login_cancel.is_set() or self.login_url is None:
            return
        cancel, url = self.login_cancel, self.login_url
        self._submit('login-browser', lambda: self._open_login_browser(cancel, url), lambda _: None)

    def _cancel_login(self):
        if self.login_cancel is not None:
            self.login_cancel.set()
            self._set_status('Abbruch angefordert. Ein bereits begonnener Neustart wird zuerst sicher abgeschlossen.')
            self._busy_state()

    def _recover(self, name):
        if self._confirm_restart(name):
            self._submit('mutation', lambda: self.services.operations.recover(name, confirmed=True), self._completed, mutation=True)

    def _rename(self, name, sid):
        label = ctk.CTkInputDialog(text='Neuer Anzeigename', title='Konto umbenennen').get_input()
        if label:
            self._submit('mutation', lambda: self.services.sessions.rename(name, sid, label), self._completed, mutation=True)

    def _inspect_account(self, name):
        def work():
            with self.services.sessions.lock(name):
                profile = self.store.get(name)
                identity = self.services.auth.describe(profile.codex_home, secure=True)
                self.services.sessions.register(name, profile.session_id, identity)
                return identity
        self._submit('mutation', work, self._completed, mutation=True)

    def _load_usage(self, name):
        def work():
            with self.services.sessions.lock(name):
                profile = self.store.get(name)
                return self.services.auth.limits(profile.codex_home, secure=not profile.linked)
        def loaded(rows):
            self.usage_profile, self.usage_data = name, rows
            self._render()
        self._submit('usage', work, loaded)

    def _discover(self):
        def loaded(rows):
            self.legacy_rows = rows
            self._render()
        self._submit('discovery', lambda: discover_legacy_profiles(default_legacy_roots()), loaded)

    def _health(self):
        def loaded(data):
            self.health_data = data
            self._render()
        self._submit('health', lambda: self.accounts.request('health'), loaded)

    def _set_theme(self, mode):
        if mode == self.theme_name:
            return
        def apply(saved):
            self.progress.stop()
            self._progress_running = False
            self.theme_name = saved
            self.palette = THEMES[saved]
            ctk.set_appearance_mode(saved)
            self._remember_tables()
            self.data_tables = {}
            self.rail.destroy(); self.right.destroy()
            self._build_shell(); self._render()
        self._submit('mutation', lambda: self.settings.save_theme(mode), apply, mutation=True)

    def _set_status(self, text):
        self.status_bar.configure(text=text[:320])

    def report_callback_exception(self, exc_type, value, traceback):
        # Tk's default handler prints raw exception text, potentially including
        # provider output. Keep the UI alive with the same safe error boundary.
        if hasattr(self, 'status_bar') and not self.closing:
            self._set_status(user_error(value))

    def _close(self):
        if self.closing:
            return
        if self.jobs.pending and not messagebox.askyesno('Laufende Aktion', 'Laufende Anmeldung abbrechen und das Verwaltungsfenster nach Abschluss beenden? Ge\u00f6ffnete Desktop-Instanzen bleiben bestehen.', parent=self):
            return
        self.closing = True
        self.quota.close()
        self.admin.close()
        if self.login_cancel is not None:
            self.login_cancel.set()
        if self._refresh_id is not None:
            self.after_cancel(self._refresh_id); self._refresh_id = None
        self.jobs.close()
        self._set_status('Laufende Aktionen werden sicher beendet. Desktop-Instanzen bleiben ge\u00f6ffnet.')
        self._busy_state()
        if not self.jobs.pending:
            self._shutdown()

    def _shutdown(self):
        self.progress.stop()
        self._progress_running = False
        for identity in (self._poll_id, self._refresh_id):
            if identity is not None:
                self.after_cancel(identity)
        self._poll_id = self._refresh_id = None
        self.jobs.close()
        self.destroy()


def main():
    MultiCodexApp().mainloop()

