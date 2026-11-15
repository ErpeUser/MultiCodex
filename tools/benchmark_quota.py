"""Measure cached quota refresh on temporary synthetic stores, never live accounts.

The comparison is an emulation of the former per-account read pattern against
the same current database, not a historical application timing. All timings are
instrumented local measurements; provider latency is deliberately not measured.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import platform
import sqlite3
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from multicodex.jobs import JobRunner
from multicodex.locks import FileLock
from multicodex.quota_service import QuotaService


@contextmanager
def instrument():
    metrics = dict(connections=0, transactions=0, json_parses=0,
                   json_parse_ms=0.0, lock_acquisitions=0, lock_acquire_ms=0.0)
    connect, loads, enter = sqlite3.connect, json.loads, FileLock.__enter__
    def trace(sql):
        if sql.startswith('BEGIN'):
            metrics['transactions'] += 1
    def connected(*args, **kwargs):
        metrics['connections'] += 1
        db = connect(*args, **kwargs)
        db.set_trace_callback(trace)
        return db
    def parsed(*args, **kwargs):
        start = time.perf_counter()
        try:
            return loads(*args, **kwargs)
        finally:
            metrics['json_parses'] += 1
            metrics['json_parse_ms'] += (time.perf_counter() - start) * 1000
    def locked(lock):
        start = time.perf_counter()
        try:
            return enter(lock)
        finally:
            metrics['lock_acquisitions'] += 1
            metrics['lock_acquire_ms'] += (time.perf_counter() - start) * 1000
    with patch('sqlite3.connect', connected), patch('json.loads', parsed), patch.object(FileLock, '__enter__', locked):
        yield metrics


def measure(count):
    import psutil
    import tkinter as tk
    from multicodex.quota_ui import QuotaPanel
    with tempfile.TemporaryDirectory(prefix='multicodex-benchmark-') as directory:
        app = SimpleNamespace(store=SimpleNamespace(list=lambda: [], issues=[]))
        service = QuotaService(Path(directory), app, provider=SimpleNamespace(), clock=lambda: 1000)
        keys=[]
        for index in range(count):
            key=service.store.register(profile_id='Fixture', session_id=f'{index:032x}',
                email=f'fixture{index}@example.invalid', account_id=f'account{index}', now=900)
            service.store.capture(key, {'source':'official-app-server', 'account_id':f'account{index}',
                'windows':[{'label':'primary', 'used_percent':40, 'minutes':300, 'reset_at':18000}]}, observed_at=950)
            keys.append(key)
        with instrument() as legacy:
            start=time.perf_counter()
            for key in keys:
                service.store.latest(key);service.store.poll_state(key)
            legacy['elapsed_ms']=(time.perf_counter()-start)*1000
        root=tk.Tk();root.withdraw()
        panel=QuotaPanel(root,on_refresh=lambda key:None,on_history=lambda *args:None)
        panel.pack(fill='both',expand=True)
        runner=JobRunner(workers=1)
        beats=[];last=time.perf_counter();alive=True;heartbeat_id=None
        def heartbeat():
            nonlocal last,heartbeat_id
            now=time.perf_counter();beats.append((now-last)*1000);last=now
            if alive:heartbeat_id=root.after(5,heartbeat)
        heartbeat()
        process=psutil.Process();rss_before=process.memory_info().rss;cpu_before=time.process_time()
        try:
            with instrument() as current:
                models=[];durations=[];render_ms=[];threads=set();rebuilds=0
                for iteration in range(5):
                    def work():
                        threads.add(threading.get_ident())
                        start=time.perf_counter();model=service.work()
                        durations.append((time.perf_counter()-start)*1000)
                        return model
                    runner.submit('refresh',work)
                    deadline=time.monotonic()+30
                    while runner.pending:
                        root.update()
                        results=runner.drain()
                        if results:
                            result=results[0]
                            if result.error:raise result.error
                            models.append(result.value)
                        if time.monotonic()>deadline:raise TimeoutError('Benchmark worker timed out')
                        time.sleep(.001)
                    before=tuple(panel.winfo_children())
                    start=time.perf_counter();panel.set_model(models[-1]);root.update_idletasks()
                    render_ms.append((time.perf_counter()-start)*1000)
                    rebuilds += tuple(panel.winfo_children()) != before
                current.update(refresh_ms=durations, render_ms=render_ms,
                    full_panel_widget_rebuilds=rebuilds, worker_threads=len(threads),
                    eventloop_max_interval_ms=max(beats), eventloop_target_ms=5,
                    process_cpu_ms=(time.process_time()-cpu_before)*1000,
                    rss_delta_bytes=process.memory_info().rss-rss_before)
        finally:
            alive=False
            if heartbeat_id is not None:root.after_cancel(heartbeat_id)
            runner.close();root.destroy()
        return dict(accounts=count, iterations=5, cached_refresh=current, legacy_reads=legacy)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=dict(platform=platform.platform(),python=sys.version,scope=__doc__,
        lock_metric='elapsed acquisition including uncontended lock/file I/O; no contention injected',
        results=[measure(count) for count in (1,10,100,500)])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    for row in report['results']:
        metrics=row['cached_refresh']
        print(row['accounts'],round(sum(metrics['refresh_ms'])/5,2),'ms',
              metrics['connections']/5,'connections/refresh')


if __name__=='__main__':main()
