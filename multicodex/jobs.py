"""Small bounded worker queue. No Tk calls or user-visible logging in workers."""
from __future__ import annotations
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

class JobBusy(RuntimeError):
    pass

@dataclass
class JobResult:
    key: str
    value: Any = None
    error: BaseException | None = None

class JobRunner:
    def __init__(self, workers=3, max_pending=8):
        self.executor=ThreadPoolExecutor(max_workers=workers,thread_name_prefix='multicodex')
        self.max_pending=max_pending
        self.results=queue.Queue(maxsize=max_pending)
        self._futures={}
        self._mutex=threading.Lock()
        self._closed=False

    @property
    def pending(self):
        with self._mutex:return len(self._futures)

    def submit(self,key:str,work:Callable):
        with self._mutex:
            if self._closed or key in self._futures or len(self._futures)>=self.max_pending:
                raise JobBusy('An operation is already pending')
            future=self.executor.submit(work)
            self._futures[key]=future
        def done(f):
            try:result=JobResult(key,value=f.result())
            except BaseException as exc:result=JobResult(key,error=exc)
            self.results.put_nowait(result)
        future.add_done_callback(done)

    def drain(self):
        out=[]
        while True:
            try:result=self.results.get_nowait()
            except queue.Empty:break
            with self._mutex:self._futures.pop(result.key,None)
            out.append(result)
        return out

    def close(self):
        with self._mutex:self._closed=True
        self.executor.shutdown(wait=False,cancel_futures=True)
