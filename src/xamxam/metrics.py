"""Métriques d'un traitement, sans aucun contenu utilisateur.

Une variable de contexte porte les métriques du traitement en cours : les appels aux
services (Kiriku, Gemini, Meta) et aux caches s'y enregistrent d'eux-mêmes, y compris
depuis les threads lancés par asyncio.to_thread, qui copient le contexte.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass
class JobMetrics:
    user: str  # identifiant haché, jamais le numéro
    inputs: Counter[str] = field(default_factory=Counter)
    requests: Counter[str] = field(default_factory=Counter)
    cache: Counter[str] = field(default_factory=Counter)
    durations_ms: dict[str, int] = field(default_factory=dict)
    outcome: str = "en_cours"
    verification: str | None = None
    error: str | None = None  # type d'exception seulement

    def as_dict(self) -> dict[str, Any]:
        return {
            "user": self.user,
            "inputs": dict(self.inputs),
            "outcome": self.outcome,
            "verification": self.verification,
            "requests": dict(self.requests),
            "cache": dict(self.cache),
            "durations_ms": self.durations_ms,
            "error": self.error,
        }


_current: ContextVar[JobMetrics | None] = ContextVar("xamxam_job_metrics", default=None)


@contextmanager
def tracking(metrics: JobMetrics) -> Iterator[JobMetrics]:
    token = _current.set(metrics)
    try:
        yield metrics
    finally:
        _current.reset(token)


def record_request(service: str) -> None:
    metrics = _current.get()
    if metrics is not None:
        metrics.requests[service] += 1


def record_cache(cache: str, *, hit: bool) -> None:
    metrics = _current.get()
    if metrics is not None:
        metrics.cache[f"{cache}_{'hit' if hit else 'miss'}"] += 1


@contextmanager
def timed(stage: str) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        metrics = _current.get()
        if metrics is not None:
            elapsed = int((time.perf_counter() - start) * 1000)
            metrics.durations_ms[stage] = metrics.durations_ms.get(stage, 0) + elapsed
