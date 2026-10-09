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


def test_llm_provider_is_gemini_by_default_and_rodium_is_optional() -> None:
    assert Settings.from_env({"GEMINI_API_KEY": "g"}).llm_provider == "gemini"
    assert Settings.from_env({}).llm_provider == "gemini"
    # Compatibilité : une seule clé Rodium suffit à choisir Rodium.
    assert Settings.from_env({"RODIUM_API_KEY": "r"}).llm_provider == "rodium"
    both = {"GEMINI_API_KEY": "g", "RODIUM_API_KEY": "r"}
    assert Settings.from_env({**both, "LLM_PROVIDER": "Gemini"}).llm_provider == "gemini"
    chosen = Settings.from_env({"GEMINI_API_KEY": "g", "LLM_PROVIDER": "rodium"})
    assert "RODIUM_API_KEY" in chosen.missing_bot_variables()
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        Settings.from_env({"LLM_PROVIDER": "openai"})


def test_settings_bot_variables() -> None:
    settings = Settings.from_env(
        {
            "UNLIMITED_NUMBERS": "+221 77 123 45 67, 221780000000,, ",
            "WHATSAPP_APP_SECRET": "s3cret",
            "LOG_HASH_KEY": "k3y",
            "XAMXAM_CACHE_DIR": "/cache",
            "XAMXAM_STATE_DIR": "/state",
        }
    )
    assert settings.unlimited_numbers == {"221771234567", "221780000000"}
    assert settings.cache_dir == Path("/cache")
    assert settings.state_dir == Path("/state")
    assert settings.whatsapp_graph_api_version == "v23.0"
    assert "WHATSAPP_APP_SECRET" not in settings.missing_bot_variables()
    assert "GEMINI_API_KEY" in settings.missing_bot_variables()
    # Kiriku (voix) et TimaLens (vidéo) sont optionnels.
    assert not {"KVICC_TTS_URL", "KVICC_API_KEY", "TIMALENS_API_KEY"} & set(
        settings.missing_bot_variables()
    )
    assert Settings.from_env({"XAMXAM_ENABLE_DEV_ROUTES": "true"}).enable_dev_routes
    gemini = Settings.from_env(
        {
            "GEMINI_API_KEY": "g-secret",
            "TIMALENS_API_KEY": "tlak_x",
            "TIMALENS_MAX_CREDITS": "12,5",
        }
    )
    assert gemini.gemini_model == "gemini-3.5-flash"
    assert gemini.gemini_fallback_model == "gemini-3.6-flash"
    assert gemini.video_enabled and gemini.timalens_max_credits == 12.5
    assert gemini.timalens_voice == "soynade_wo_female"
    assert "g-secret" not in repr(gemini) and "tlak_x" not in repr(gemini)
    with pytest.raises(ValueError, match="Nombre invalide"):
        Settings.from_env({"TIMALENS_MAX_CREDITS": "beaucoup"})
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
    assert not settings.audio_self_check
    assert BotSettings.from_env({"XAMXAM_AUDIO_SELF_CHECK": "true"}).audio_self_check
    assert BotSettings().reply_mode == "audio"
    assert BotSettings().waiting_sticker
    assert not BotSettings.from_env({"XAMXAM_WAITING_STICKER": "non"}).waiting_sticker
    assert BotSettings.from_env({"XAMXAM_REPLY_MODE": "Texte"}).reply_mode == "texte"
    with pytest.raises(XamXamError, match="XAMXAM_REPLY_MODE"):
        BotSettings.from_env({"XAMXAM_REPLY_MODE": "video"})
    with pytest.raises(XamXamError, match="XAMXAM_AUDIO_SELF_CHECK"):
        BotSettings.from_env({"XAMXAM_AUDIO_SELF_CHECK": "maybe"})
    with pytest.raises(XamXamError, match="XAMXAM_MAX_EXPLANATION_CHARS"):
        BotSettings.from_env({"XAMXAM_MAX_EXPLANATION_CHARS": "beaucoup"})


def test_messages_override(tmp_path: Path) -> None:
    path = tmp_path / "messages.json"
    path.write_text(json.dumps({"ack": "Jërëjëf !"}), encoding="utf-8")
    messages = BotMessages.from_json_file(path)
    assert messages.ack == "Jërëjëf !"
    assert messages.error == BotMessages().error
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


def test_every_variable_read_by_settings_is_isolated_in_tests() -> None:
    # Garde-fou : une variable lue par Settings mais absente de conftest._ENV_VARS
    # laisserait l'environnement du développeur influencer les tests.
    import re

    import conftest

    source = (Path(__file__).parents[1] / "src/xamxam/config.py").read_text(encoding="utf-8")
    read = set(re.findall(r'_read\(env, "([A-Z0-9_]+)"\)', source))
    assert read <= set(conftest._ENV_VARS), sorted(read - set(conftest._ENV_VARS))
