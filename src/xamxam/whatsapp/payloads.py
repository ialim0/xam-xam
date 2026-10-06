"""Lecture des notifications de l'API WhatsApp Cloud (webhook « messages »).

Seuls les champs utiles sont modélisés ; tout le reste est ignoré.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class MessageKind(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    OTHER = "other"


class MediaRef(_Model):
    id: str
    mime_type: str | None = None


class TextBody(_Model):
    body: str = ""


class RawMessage(_Model):
    id: str
    sender: str = Field(alias="from")
    type: str
    text: TextBody | None = None
    image: MediaRef | None = None
    audio: MediaRef | None = None


class _Value(_Model):
    messages: list[RawMessage] = []


class _Change(_Model):
    field: str = ""
    value: _Value = _Value()


class _Entry(_Model):
    changes: list[_Change] = []


class WebhookPayload(_Model):
    object: str = ""
    entry: list[_Entry] = []


class IncomingMessage(BaseModel):
    """Message entrant simplifié, prêt pour le bot."""

    model_config = ConfigDict(frozen=True)

    message_id: str
    sender: str  # wa_id de l'élève (numéro, chiffres seuls)
    kind: MessageKind
    media_id: str | None = None
    mime_type: str | None = None
    text: str | None = None


def extract_messages(payload: WebhookPayload) -> list[IncomingMessage]:
    """Liste les messages d'élèves ; les statuts de livraison et autres événements sont ignorés."""
    messages = []
    for entry in payload.entry:
        for change in entry.changes:
            for raw in change.value.messages:
                if raw.type == MessageKind.IMAGE and raw.image:
                    kind, media = MessageKind.IMAGE, raw.image
                elif raw.type == MessageKind.AUDIO and raw.audio:
                    kind, media = MessageKind.AUDIO, raw.audio
                elif raw.type == MessageKind.TEXT and raw.text:
                    kind, media = MessageKind.TEXT, None
                else:
                    kind, media = MessageKind.OTHER, None
                messages.append(
                    IncomingMessage(
                        message_id=raw.id,
                        sender=raw.sender,
                        kind=kind,
                        media_id=media.id if media else None,
                        mime_type=media.mime_type if media else None,
                        text=raw.text.body if kind is MessageKind.TEXT and raw.text else None,
                    )
                )
    return messages
