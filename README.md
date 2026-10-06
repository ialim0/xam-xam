# Xam-Xam

> Narration scientifique pour les langues nationales du Sénégal : wolof d'abord, puis pulaar et sérère.
> Projet présenté au **KVICC 2026** (Kiriku Voice Inclusive & Creative Challenge).

*[English version below](#english-summary)*

## Le problème

Les moteurs de synthèse vocale (TTS) en wolof lisent mal les termes de mathématiques et de
sciences : « hypoténuse », « théorème de Pythagore », `AB²` ou `√25` sont souvent prononcés à
l'anglaise, ou pas prononcés du tout. Une explication orale devient alors incompréhensible pour
l'élève.

## La solution

Xam-Xam est une brique qui se place **avant** le TTS. Elle :

1. **normalise** les expressions mathématiques en mots (`BC = 5 cm` → « B C égale cinq centimètres ») ;
2. **réécrit** les termes scientifiques à partir d'un **lexique de prononciations validées par
   des locuteurs natifs** ;
3. **mesure** l'amélioration par un aller-retour TTS → STT et par une évaluation humaine.

Le premier produit construit dessus est un **bot WhatsApp** : l'élève envoie la photo d'un
exercice et reçoit une explication vocale en wolof.

La génération vidéo utilise l'API TimaLens, service propriétaire. Clé gratuite pour les participants du KVICC sur demande.

## Démarrage rapide

Prérequis : Python 3.11 ou plus récent.

```bash
git clone https://github.com/ialim0/xam-xam.git
cd xam-xam
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest                          # tous les tests passent sans aucune clé (provider mock)
python -m xamxam.lexicon        # valide le lexique et signale les caractères ignorés par le TTS
python -m xamxam.eval run       # audios des 3 conditions, aller-retour STT, fiche d'évaluation humaine
python -m xamxam.eval report    # classement des termes et résumé Markdown
```

### Évaluation en trois conditions

Chaque phrase est synthétisée trois fois, chaque condition ajoutant une couche à la précédente :

| Condition | Texte envoyé au TTS |
| --- | --- |
| `brut` | phrase d'origine, symboles compris (`AB² = 25 cm`) |
| `normalise` | normalisation mathématique seule (« A B au carré égale vingt-cinq centimètres ») |
| `lexique` | normalisation puis réécriture des termes par le lexique |

Le rapport sépare ainsi l'**apport de la normalisation** (`brut` → `normalise`) de l'**apport du
lexique** (`normalise` → `lexique`), globalement et pour chaque terme. Les résultats sont écrits
dans `outputs/` (ignoré par Git) :

| Fichier | Contenu |
| --- | --- |
| `outputs/audio/{id}_{condition}.wav` | audio de chaque condition |
| `outputs/stt/transcriptions.csv` | transcription STT et WER de chaque audio |
| `outputs/stt/termes.csv` | apparitions et erreurs de chaque terme cible |
| `outputs/humain/evaluation_humaine.csv` | fiche à remplir (notes 1 à 5, mots mal prononcés) |
| `outputs/rapport/classement_termes.csv` | taux d'erreur par terme et par condition, apport de chaque couche |
| `outputs/rapport/resume.md` | taux par condition, apport des couches, notes moyennes, termes prioritaires |

`run` n'écrase jamais une fiche humaine déjà remplie (option `--overwrite-human` pour forcer).

Options utiles de `run` :

- `--number-language fr|wo` : nombres écrits en lettres françaises (« vingt-cinq ») ou wolof
  (« ñaar fukk ak juróom »). Le TTS ne lit lui-même que 0 à 10 : sans cette étape, les autres
  nombres sont perdus. La numération wolof suit l'orthographe officielle et reste **à faire
  valider** par des locuteurs natifs (variantes comme « fanweer » pour 30).
- `--cache-dir` (défaut `.cache/tts/`) et `--no-cache` : chaque audio est mis en cache sous
  l'empreinte SHA-256 de (fournisseur et réglages, langue, texte exact). Un audio déjà produit
  n'est jamais régénéré, ce qui ménage le quota de l'API.

### Configuration

Copiez `.env.example` en `.env` et renseignez les clés dont vous disposez, puis chargez-les
(`set -a; source .env; set +a`). **Toutes les variables sont optionnelles** :

- avec `KVICC_*`, Xam-Xam utilise l'API Kiriku du challenge (TTS wolof et pulaar, STT wolof,
  pulaar et sérère) ;
- sans `KVICC_*`, le TTS et le STT **mock** sont utilisés (audio silencieux, aller-retour exact) ;
- sans `TIMALENS_API_KEY`, la génération vidéo est désactivée et un message l'indique ;
- sans `WHATSAPP_TOKEN`, le webhook répond 503.

Le client KVICC respecte les limites de l'API : il espace les requêtes (30 par minute et par clé,
TTS et STT confondus), réessaie après un `429` ou un `503` en suivant `Retry-After`, et découpe par
phrase les textes de plus de 512 caractères. Une évaluation de 100 phrases demande 400 requêtes,
soit environ 14 minutes.

> ⚠️ L'intégration TimaLens (`src/xamxam/timalens/client.py`) est encore un squelette : ses
> endpoints restent à renseigner à partir de la documentation officielle.

### Serveur de développement

```bash
uvicorn --factory xamxam.whatsapp.app:create_app --reload
curl -X POST localhost:8000/dev/speak -H 'Content-Type: application/json' \
     -d '{"text": "AB² = 9 cm²"}' -o test.wav
```

## Architecture

```
src/xamxam/
├── lexicon/     schéma pydantic, chargement, recherche (termes composés prioritaires)
├── normalize/   expressions mathématiques → mots, tables de lecture par langue
├── pronounce/   substitution des termes par leur prononciation validée
├── pipeline.py  normalisation puis réécriture : le texte prêt pour le TTS
├── providers/   interfaces TTSProvider / STTProvider, mock, API Kiriku du KVICC, cache audio
├── tts_alphabet.py  caractères acceptés par les voix TTS (wolof, pulaar)
├── timalens/    client vidéo optionnel (désactivé sans clé)
├── whatsapp/    webhook FastAPI (squelette)
└── eval/        évaluation avant/après : run, alignement, fiche humaine, métriques, rapport
```

```
texte ──► normalize ──► pronounce (lexique) ──► TTS (cache) ──► audio
                                                 │
                         eval : STT ◄────────────┘ ──► alignement ──► métriques ──► rapport
```

Les tables de lecture des expressions mathématiques (« au carré », « racine carrée de »…) existent
pour l'instant **en français** seulement ; les nombres peuvent être lus en français ou en wolof.
Les lectures en wolof, pulaar et sérère seront complétées avec des locuteurs natifs.

## Contribuer au lexique

Le lexique (`data/lexicon/`) est le cœur du projet. Chaque prononciation doit être **validée par
un locuteur natif** avant d'être fusionnée. Voir [CONTRIBUTING.md](CONTRIBUTING.md) pour le
format et la procédure.

> Le fichier fourni dans `data/lexicon/` et les 5 phrases de `data/eval/` sont des **exemples non
> validés**, en attendant le lexique v0 et le jeu complet de 100 phrases.

## Licences

- Code : [MIT](LICENSE).
- Lexique et jeux de phrases (`data/`) : [CC BY-SA 4.0](data/LICENSE).

---

## English summary

**Xam-Xam** is a scientific narration layer for Senegal's national languages (Wolof first, then
Pulaar and Serer), built for the KVICC 2026 challenge. Current TTS engines often read math and
science terms as if they were English. Xam-Xam sits *before* the TTS: it turns math expressions
into words, rewrites scientific terms using a lexicon of pronunciations validated by native
speakers, and measures the gain with a TTS → STT round trip plus human ratings.

The first product built on it is a WhatsApp bot: a student sends a photo of an exercise and gets
a spoken explanation in Wolof.

Video generation uses the TimaLens API, a proprietary service. Free key for KVICC participants on request.

```bash
pip install -e ".[dev]"
pytest
python -m xamxam.eval run && python -m xamxam.eval report
```

The evaluation compares three conditions (raw text, math normalization only, normalization +
lexicon) so the report isolates the contribution of each layer. TTS audio is cached by text hash.

Every key is optional: without them, mock providers are used and video is disabled. Code is MIT;
lexicon and datasets are CC BY-SA 4.0. Contributions to the lexicon are welcome, see
[CONTRIBUTING.md](CONTRIBUTING.md).
