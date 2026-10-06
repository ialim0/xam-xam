import json
from pathlib import Path

import pytest

from xamxam.config import Settings, normalize_phone_number
from xamxam.errors import XamXamError
from xamxam.normalize import NumberLanguage
from xamxam.whatsapp.bot import truncate_explanation
from xamxam.whatsapp.messages import BotMessages
from xamxam.whatsapp.privacy import IdHasher
from xamxam.whatsapp.settings import BotSettings


def test_settings_bot_variables() -> None:
    settings = Settings.from_env(
        {
            "UNLIMITED_NUMBERS": "+221 77 123 45 67, 221780000000,, ",
            "WHATSAPP_APP_SECRET": "s3cret",
            "LOG_HASH_KEY": "k3y",
            "XAMXAM_CACHE_DIR": "/cache",
        }
    )
    assert settings.unlimited_numbers == {"221771234567", "221780000000"}
    assert settings.cache_dir == Path("/cache")
    assert settings.whatsapp_graph_api_version == "v23.0"
    assert "WHATSAPP_APP_SECRET" not in settings.missing_bot_variables()
    assert "GEMINI_MODEL" in settings.missing_bot_variables()
    text = repr(settings)
    assert "s3cret" not in text and "k3y" not in text and "221771234567" not in text
    assert normalize_phone_number("+221 (77) 123-45-67") == "221771234567"


def test_bot_settings_from_env() -> None:
    settings = BotSettings.from_env(
        {"XAMXAM_USER_REQUESTS_PER_HOUR": "3", "XAMXAM_NUMBER_LANGUAGE": "wo"}
    )
    assert settings.user_requests_per_hour == 3
    assert settings.number_language is NumberLanguage.WOLOF
    assert settings.grouping_window_seconds == 8.0
    with pytest.raises(XamXamError, match="XAMXAM_MAX_EXPLANATION_CHARS"):
        BotSettings.from_env({"XAMXAM_MAX_EXPLANATION_CHARS": "beaucoup"})


def test_messages_override(tmp_path: Path) -> None:
    path = tmp_path / "messages.json"
    path.write_text(json.dumps({"ack": "Jërëjëf !"}), encoding="utf-8")
    messages = BotMessages.from_json_file(path)
    assert messages.ack == "Jërëjëf !"
    assert messages.help == BotMessages().help
    path.write_text(json.dumps({"inconnu": "x"}), encoding="utf-8")
    with pytest.raises(XamXamError, match="inconnu"):
        BotMessages.from_json_file(path)


def test_id_hasher() -> None:
    hasher = IdHasher("cle")
    assert hasher("221771234567") == hasher("221771234567")
    assert hasher("221771234567") != IdHasher("autre")("221771234567")
    assert "221771234567" not in hasher("221771234567")
    assert len(IdHasher(None)("x")) == 16


def test_truncate_explanation() -> None:
    assert truncate_explanation("  Court.  ", 100) == "Court."
    assert truncate_explanation("Une phrase. Deux phrases longues.", 20) == "Une phrase."
    assert truncate_explanation("sanspoint" * 5, 10) == "sanspoints"
