"""Interfaces abstraites des fournisseurs TTS et STT."""

from __future__ import annotations

from abc import ABC, abstractmethod

from xamxam.errors import XamXamError


class ProviderError(XamXamError):
    """Échec d'un appel à un fournisseur."""


class ProviderNotConfiguredError(ProviderError):
    """Le fournisseur demandé n'a pas les variables d'environnement nécessaires."""


class TTSProvider(ABC):
    """Synthèse vocale : texte → audio WAV."""

    name: str

    @abstractmethod
    def synthesize(self, text: str, *, language: str = "wo") -> bytes:
        """Retourne l'audio au format WAV."""


class STTProvider(ABC):
    """Reconnaissance vocale : audio WAV → texte."""

    name: str

    @abstractmethod
    def transcribe(self, audio: bytes, *, language: str = "wo") -> str:
        """Retourne la transcription de l'audio."""
