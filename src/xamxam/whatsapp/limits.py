"""Limite de demandes par élève et déduplication des notifications de Meta."""

from __future__ import annotations

import time
from collections import OrderedDict, deque
from collections.abc import Callable

from xamxam.config import normalize_phone_number


class UserRateLimiter:
    """Fenêtre glissante : au plus `max_requests` demandes par `window_seconds` et par élève.

    Les numéros de `unlimited_numbers` (équipe, démos) ne sont jamais limités.
    """

    def __init__(
        self,
        max_requests: int,
        *,
        window_seconds: float = 3600.0,
        unlimited_numbers: frozenset[str] = frozenset(),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_requests = max_requests
        self._window = window_seconds
        self._unlimited = unlimited_numbers
        self._clock = clock
        self._history: dict[str, deque[float]] = {}

    def allow(self, sender: str, key: str) -> bool:
        """`sender` sert à repérer les numéros illimités ; `key` (haché) indexe l'historique."""
        if normalize_phone_number(sender) in self._unlimited:
            return True
        now = self._clock()
        history = self._history.setdefault(key, deque())
        while history and history[0] <= now - self._window:
            history.popleft()
        if len(history) >= self._max_requests:
            return False
        history.append(now)
        return True


class MessageDeduplicator:
    """Meta peut renvoyer une même notification : chaque identifiant n'est traité qu'une fois."""

    def __init__(self, max_size: int = 10_000) -> None:
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._max_size = max_size

    def is_duplicate(self, message_id: str) -> bool:
        if message_id in self._seen:
            return True
        self._seen[message_id] = None
        if len(self._seen) > self._max_size:
            self._seen.popitem(last=False)
        return False
