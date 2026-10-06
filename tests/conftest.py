from pathlib import Path

import pytest

from xamxam.lexicon import Lexicon, LexiconIndex, load_lexicon
from xamxam.pipeline import XamXamPipeline

ROOT = Path(__file__).resolve().parents[1]
LEXICON_PATH = ROOT / "data" / "lexicon" / "xam_xam_lexique_v0.json"
SENTENCES_PATH = ROOT / "data" / "eval" / "phrases_pythagore_thales.csv"

# Toutes les variables lues par Xam-Xam : les tests doivent passer sans aucune clé, même si
# le poste du développeur en définit.
_ENV_VARS = (
    "KVICC_TTS_URL",
    "KVICC_STT_URL",
    "KVICC_API_KEY",
    "TIMALENS_API_KEY",
    "WHATSAPP_TOKEN",
    "WHATSAPP_PHONE_NUMBER_ID",
    "WHATSAPP_VERIFY_TOKEN",
    "WHATSAPP_APP_SECRET",
    "WHATSAPP_GRAPH_API_VERSION",
    "LLM_PROVIDER",
    "BEDROCK_MODEL_ID",
    "BEDROCK_REGION",
    "SELFHOSTED_BASE_URL",
    "SELFHOSTED_MODEL",
    "SELFHOSTED_API_KEY",
    "TRANSLATE_FROM_FRENCH",
    "LOG_HASH_KEY",
    "UNLIMITED_NUMBERS",
    "XAMXAM_CACHE_DIR",
    "XAMXAM_MESSAGES_PATH",
    "XAMXAM_GROUPING_WINDOW_SECONDS",
    "XAMXAM_MAX_EXPLANATION_CHARS",
    "XAMXAM_USER_REQUESTS_PER_HOUR",
    "XAMXAM_NUMBER_LANGUAGE",
)


@pytest.fixture(autouse=True)
def _no_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def lexicon() -> Lexicon:
    return load_lexicon(LEXICON_PATH)


@pytest.fixture
def index(lexicon: Lexicon) -> LexiconIndex:
    return LexiconIndex(lexicon)


@pytest.fixture
def pipeline(lexicon: Lexicon) -> XamXamPipeline:
    return XamXamPipeline(lexicon)


@pytest.fixture
def anyio_backend() -> str:
    # Tests asynchrones (plugin anyio, fourni avec Starlette) : boucle asyncio uniquement.
    return "asyncio"
