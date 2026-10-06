from pathlib import Path

import pytest

from xamxam.lexicon import Lexicon, LexiconIndex, load_lexicon
from xamxam.pipeline import XamXamPipeline

ROOT = Path(__file__).resolve().parents[1]
LEXICON_PATH = ROOT / "data" / "lexicon" / "xam_xam_lexique_v0.json"
SENTENCES_PATH = ROOT / "data" / "eval" / "phrases_pythagore_thales.csv"

_ENV_VARS = (
    "KVICC_TTS_URL",
    "KVICC_STT_URL",
    "KVICC_API_KEY",
    "TIMALENS_API_KEY",
    "WHATSAPP_TOKEN",
)


@pytest.fixture(autouse=True)
def _no_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    # Les tests doivent passer sans aucune clé, même si le poste du développeur en a.
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
