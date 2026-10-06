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
python -m xamxam.eval run       # audios avant/après, aller-retour STT, fiche d'évaluation humaine
python -m xamxam.eval report    # classement des termes et résumé Markdown
```

Les résultats sont écrits dans `outputs/` (ignoré par Git) :

| Fichier | Contenu |
| --- | --- |
| `outputs/audio/{id}_avant.wav`, `{id}_apres.wav` | audio du texte brut et du texte passé par Xam-Xam |
| `outputs/stt/transcriptions.csv` | transcription STT et WER de chaque audio |
| `outputs/stt/termes.csv` | apparitions et erreurs de chaque terme cible |
| `outputs/humain/evaluation_humaine.csv` | fiche à remplir (notes 1 à 5, mots mal prononcés) |
| `outputs/rapport/classement_termes.csv` | taux d'erreur par terme, avant et après |
| `outputs/rapport/resume.md` | taux global d'amélioration, notes moyennes, termes prioritaires |

`run` n'écrase jamais une fiche humaine déjà remplie (option `--overwrite-human` pour forcer).

### Configuration

Copiez `.env.example` en `.env` et renseignez les clés dont vous disposez, puis chargez-les
(`set -a; source .env; set +a`). **Toutes les variables sont optionnelles** :

- sans `KVICC_*`, le TTS et le STT **mock** sont utilisés (audio silencieux, aller-retour exact) ;
- sans `TIMALENS_API_KEY`, la génération vidéo est désactivée et un message l'indique ;
- sans `WHATSAPP_TOKEN`, le webhook répond 503.

> ⚠️ L'intégration de l'API KVICC (`src/xamxam/providers/kvicc.py`) et celle de TimaLens
> (`src/xamxam/timalens/client.py`) sont des squelettes : leurs endpoints restent à renseigner à
> partir de la documentation officielle.

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
├── providers/   interfaces TTSProvider / STTProvider, mock, squelette KVICC
├── timalens/    client vidéo optionnel (désactivé sans clé)
├── whatsapp/    webhook FastAPI (squelette)
└── eval/        évaluation avant/après : run, alignement, fiche humaine, métriques, rapport
```

```
texte ──► normalize ──► pronounce (lexique) ──► TTS ──► audio
                                                 │
                         eval : STT ◄────────────┘ ──► alignement ──► métriques ──► rapport
```

Les tables de lecture des expressions mathématiques existent pour l'instant **en français**
seulement. Les lectures en wolof, pulaar et sérère seront ajoutées avec des locuteurs natifs.

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

Every key is optional: without them, mock providers are used and video is disabled. Code is MIT;
lexicon and datasets are CC BY-SA 4.0. Contributions to the lexicon are welcome, see
[CONTRIBUTING.md](CONTRIBUTING.md).
