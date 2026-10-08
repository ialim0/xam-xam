from pathlib import Path

import pytest

from xamxam.lexicon import VALIDATED_AND_DRAFT, Lexicon, LexiconIndex, load_lexicon
from xamxam.pipeline import XamXamPipeline

ROOT = Path(__file__).resolve().parents[1]
# Données réelles du dépôt (vérifiées par des tests dédiés : schéma, alphabet, check).
REPO_LEXICON_PATH = ROOT / "data" / "lexicon" / "xam_xam_lexique_v0.json"
REPO_SENTENCES_PATH = ROOT / "data" / "eval" / "phrases_pythagore_thales.csv"
# Données de test, petites et stables : les tests de comportement ne dépendent pas du
# contenu du lexique et du jeu de phrases réels, appelés à évoluer.
LEXICON_PATH = ROOT / "tests" / "data" / "lexique_test.json"
SENTENCES_PATH = ROOT / "tests" / "data" / "phrases_test.csv"

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
    "XAMXAM_ENABLE_DEV_ROUTES",
    "LOG_HASH_KEY",
    "UNLIMITED_NUMBERS",
    "XAMXAM_CACHE_DIR",
    "XAMXAM_STATE_DIR",
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
def repo_lexicon() -> Lexicon:
    return load_lexicon(REPO_LEXICON_PATH)


@pytest.fixture
def index(lexicon: Lexicon) -> LexiconIndex:
    return LexiconIndex(lexicon)


@pytest.fixture
def pipeline(lexicon: Lexicon) -> XamXamPipeline:
    # Le lexique du dépôt ne contient que des brouillons : les tests les appliquent
    # explicitement (en production, seules les prononciations validées le sont).
    return XamXamPipeline(lexicon, applied_statuses=VALIDATED_AND_DRAFT)


@pytest.fixture
def anyio_backend() -> str:
    # Tests asynchrones (plugin anyio, fourni avec Starlette) : boucle asyncio uniquement.
    return "asyncio"
