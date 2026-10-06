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

    @property
    def cache_identity(self) -> str:
        """Tout ce qui, en plus du texte et de la langue, change l'audio produit
        (modèle, vitesse…). Sert à construire la clé du cache audio."""
        return self.name

    @abstractmethod
    def synthesize(self, text: str, *, language: str = "wo") -> bytes:
        """Retourne l'audio au format WAV."""


class STTProvider(ABC):
    """Reconnaissance vocale : audio WAV → texte."""

    name: str

    @property
    def cache_identity(self) -> str:
        """Tout ce qui, en plus de l'audio et de la langue, change la transcription."""
        return self.name

    @abstractmethod
    def transcribe(self, audio: bytes, *, language: str = "wo") -> str:
        """Retourne la transcription de l'audio."""
