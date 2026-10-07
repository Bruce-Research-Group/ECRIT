"""Device work off the Tk thread.

Serial calls can block for a long time (G28 answers only once homing is done),
and Tk widgets may only be touched from the thread running mainloop. So every
device call goes through one worker thread, in the order it was submitted, and
its result comes back to the Tk thread through a queue polled with after().
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)


class TaskRunner:
    def __init__(self, root: tk.Misc, poll_ms: int = 50):
        self.root = root
        self.poll_ms = poll_ms
        self._jobs: "queue.Queue[tuple]" = queue.Queue()
        self._results: "queue.Queue[tuple]" = queue.Queue()
        self._pending = 0
        threading.Thread(target=self._work, name="device-worker", daemon=True).start()
        self._poll()

    @property
    def busy(self) -> bool:
        return self._pending > 0

    def submit(self, fn: Callable[[], Any], on_done: Optional[Callable[[Any], None]] = None,
               on_error: Optional[Callable[[Exception], None]] = None) -> None:
        """Run fn() on the worker. on_done(result) or on_error(exception) runs
        on the Tk thread afterwards; errors default to a message box."""
        self._pending += 1
        self._jobs.put((fn, on_done, on_error or self._show_error))

    def post(self, fn: Callable[[], None]) -> None:
        """Run fn() on the Tk thread. Safe to call from any thread."""
        self._results.put((fn, ()))

    def _work(self) -> None:
        while True:
            fn, on_done, on_error = self._jobs.get()
            try:
                result = fn()
            except Exception as e:
                log.debug("task failed", exc_info=True)
                self._results.put((self._finish, (on_error, e)))
            else:
                self._results.put((self._finish, (on_done, result)))

    def _finish(self, callback: Optional[Callable[[Any], None]], value: Any) -> None:
        self._pending -= 1
        if callback is not None:
            callback(value)

    def _poll(self) -> None:
        while True:
            try:
                fn, args = self._results.get_nowait()
            except queue.Empty:
                break
            try:
                fn(*args)
            except Exception:
                log.exception("UI callback failed")
        self.root.after(self.poll_ms, self._poll)

    @staticmethod
    def _show_error(e: Exception) -> None:
        log.error("%s", e)
        messagebox.showerror(title="Error", message=str(e) or type(e).__name__)
