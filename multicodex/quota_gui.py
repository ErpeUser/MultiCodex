"""Quota integration into MultiCodex's existing JobRunner/Tk completion boundary."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import threading
from .automation_settings import DEFAULTS
from .quota_service import QuotaService
from .quota_ui import QuotaPanel, QuotaSettingsPanel
from .quota_view import summarize_rows


class QuotaGuiController:
    def __init__(self,host,root):
        self.host=host
        self.root=Path(root)
        self.application=host.services
        self.cancel=threading.Event()
        self.service=None
        self.ready=False
        self.foreground=False
        self.error_message=None
        self.panel=None
        self.summary_label=None
        self.settings_panel=None
        self.model={'rows':[],'settings':{**DEFAULTS,'allowed_profiles':[]},'profiles':[],
                    'issues':[],'operation':{'state':'IDLE'}}

    def _get_service(self):
        # Only called from a queued worker, never during Tk construction/rendering.
        if self.service is None:
            self.service=QuotaService(self.root,self.application,cancel=self.cancel)
        return self.service

    @staticmethod
    def _alive(widget):
        return widget is not None and bool(widget.winfo_exists())

    def _queue(self,work,callback,*,foreground=False):
        previous=self.foreground
        self.foreground=previous or foreground
        def completed(result):
            self.foreground=False
            callback(result)
        accepted=self.host._submit('quota-monitor',work,completed,error_callback=self._failed)
        if not accepted:self.foreground=previous
        return accepted

    def refresh(self,*,force_key=None):
        if self.host.closing or self.host.mutating or self.cancel.is_set():return False
        accepted=self._queue(lambda:self._get_service().work(force_key=force_key),
            self._loaded,foreground=force_key is not None)
        if force_key is not None:
            self.host._set_status('Quota-Abfrage angefordert.' if accepted else 'Eine Quota-Aktion l\u00e4uft bereits. Bitte danach erneut pr\u00fcfen.')
        return accepted

    def _loaded(self,model):
        self.foreground=False
        if self.host.closing:return
        was_ready=self.ready
        self.model=model;self.ready=True;self.error_message=None
        if self._alive(self.panel):self.panel.set_model(model)
        if self._alive(self.summary_label):self.summary_label.configure(text=self._summary_text())
        if not was_ready and self.host.page in ('Settings','Usage'):self.host._render()

    def _failed(self,error):
        self.foreground=False
        self.error_message='Quota-Aktion nicht abgeschlossen. Historische Daten bleiben erhalten; Speicher, Einstellungen und Codex-Verbindung pr\u00fcfen.'
        self.host._set_status(self.error_message)
        self.model=deepcopy(self.model)
        for row in self.model['rows']:
            row['quota']['freshness']='CACHED'
            row['quota']['capacity_confirmed']=False
            if row['quota']['status']!='ACCESS_REMOVED':row['quota']['status']='VERIFICATION_REQUIRED'
        if self._alive(self.panel):self.panel.set_model(self.model)

    def render(self):
        if not self.ready:
            card=self.host._panel('Quota-Historie')
            self.host._line(card,self.error_message or 'Gespeicherte Quota-Daten werden geladen.')
            return
        self.panel=QuotaPanel(self.host.page_frame,theme=self.host.theme_name,
            on_refresh=lambda key:self.refresh(force_key=key),on_history=self.history)
        self.panel.pack(fill='both',expand=True,padx=7,pady=(6,14))
        self.panel.set_model(self.model)
        if self.error_message:
            card=self.host._panel('Quota-Pr\u00fcfung erforderlich')
            self.host._line(card,self.error_message)

    def _summary_text(self):
        if not self.ready:return self.error_message or 'Gespeicherte Quota-Daten werden geladen.'
        summary=summarize_rows(self.model.get('rows',[]))
        mode='aktiv' if self.model.get('settings',{}).get('enabled') else 'pausiert'
        return (f'{summary["accounts"]} gespeicherte Quota-Konten  |  {summary["critical"]} mit Warnung  |  '
                f'{summary["needs_check"]} zu pr\u00fcfen\nMonitoring {mode}. Gespeicherte Werte bleiben auch ohne Workspace-Zugang erhalten.')

    def summary(self):
        card=self.host._panel('Quota-Monitoring')
        self.summary_label=self.host._line(card,self._summary_text())
        self.host._actions(card,[('Quota-Historie \u00f6ffnen',lambda:self.host._set_page('Usage'))])

    def settings_view(self):
        self.settings_panel=QuotaSettingsPanel(self.host.page_frame,theme=self.host.theme_name,
            model=self.model,on_save=self.save_settings)
        self.settings_panel.pack(fill='x',padx=7,pady=(6,14))
        if not self.ready:
            self.settings_panel.save_button.configure(state='disabled')
            self.settings_panel.message.configure(text='Quota-Einstellungen werden noch geladen.')

    def save_settings(self,changes):
        if self.host.closing or self.host.mutating:return
        def work():
            service=self._get_service();service.save_settings(changes)
            return service.work()
        def saved(model):
            self._loaded(model)
            self.host._set_status('Quota-Monitoring gespeichert. Keine Konto- oder Workspace-Mitgliedschaft ge\u00e4ndert.')
            if self._alive(self.settings_panel):self.settings_panel.message.configure(text='Vom Backend best\u00e4tigt gespeichert.')
        accepted=self._queue(work,saved,foreground=True)
        if not accepted:self.host._set_status('Eine Quota-Abfrage l\u00e4uft. Einstellungen danach erneut speichern.')

    def history(self,key,offset=0):
        if self.host.closing:return
        def loaded(rows):
            if self._alive(self.panel):self.panel.show_history(key,rows,offset)
        accepted=self._queue(lambda:self._get_service().history(key,offset=offset),loaded,foreground=True)
        if not accepted:self.host._set_status('Eine Quota-Aktion l\u00e4uft; Historie danach erneut \u00f6ffnen.')

    def diagnostics(self):
        card=self.host._panel('Quota-Speicher und Automatisierung')
        self.host._line(card,self.error_message or 'Quota-Historie liegt getrennt von den Anmeldedaten in quota-history/quota.sqlite3.',muted=True)
        self.host._line(card,'Mitgliederverwaltung und automatischer Profilwechsel sind nicht freigeschaltet: Es fehlen eine konfigurierte offizielle Verwaltungsschnittstelle und die native Desktop-Identit\u00e4tspr\u00fcfung.',muted=True)
        for issue in self.model.get('issues',[]):
            self.host._line(card,issue['profile']+': Sitzungsmetadaten momentan nicht verf\u00fcgbar.')
        if self.ready:self.host._actions(card,[('Quota-Sicherung erstellen',self.backup)])

    def backup(self):
        if self.host.closing:return
        self._queue(lambda:self._get_service().backup(),
            lambda path:self.host._set_status('Quota-Sicherung erstellt: quota.previous.sqlite3'),foreground=True)

    def close(self):
        self.cancel.set()
