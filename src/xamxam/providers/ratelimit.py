"""Limitation du débit global vers l'API Kiriku.

Le quota (30 requêtes par minute) est partagé entre TTS et STT et entre tous les élèves :
un seul limiteur doit donc servir toutes les requêtes du processus. Chaque appel réserve
le prochain créneau libre, ce qui forme une file d'attente FIFO et permet d'estimer
l'attente avant de commencer un traitement.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class RateLimiter:
    """File d'attente à créneaux réguliers, utilisable depuis plusieurs threads."""

    def __init__(
        self,
        requests_per_minute: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._interval = 60.0 / requests_per_minute if requests_per_minute > 0 else 0.0
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_slot: float | None = None

    @property
    def interval(self) -> float:
        return self._interval

    def reserve(self) -> float:
        """Réserve le prochain créneau et retourne l'attente (en secondes) avant de l'utiliser."""
        with self._lock:
            now = self._clock()
            slot = now if self._next_slot is None else max(now, self._next_slot)
            self._next_slot = slot + self._interval
            return slot - now

    def acquire(self) -> None:
        """Bloque jusqu'au prochain créneau disponible."""
        wait = self.reserve()
        if wait > 0:
            self._sleep(wait)

    def estimated_wait(self, requests: int) -> float:
        """Attente estimée avant que `requests` nouvelles requêtes soient toutes passées."""
        if requests <= 0:
            return 0.0
        with self._lock:
            now = self._clock()
            backlog = 0.0 if self._next_slot is None else max(0.0, self._next_slot - now)
        return backlog + (requests - 1) * self._interval
