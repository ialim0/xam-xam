"""Limite de demandes par élève et déduplication des notifications de Meta."""

from __future__ import annotations

import sqlite3
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from pathlib import Path

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
        store_path: Path | None = None,
    ) -> None:
        self._max_requests = max_requests
        self._window = window_seconds
        self._unlimited = unlimited_numbers
        self._clock = clock
        self._history: dict[str, deque[float]] = {}
        self._store = _open_store(store_path) if store_path is not None else None
        if self._store is not None:
            self._store.execute(
                "CREATE TABLE IF NOT EXISTS requests (user_hash TEXT NOT NULL, ts REAL NOT NULL)"
            )
            self._store.execute("CREATE INDEX IF NOT EXISTS requests_ts ON requests(ts)")
            self._store.execute(
                "CREATE INDEX IF NOT EXISTS requests_user ON requests(user_hash, ts)"
            )

    def allow(self, sender: str, key: str) -> bool:
        """`sender` sert à repérer les numéros illimités ; `key` (haché) indexe l'historique."""
        if normalize_phone_number(sender) in self._unlimited:
            return True
        now = self._clock()
        if self._store is not None:
            with self._store:
                self._store.execute("DELETE FROM requests WHERE ts <= ?", (now - self._window,))
                count = self._store.execute(
                    "SELECT COUNT(*) FROM requests WHERE user_hash = ?", (key,)
                ).fetchone()[0]
                if count >= self._max_requests:
                    return False
                self._store.execute("INSERT INTO requests(user_hash, ts) VALUES (?, ?)", (key, now))
            return True
        history = self._history.setdefault(key, deque())
        while history and history[0] <= now - self._window:
            history.popleft()
        if len(history) >= self._max_requests:
            return False
        history.append(now)
        return True

    def close(self) -> None:
        if self._store is not None:
            self._store.close()


class MessageDeduplicator:
    """Meta peut renvoyer une même notification : chaque identifiant n'est traité qu'une fois."""

    def __init__(
        self,
        max_size: int = 10_000,
        *,
        store_path: Path | None = None,
        hasher: Callable[[str], str] | None = None,
        retention_seconds: float = 7 * 24 * 3600,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if store_path is not None and hasher is None:
            raise ValueError("Une fonction de hachage est nécessaire pour le stockage persistant.")
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._max_size = max_size
        self._hasher = hasher or (lambda value: value)
        self._store = _open_store(store_path) if store_path is not None else None
        self._clock = clock
        self._retention = retention_seconds
        self._last_purge = clock()
        if self._store is not None:
            with self._store:
                self._store.execute(
                    "CREATE TABLE IF NOT EXISTS completed "
                    "(message_hash TEXT PRIMARY KEY, ts REAL NOT NULL)"
                )
                self._store.execute("CREATE INDEX IF NOT EXISTS completed_ts ON completed(ts)")
                self._store.execute(
                    "DELETE FROM completed WHERE ts <= ?", (self._last_purge - retention_seconds,)
                )

    def is_duplicate(self, message_id: str) -> bool:
        key = self._hasher(message_id)
        if key in self._seen:
            return True
        if self._store is not None:
            completed = self._store.execute(
                "SELECT 1 FROM completed WHERE message_hash = ?", (key,)
            ).fetchone()
            if completed is not None:
                return True
        self._seen[key] = None
        if len(self._seen) > self._max_size:
            self._seen.popitem(last=False)
        return False

    def mark_done(self, message_ids: list[str]) -> None:
        """Mémorise uniquement les notifications dont le traitement a abouti."""
        if self._store is None or not message_ids:
            return
        now = self._clock()
        with self._store:
            if now - self._last_purge >= 3600:
                self._store.execute("DELETE FROM completed WHERE ts <= ?", (now - self._retention,))
                self._last_purge = now
            self._store.executemany(
                "INSERT OR REPLACE INTO completed(message_hash, ts) VALUES (?, ?)",
                ((self._hasher(message_id), now) for message_id in message_ids),
            )

    def forget(self, message_ids: list[str]) -> None:
        """Autorise une nouvelle livraison si le traitement a été interrompu."""
        for message_id in message_ids:
            self._seen.pop(self._hasher(message_id), None)

    def close(self) -> None:
        if self._store is not None:
            self._store.close()


def _open_store(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path, timeout=5)
