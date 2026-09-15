"""Hintergrundlaeufe.

Ein Screening ueber mehrere hundert Titel dauert Minuten - das darf die
Oberflaeche nicht blockieren. Ein einzelner Arbeitsthread genuegt und
verhindert nebenbei, dass sich zwei Laeufe gegenseitig die Kursquelle
wegdrosseln.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

log = logging.getLogger(__name__)


@dataclass
class JobState:
    name: str = ""
    label: str = ""
    running: bool = False
    current: int = 0
    total: int = 0
    message: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str = ""
    result: dict = field(default_factory=dict)

    @property
    def percent(self) -> int:
        return int(self.current / self.total * 100) if self.total else 0


class JobRunner:
    def __init__(self) -> None:
        self._queue: queue.Queue[tuple[str, str, Callable[[Callable], dict]]] = queue.Queue()
        self._lock = threading.Lock()
        self.state = JobState()
        self.history: list[JobState] = []
        self._worker = threading.Thread(target=self._loop, daemon=True, name="job-runner")
        self._worker.start()

    @property
    def busy(self) -> bool:
        with self._lock:
            return self.state.running

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    def submit(self, name: str, label: str, fn: Callable[[Callable], dict]) -> bool:
        """Auftrag einreihen. Doppelte Auftraege werden verworfen."""
        with self._lock:
            if self.state.running and self.state.name == name:
                return False
        self._queue.put((name, label, fn))
        return True

    def _progress(self, current: int, total: int, message: str) -> None:
        with self._lock:
            self.state.current = current
            self.state.total = total
            self.state.message = message

    def _loop(self) -> None:
        while True:
            name, label, fn = self._queue.get()
            with self._lock:
                self.state = JobState(
                    name=name, label=label, running=True, started_at=datetime.now(),
                    message="gestartet",
                )
            try:
                result = fn(self._progress)
                with self._lock:
                    self.state.result = result or {}
                    self.state.message = "fertig"
            except Exception as exc:
                log.exception("Lauf '%s' fehlgeschlagen", name)
                with self._lock:
                    self.state.error = str(exc)
                    self.state.message = "fehlgeschlagen"
            finally:
                with self._lock:
                    self.state.running = False
                    self.state.finished_at = datetime.now()
                    self.history.insert(0, self.state)
                    del self.history[12:]
                self._queue.task_done()
