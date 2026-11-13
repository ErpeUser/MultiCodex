"""Native desktop interface. Worker services own I/O; Tk owns every widget."""
from __future__ import annotations

import os
import threading
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
from .ui_tokens import THEMES, PADDING, NAV_WIDTH

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
        self.title('MultiCodex 0.2.0-dev')
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
        self.page = 'Overview'
        self._poll_id = None
        self._refresh_id = None
        self._progress_running = False
        self._build_shell()
        self._render()
        self.protocol('WM_DELETE_WINDOW', self._close)
        self.bind('<Control-r>', lambda event: self._refresh(include_pool=True))
        self.bind('<Escape>', lambda event: self._cancel_login())
        self._poll_id = self.after(100, self._poll_results)
        if auto_start:
            self._refresh(include_pool=True)
            self._discover()
            self._refresh_id = self.after(3000, self._periodic_refresh)

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
                     font=ctk.CTkFont(family='Segoe UI', size=21, weight='bold')).pack(anchor='w', padx=24, pady=(28, 5))
        ctk.CTkLabel(self.rail, text='Lokale Kontoverwaltung', text_color=p['muted']).pack(anchor='w', padx=24, pady=(0, 30))
        for key in PAGES:
            button = ctk.CTkButton(self.rail, text=LABELS[key], anchor='w', height=38,
                fg_color='transparent', hover_color=p['selected'], text_color=p['text'],
                command=lambda key=key: self._set_page(key))
            button.pack(fill='x', padx=14, pady=4)
            self._keyboard_button(button)
            self.nav_buttons[key] = button
        ctk.CTkLabel(self.rail, text='Entwicklungsstand\nKeine Cloud-Synchronisierung', text_color=p['muted'],
                     justify='left', font=ctk.CTkFont(size=11)).pack(side='bottom', padx=24, pady=24)
        self.right = ctk.CTkFrame(self, fg_color=p['canvas'], corner_radius=0)
        self.right.grid(row=0, column=1, sticky='nsew')
        self.right.grid_columnconfigure(0, weight=1)
        self.right.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self.right, fg_color='transparent')
        header.grid(row=0, column=0, sticky='ew', padx=30, pady=(25, 12))
        header.grid_columnconfigure(0, weight=1)
        self.header_title = ctk.CTkLabel(header, text='', text_color=p['text'],
            font=ctk.CTkFont(family='Segoe UI', size=26, weight='bold'), anchor='w')
        self.header_title.grid(row=0, column=0, sticky='w')
        self.header_subtitle = ctk.CTkLabel(header, text='', text_color=p['muted'],
            justify='left', wraplength=420, anchor='w')
        self.header_subtitle.grid(row=1, column=0, sticky='w', pady=(5, 0))
        self.primary = ctk.CTkButton(header, text='Neue Instanz', width=140, height=40,
            fg_color=p['accent'], hover_color=p['selected'], text_color=p['accent_text'], command=self._new_profile)
        self.primary.grid(row=0, column=1, rowspan=2, padx=(12, 0))
        self._keyboard_button(self.primary)
        self.page_frame = ctk.CTkScrollableFrame(self.right, fg_color='transparent')
        self.page_frame.grid(row=1, column=0, sticky='nsew', padx=24, pady=4)
        footer = ctk.CTkFrame(self.right, fg_color='transparent')
        footer.grid(row=2, column=0, sticky='ew', padx=32, pady=(5, 14))
        footer.grid_columnconfigure(0, weight=1)
        self.progress = ctk.CTkProgressBar(footer, height=3, mode='indeterminate', progress_color=p['accent'])
        self.progress.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 9))
        self.progress.set(0)
        self.status_bar = ctk.CTkLabel(footer, text='Bereit', text_color=p['muted'],
            anchor='w', justify='left', wraplength=530)
        self.status_bar.grid(row=1, column=0, sticky='w')
        self.cancel_button = ctk.CTkButton(footer, text='Anmeldung abbrechen', width=150,
            fg_color=p['selected'], text_color=p['text'], command=self._cancel_login, state='disabled')
        self.cancel_button.grid(row=1, column=1, padx=(10, 0))
        self._keyboard_button(self.cancel_button)

    @staticmethod
    def _keyboard_button(button):
        button.bind('<Return>', lambda event: button.invoke())
        button.bind('<space>', lambda event: button.invoke())

    def _set_page(self, page):
        if not self.closing:
            self.page = page
            self._render()

    def _render(self):
        self.action_buttons = []
        titles = {**LABELS, 'Overview': 'Konten und Instanzen', 'Usage': 'Nutzungslimits'}
        subtitles = {
            'Overview': 'Getrennte Profile. Nur die ausgew\u00e4hlte Instanz wird neu gestartet.',
            'Accounts': 'Gespeicherte Anmeldungen je Profil; der vorhandene globale Pool bleibt unver\u00e4ndert.',
            'Instances': 'Start und Ende werden anhand des konkreten Profilpfads gepr\u00fcft.',
            'Usage': 'Nur gemeldete Werte der offiziellen Anwendung. Keine Sch\u00e4tzungen.',
            'Diagnostics': 'Fehlerzust\u00e4nde und offene Wiederherstellungen, ohne Zugangsdaten.',
            'Settings': 'Darstellung und lokaler Speicherort.',
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
        card = ctk.CTkFrame(self.page_frame, fg_color=self.palette['panel'], corner_radius=12)
        card.pack(fill='x', padx=7, pady=(6, 14))
        ctk.CTkLabel(card, text=title, text_color=self.palette['text'],
            font=ctk.CTkFont(size=17, weight='bold')).pack(anchor='w', padx=PADDING, pady=(16, 7))
        if subtitle:
            self._line(card, subtitle, muted=True)
        return card

    def _line(self, parent, text, *, muted=False):
        label = ctk.CTkLabel(parent, text=text, text_color=self.palette['muted' if muted else 'text'],
            wraplength=max(340, self.winfo_width()-NAV_WIDTH-140), justify='left', anchor='w')
        label.pack(fill='x', padx=20, pady=(2, 10))
        return label

    def _actions(self, parent, items):
        """Wrap controls naturally at two columns instead of squeezing long labels."""
        row = ctk.CTkFrame(parent, fg_color='transparent')
        row.pack(fill='x', padx=20, pady=(5, 14))
        row.grid_columnconfigure((0, 1), weight=1)
        for index, (text, command) in enumerate(items):
            button = ctk.CTkButton(row, text=text, height=34,
                fg_color=self.palette['selected'], text_color=self.palette['text'],
                hover_color=self.palette['border'], command=command)
            button.grid(row=index//2, column=index%2, sticky='ew', padx=(0, 8), pady=4)
            self._keyboard_button(button)
            self.action_buttons.append(button)

    def _page_overview(self):
        profiles = self.view['profiles']
        unknown = any(v['running'] is None for v in self.view['processes'].values())
        running = sum(v['running'] is True for v in self.view['processes'].values())
        total_sessions = sum(len(v) for v in self.view['sessions'].values())
        card = self._panel('Lokaler Status')
        self._line(card, f'{len(profiles)} Profile   |   {"?" if unknown else running} laufend   |   {total_sessions} gespeicherte Anmeldungen')
        if os.name != 'nt':
            self._line(card, 'Desktop-Instanzen ben\u00f6tigen Windows. Diese Umgebung kann ihre Funktion nicht best\u00e4tigen.', muted=True)
        self._draw_profiles()
        if self.view['issues']:
            card = self._panel('Pr\u00fcfung erforderlich')
            self._line(card, 'Mindestens ein Profil oder Prozessstatus ist nicht lesbar. Details unter Diagnose.')
        if not profiles:
            card = self._panel('Vorhandene Profile weiterverwenden', 'Bestehende Anmeldungen werden weder kopiert noch gel\u00f6scht.')
            self._actions(card, [('Profil verkn\u00fcpfen', self._link_profile)])

    def _draw_profiles(self):
        for profile in self.view['profiles']:
            process = self.view['processes'].get(profile.name, {})
            status = {True: 'L\u00e4uft', False: 'Gestoppt', None: 'Unbekannt'}[process.get('running')]
            recovery = self.view['recovery'].get(profile.name)
            card = self._panel(profile.name, f'{status}  |  {"Verkn\u00fcpft" if profile.linked else "Verwaltet"}')
            self._line(card, profile.account_email or ('Anmeldung der Original-App' if profile.linked else 'Keine Kontometadaten best\u00e4tigt'), muted=True)
            if process.get('pids'):
                self._line(card, 'Prozess: ' + ', '.join(str(p) for p in process['pids']), muted=True)
            if recovery:
                self._line(card, 'Ein unterbrochener Kontowechsel muss zuerst wiederhergestellt werden.')
                items = [('Wiederherstellen', lambda n=profile.name: self._recover(n)),
                         ('Stoppen', lambda n=profile.name: self._instance_action(n, 'stop'))]
            else:
                items = [('Starten', lambda n=profile.name: self._instance_action(n, 'launch')),
                         ('Stoppen', lambda n=profile.name: self._instance_action(n, 'stop')),
                         ('Neu starten', lambda n=profile.name: self._instance_action(n, 'restart'))]
            self._actions(card, items)

    def _page_instances(self):
        self._draw_profiles()
        card = self._panel('Bestehende Profile', 'Eine Verkn\u00fcpfung registriert nur den Pfad. Die Originaldaten bleiben an ihrem Ort.')
        if self.legacy_rows is not None:
            if not self.legacy_rows:
                self._line(card, 'An den bekannten Speicherorten keine Profile gefunden.', muted=True)
            for found in self.legacy_rows:
                self._line(card, f'{found.name}: {found.path}', muted=True)
        self._actions(card, [('Speicherorte pr\u00fcfen', self._discover), ('Profil verkn\u00fcpfen', self._link_profile)])

    def _page_accounts(self):
        managed = [p for p in self.view['profiles'] if not p.linked]
        if not managed:
            card = self._panel('Noch kein verwaltetes Profil')
            self._line(card, 'Eine Instanz erstellen, bevor eine isolierte Anmeldung hinzugef\u00fcgt wird.')
            self._actions(card, [('Neue Instanz', self._new_profile)])
        for profile in managed:
            card = self._panel(profile.name, 'Beim Wechsel oder Re-Login startet ausschlie\u00dflich dieses Profil neu.')
            for session in self.view['sessions'].get(profile.name, []):
                active = session['id'] == profile.session_id
                self._line(card, f'{session.get("label") or session["email"]}  |  {"Zugeordnet" if active else "Gespeichert"}')
                actions = [('Umbenennen', lambda n=profile.name, s=session['id']: self._rename(n, s))]
                if not active:
                    actions.insert(0, ('Konto wechseln', lambda n=profile.name, s=session['id']: self._switch(n, s)))
                self._actions(card, actions)
            if self.view['recovery'].get(profile.name):
                self._actions(card, [('Wiederherstellen', lambda n=profile.name: self._recover(n))])
            else:
                self._actions(card, [('Konto hinzuf\u00fcgen', lambda n=profile.name: self._login(n)),
                    ('Erneut anmelden', lambda n=profile.name: self._login(n, reauthenticate=True)),
                    ('Anmeldung pr\u00fcfen', lambda n=profile.name: self._inspect_account(n))])
        card = self._panel('Vorhandener Multi-Auth-Pool', 'Nur Bestandsanzeige. Die verschl\u00fcsselte \u00dcbernahme dieser Pool-Konten in einzelne Instanzen ist noch nicht implementiert.')
        if self.pool_rows is None:
            self._line(card, self.pool_error or 'Noch nicht geladen.', muted=True)
        elif not self.pool_rows:
            self._line(card, 'Keine gespeicherten Konten gefunden.', muted=True)
        else:
            for row in self.pool_rows:
                status = 'Ung\u00fcltig markiert' if row.get('invalidated') else 'Deaktiviert' if row.get('enabled') is False else 'Gespeichert, nicht live gepr\u00fcft'
                self._line(card, f'{row.get("label") or row.get("email") or "Konto"}  |  {status}')

    def _page_usage(self):
        card = self._panel('Profil ausw\u00e4hlen', 'Die offizielle Codex-Anwendung fragt die Limits des gew\u00e4hlten Profils ab.')
        self._actions(card, [(p.name, lambda n=p.name: self._load_usage(n)) for p in self.view['profiles']])
        if self.usage_data is None:
            self._line(card, 'Noch keine Nutzungswerte abgefragt.', muted=True)
        else:
            card = self._panel(self.usage_profile or 'Nutzungswerte')
            for text in usage_lines(self.usage_data):
                self._line(card, text)

    def _page_diagnostics(self):
        card = self._panel('Laufzeit und Abh\u00e4ngigkeiten')
        if self.health_data is None:
            self._line(card, 'Noch nicht gepr\u00fcft.', muted=True)
        else:
            for key, label in [('serviceReady', 'Lokale Schnittstelle'), ('nodeCompatible', 'Node-Version'), ('upstreamReady', 'Multi-Auth-Modul')]:
                self._line(card, f'{label}: {"Bereit" if self.health_data.get(key) is True else "Nicht bereit"}')
        self._actions(card, [('Abh\u00e4ngigkeiten pr\u00fcfen', self._health)])
        card = self._panel('Profile und Wiederherstellung')
        if not self.view['issues'] and not any(self.view['recovery'].values()):
            self._line(card, 'Keine lokalen Metadatenfehler gemeldet. Das ist kein Nachweis g\u00fcltiger Online-Anmeldungen.', muted=True)
        for issue in self.view['issues']:
            self._line(card, f'{issue["name"]}: {issue["error"]}')
        for profile in self.view['profiles']:
            if self.view['recovery'].get(profile.name):
                self._actions(card, [(profile.name + ': wiederherstellen', lambda n=profile.name: self._recover(n))])
            if self.view['processes'].get(profile.name, {}).get('running') is True:
                self._actions(card, [(profile.name + ': Beenden erzwingen', lambda n=profile.name: self._instance_action(n, 'stop', force=True))])
        card = self._panel('Kompatibilit\u00e4t')
        self._line(card, 'Unterst\u00fctzter Erkennungspfad: OpenAI.Codex MSIX, app/ChatGPT.exe. Andere und kombinierte ChatGPT-Builds werden nicht erraten. Echte Windows-/OAuth-Abnahme steht aus.', muted=True)

    def _page_settings(self):
        card = self._panel('Darstellung', 'Die Auswahl bleibt nach dem Neustart erhalten.')
        self._actions(card, [('Dunkel', lambda: self._set_theme('dark')), ('Hell', lambda: self._set_theme('light'))])
        if self.settings.problem:
            self._line(card, 'Die vorhandenen Einstellungen sind besch\u00e4digt und wurden nicht \u00fcberschrieben.')
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
        busy = self.mutating or self.closing
        for button in [self.primary] + self.action_buttons:
            button.configure(state='disabled' if busy else 'normal')
        self.cancel_button.configure(state='normal' if self.login_cancel is not None and not self.login_cancel.is_set() else 'disabled')
        if self.jobs.pending and not self._progress_running:
            self.progress.start(); self._progress_running = True
        elif not self.jobs.pending and self._progress_running:
            self.progress.stop(); self.progress.set(0); self._progress_running = False

    def _poll_results(self):
        self._poll_id = None
        for result in self.jobs.drain():
            callback, mutation, error_callback = self.callbacks.pop(result.key, (None, False, None))
            if mutation:
                self.mutating = False
                self.login_cancel = None
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
        if include_pool:
            self._submit('pool', self.accounts.list_accounts, self._pool_loaded, error_callback=self._pool_failed)

    def _periodic_refresh(self):
        self._refresh_id = None
        if not self.closing:
            self._refresh()
            self._refresh_id = self.after(3000, self._periodic_refresh)

    def _snapshot_loaded(self, snapshot):
        if snapshot != self.view:
            self.view = snapshot
            self._render()

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
        def open_login(url):
            validate_login_url(url)
            if not webbrowser.open(url, new=2):
                raise RuntimeError('System browser unavailable')
        accepted = self._submit('mutation', lambda: self.services.operations.login(name,
            confirmed=True, reauthenticate=reauthenticate, on_browser=open_login, cancel=cancel),
            self._completed, mutation=True)
        if not accepted:
            self.login_cancel = None
        else:
            self._set_status('Im offiziellen Browser anmelden. Die bestehende Instanz bleibt bis zum Erfolg ge\u00f6ffnet.')
        self._busy_state()

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
