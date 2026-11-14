"""Render real Tk queue/directory components on an explicitly isolated Linux display."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from multicodex.activation_ui import ActivationPanel
from multicodex.workspace_ui import WorkspacePanel
from multicodex.automation_settings import DEFAULTS
from multicodex.ui_tokens import THEMES


def render(output,isolated_display):
    if not isolated_display or platform.system()!='Linux' or not os.environ.get('DISPLAY'):
        raise RuntimeError('Only an explicitly isolated Linux display may be captured')
    from PIL import ImageGrab
    output.mkdir(parents=True,exist_ok=True)
    report={'kind':'isolated-linux-tk-components','synthetic_accounts':True,
        'full_app':False,'windows_acceptance':False,'screens':[]}
    for name,theme,width,kind in [('activation-dark','dark',850,'queue'),
        ('activation-light','light',850,'queue'),('activation-small','dark',640,'queue'),
        ('workspace-dark','dark',850,'directory'),('workspace-light','light',850,'directory')]:
        root=tk.Tk();root.geometry(f'{width}x500+0+0');root.configure(bg=THEMES[theme]['canvas'])
        root.title('MultiCodex / Linux Tk components / test data')
        tk.Label(root,text='TESTDATEN / Linux-Tk-Komponenten, keine Windows-Abnahme',
            bg=THEMES[theme]['rail'],fg=THEMES[theme]['muted'],padx=16,pady=8).pack(fill='x')
        if kind=='queue':
            panel=ActivationPanel(root,theme=theme,on_enqueue=lambda k:None,
                on_action=lambda *a:None,on_enabled=lambda v:None)
            panel.set_model({'rows':[{'account':{'account_key':'a'*64,'profile_id':'Entwicklung',
                'email':'entwicklung@example.invalid','session_id':'default'},'binding_available':True}],
                'settings':{**DEFAULTS,'automatic_activation_enabled':True,'allowed_profiles':['Entwicklung']},
                'activation_runs':[{'run_id':f'{i+1:032x}','profile':p,'session_id':'default',
                    'state':s,'old_session':'default' if s=='ROLLBACK_REQUIRED' else None}
                    for i,(p,s) in enumerate([('Entwicklung','WAITING_FOR_RESET'),('Review','COMPLETED'),
                        ('Testprofil','ROLLBACK_REQUIRED')])]})
            panel.tree.selection_set(f'{3:032x}');panel.selected()
        else:
            panel=WorkspacePanel(root,theme=theme,on_read=lambda *a:None)
            panel.workspace.insert(0,'ws_beispiel')
            panel.set_model({'workspace_id':'ws_beispiel','complete':True,'members':[
                {'id':'user_entwicklung','email':'entwicklung@example.invalid'},
                {'id':'user_review','email':'review@example.invalid'}]})
        panel.pack(fill='both',expand=True,padx=18,pady=14)
        root.update_idletasks();root.update()
        box=(root.winfo_rootx(),root.winfo_rooty(),root.winfo_rootx()+root.winfo_width(),
             root.winfo_rooty()+root.winfo_height())
        path=output/(name+'.png');ImageGrab.grab(bbox=box,xdisplay=os.environ['DISPLAY']).save(path)
        report['screens'].append({'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                                 'width':root.winfo_width(),'height':root.winfo_height()})
        root.destroy()
    (output/'automation-widget-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--isolated-display',action='store_true')
    args=parser.parse_args();render(args.output,args.isolated_display)
