"""Render the new real Tk components with synthetic accounts on isolated Xvfb.

This is NOT the full CustomTkinter application or Windows acceptance. Screenshot
capture requires --isolated-display and Linux; never capture a user's desktop.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time
import tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from multicodex.automation_settings import DEFAULTS
from multicodex.quota import evaluate_snapshot
from multicodex.quota_ui import QuotaPanel, QuotaSettingsPanel
from multicodex.ui_tokens import THEMES


def fixture_model(now):
    rows=[]
    for index,(name,used,weekly,membership,error) in enumerate([
        ('Entwicklung',28,42,'WORKSPACE_ACCESS_UNKNOWN',None),
        ('Team / historischer Business-Zugang',100,64,'ACCESS_REMOVED',None),
        ('Review',93,88,'WORKSPACE_ACCESS_UNKNOWN',None),
        ('Archiv',None,None,'WORKSPACE_ACCESS_UNKNOWN','NOT_AUTHENTICATED')]):
        key=f'{index+1:064x}'
        account={'account_key':key,'profile_id':name,'email':f'konto-{index+1}@example.invalid',
            'workspace_id':None,'plan_type':'business','seat_type':None,'membership_state':membership,
            'last_error_code':error,'auth_state':'SESSION_EXPIRED' if error else 'AUTHENTICATED',
            'last_error_at':now if error else None,'context_revision':0}
        snapshot={'snapshot_id':f'{index+1:032x}','account_key':key,'source':'official-app-server',
            'account_id':None,'workspace_id':None,'plan_type':'business','seat_type':None,
            'ordinary_usage_allowed':True,'spend_control_reached':False,
            'observed_at':now-20000 if membership=='ACCESS_REMOVED' else now-30,
            'primary_present':True,'primary_used_percent':used,'primary_duration_minutes':300,
            'primary_reset_at':now-600 if membership=='ACCESS_REMOVED' else now+7200,
            'secondary_present':True,'secondary_used_percent':weekly,'secondary_duration_minutes':10080,
            'secondary_reset_at':now+172800,'access_state':'WORKSPACE_MEMBER' if membership=='ACCESS_REMOVED' else membership,'context_revision':0}
        quota=evaluate_snapshot(snapshot,account,now=now)
        rows.append({'account':account,'snapshot':snapshot,'quota':quota,'binding_available':True,
                     'polling':{'suspended':bool(error)}})
    return {'rows':rows,'settings':{**DEFAULTS,'allowed_profiles':['Entwicklung']},
            'profiles':['Entwicklung','Review','Archiv'],'issues':[],'operation':{'state':'IDLE'}}


def render(output,isolated_display):
    if not isolated_display or platform.system()!='Linux' or not os.environ.get('DISPLAY'):
        raise RuntimeError('Use an isolated Linux Xvfb display; no desktop capture is allowed')
    from PIL import ImageGrab
    output.mkdir(parents=True,exist_ok=True)
    report={'environment':platform.platform(),'tk':tk.TkVersion,'kind':'isolated-linux-tk-components',
            'synthetic_accounts':True,'full_customtkinter_app':False,'windows_acceptance':False,'screens':[]}
    for name,theme,width,height,kind in (
        ('quota-dark','dark',1050,800,'quota'),('quota-light','light',1050,800,'quota'),
        ('quota-small','dark',680,740,'quota'),('quota-empty','light',900,700,'empty'),
        ('quota-settings','dark',900,720,'settings'),('quota-history','light',1050,800,'history')):
        root=tk.Tk();root.title('MultiCodex / Linux widget test / synthetic data')
        root.geometry(f'{width}x{height}+0+0');root.configure(bg=THEMES[theme]['canvas'])
        tk.Label(root,text='TESTDATEN  /  Echtes Tk-Rendering unter Linux, keine Windows-Abnahme',
            bg=THEMES[theme]['rail'],fg=THEMES[theme]['muted'],anchor='w',padx=20,pady=9).pack(fill='x')
        model=fixture_model(int(time.time()))
        if kind=='settings':
            panel=QuotaSettingsPanel(root,theme=theme,model=model,on_save=lambda data:None)
        else:
            panel=QuotaPanel(root,theme=theme,on_refresh=lambda key:None,on_history=lambda *args:None)
            if kind=='empty':model['rows']=[]
            panel.set_model(model)
            if kind!='empty':
                panel.table.selection_set(f'{2:064x}');panel.select_row()
        panel.pack(fill='both',expand=True,padx=22,pady=18)
        root.update_idletasks();root.update()
        capture=root
        if kind not in ('settings','empty'):panel.table.see(f'{2:064x}');root.update()
        if kind=='history':
            historical=model['rows'][1]['snapshot']
            history=[{**historical,'observed_at':historical['observed_at']-offset*3600,
                      'primary_used_percent':100-offset*9,'secondary_used_percent':64-offset}
                     for offset in range(4)]
            panel.show_history(f'{2:064x}',history)
            tk.Label(panel.history_window,text='TESTDATEN / Linux-Tk-Komponente, keine Windows-Abnahme',
                bg=THEMES[theme]['rail'],fg=THEMES[theme]['muted'],padx=12,pady=5).grid(row=4,column=0,sticky='ew')
            root.update_idletasks();root.update();capture=panel.history_window
        box=(capture.winfo_rootx(),capture.winfo_rooty(),capture.winfo_rootx()+capture.winfo_width(),capture.winfo_rooty()+capture.winfo_height())
        image=ImageGrab.grab(bbox=box,xdisplay=os.environ['DISPLAY'])
        path=output/(name+'.png');image.save(path)
        report['screens'].append({'file':path.name,'size':list(image.size),'theme':theme,'fixture':kind,
                                 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        root.destroy()
    (output/'widget-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--isolated-display',action='store_true')
    args=parser.parse_args()
    render(args.output,args.isolated_display)
