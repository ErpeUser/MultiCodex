"""Small bounded worker queue. No Tk calls or user-visible logging in workers."""
from __future__ import annotations
import queue
import threading
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
        if workers < 1 or max_pending < 1:
            raise ValueError('Worker and pending limits must be positive')
        self.max_pending=max_pending
        self.results=queue.Queue(maxsize=max_pending)
        self._pending=set()
        self._active=set()
        self._mutex=threading.Lock()
        self._closed=False
        self._work=queue.SimpleQueue()
        # ThreadPoolExecutor registers an interpreter-exit join even with
        # shutdown(wait=False). These bounded daemon workers let the GUI apply
        # its cancellation grace period without a stalled I/O call owning exit.
        self._workers=[threading.Thread(target=self._run, name=f'multicodex-{index}', daemon=True)
                       for index in range(workers)]
        for worker in self._workers:
            worker.start()

    @property
    def pending(self):
        with self._mutex:return len(self._pending)

    def submit(self,key:str,work:Callable):
        with self._mutex:
            if self._closed or key in self._pending or len(self._pending)>=self.max_pending:
                raise JobBusy('An operation is already pending')
            self._pending.add(key)
            self._work.put((key,work))

    def _run(self):
        while True:
            item=self._work.get()
            if item is None:
                return
            key,work=item
            del item
            with self._mutex:
                if self._closed:
                    del work
                    continue
                self._active.add(key)
            try:result=JobResult(key,value=work())
            except BaseException as exc:result=JobResult(key,error=exc)
            finally:del work
            with self._mutex:
                self._active.discard(key)
                if self._closed:
                    self._pending.discard(key)
                else:
                    # Accepted jobs remain pending until drained, so the result
                    # queue has exactly one reserved slot for each completion.
                    self.results.put_nowait(result)
            del result

    def drain(self):
        out=[]
        with self._mutex:
            while True:
                try:result=self.results.get_nowait()
                except queue.Empty:break
                self._pending.discard(result.key)
                out.append(result)
        return out

    def close(self):
        with self._mutex:
            if self._closed:
                return
            self._closed=True
            self._pending.intersection_update(self._active)
            while True:
                try:self.results.get_nowait()
                except queue.Empty:break
            while True:
                try:self._work.get_nowait()
                except queue.Empty:break
            for _ in self._workers:
                self._work.put(None)
