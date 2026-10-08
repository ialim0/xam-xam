"""Mémoire courte de conversation, en mémoire vive uniquement.

Rien n'est écrit sur disque : un redémarrage efface toutes les conversations. Chaque élève
(identifiant haché) garde ses derniers échanges en texte, oubliés après une période
d'inactivité. Les photos et audios ne sont jamais conservés : seuls des repères textuels
(« [photo jointe] ») et le texte des réponses le sont.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from xamxam.llm import MathSolution

STUDENT = "eleve"
TUTOR = "xamxam"


@dataclass
class Conversation:
    turns: deque[tuple[str, str]]
    last_activity: float
    # Dernier exercice résolu : sert à l'audio, à la vidéo et aux questions de suivi.
    solution: MathSolution | None = None
    audio_sent: bool = False  # une explication audio a déjà été envoyée pour cet exercice
    video_in_progress: bool = False
    videos: list[str] = field(default_factory=list)  # titres des vidéos envoyées

    def note(self, role: str, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if self.turns and self.turns[-1][0] == role:
            previous = self.turns.pop()[1]
            text = f"{previous}\n{text}"
        self.turns.append((role, text))


class ConversationMemory:
    def __init__(
        self,
        *,
        ttl_seconds: float = 3600.0,
        max_turns: int = 20,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_turns = max_turns
        self._clock = clock
        self._conversations: dict[str, Conversation] = {}

    def get(self, user: str) -> Conversation:
        """Conversation de l'élève, neuve si elle a expiré. Purge au passage."""
        now = self._clock()
        expired = [k for k, c in self._conversations.items() if now - c.last_activity > self._ttl]
        for key in expired:
            # Une vidéo en cours garde la conversation vivante jusqu'à son envoi.
            if not self._conversations[key].video_in_progress:
                del self._conversations[key]
        conversation = self._conversations.get(user)
        if conversation is None:
            conversation = Conversation(deque(maxlen=self._max_turns), now)
            self._conversations[user] = conversation
        conversation.last_activity = now
        return conversation

    def __len__(self) -> int:
        return len(self._conversations)


def history_messages(conversation: Conversation) -> list[dict[str, Any]]:
    """Échanges passés au format des messages de l'agent (rôles user / assistant alternés)."""
    messages: list[dict[str, Any]] = [
        {"role": "user" if role == STUDENT else "assistant", "content": text}
        for role, text in conversation.turns
    ]
    # L'historique commence par l'élève, jamais par une réponse orpheline.
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    return messages
