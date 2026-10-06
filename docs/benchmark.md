# Benchmark de prononciation (TTS) sur 100 phrases

Objectif : mesurer, sur 100 phrases de mathématiques (40 Pythagore, 40 Thalès, 20 situations
concrètes au Sénégal), ce qu'apportent la **normalisation** et le **lexique** à la prononciation
du TTS Kiriku, avec un aller-retour STT et une notation humaine.

- Phrases : [`data/eval/phrases_pythagore_thales.csv`](../data/eval/phrases_pythagore_thales.csv)
  (colonne `wo` envoyée au TTS ; **`statut_wo = brouillon`** : le wolof est à faire relire).
  Elles sont générées depuis [`tools/phrases_benchmark_100.py`](../tools/phrases_benchmark_100.py).
- Lexique : [`data/lexicon/xam_xam_lexique_v0.json`](../data/lexicon/xam_xam_lexique_v0.json),
  30 termes cibles, **tous en brouillon** tant qu'ils ne sont pas validés.
- Trois conditions par phrase : `brut`, `normalise`, `lexique` (voir le README).

## Durée et nombre de requêtes

Le client Kiriku espace les requêtes de 2 s (30 par minute, TTS et STT confondus). Chaque
condition coûte au plus 2 requêtes (1 TTS + 1 STT). Les caches TTS et STT de l'évaluation
évitent de refaire une requête pour un texte ou un audio déjà traité : tant qu'aucun terme n'est
validé, la condition `lexique` produit le même texte que `normalise` et ne coûte rien.

| Étape | Requêtes Kiriku | Durée estimée |
| --- | --- | --- |
| 1. Remplir le CSV de validation | 0 | selon les validateurs (30 termes) |
| 2. Réimporter le CSV | 0 | instantané |
| 3. `check` | 0 | quelques secondes |
| 4. `run --limit 5` | 20 à 30 | environ 1 min |
| 5. Écouter les 15 audios | 0 | 10 min |
| 6. `run` sur les 100 phrases | 380 à 570 (les 5 premières sont en cache) | 13 à 20 min |
| 7. Notation humaine (300 lignes) | 0 | 2 à 3 h (environ 30 s par audio) |
| 8. `report` | 0 | instantané |

L'API du challenge est disponible jusqu'au **16 octobre 2026** : prévoyez les étapes 4 et 6
avant cette date.

## Étapes

### 0. Prérequis

```bash
pip install -e ".[dev]"
cp .env.example .env    # renseigner KVICC_TTS_URL, KVICC_STT_URL, KVICC_API_KEY
set -a; source .env; set +a
```

### 1. Faire valider les prononciations des termes cibles

Ouvrez [`data/lexicon/termes_cibles_a_valider.csv`](../data/lexicon/termes_cibles_a_valider.csv)
(une ligne par terme, triée par nombre d'occurrences). Pour chaque terme, un locuteur natif :

- écoute ou lit la `prononciation_proposee` (proposition **brouillon**) ;
- écrit la prononciation correcte dans `prononciation_validee` (orthographe wolof, minuscules,
  sans chiffres ni symboles : le TTS ignore les caractères hors de son alphabet) ;
- signe dans `validateur` ; une remarque éventuelle va dans `remarques`.

Une ligne sans `prononciation_validee` reste en brouillon. Pour régénérer le fichier après une
modification des phrases : `python -m xamxam.lexicon export-validation`.

### 2. Réimporter les validations

```bash
python -m xamxam.lexicon import-validation
```

Les lignes remplies et signées passent au statut **valide** dans le lexique. L'import est refusé
en bloc si une ligne a une prononciation sans validateur, ou un caractère que le TTS ignorerait.
La commande affiche ensuite le bilan du lexique (validés, brouillons, sans prononciation).

### 3. Contrôler le jeu de phrases

```bash
python -m xamxam.eval check
```

Vérifie 100 lignes et les identifiants P001–P040, T001–T040, C001–C020 ; chaque terme cible
présent dans la colonne `wo` de sa phrase, au moins 4 fois au total et à des positions variées ;
20 mots au plus par phrase ; 512 caractères au plus après normalisation ; au moins 60 phrases
avec nombres supérieurs à 10, décimaux ou notations. Elle affiche, phrase par phrase, les
caractères que le TTS ignorerait en condition brute et après Xam-Xam. Code de sortie 1 en cas
d'erreur.

### 4. Essai sur 5 phrases

```bash
python -m xamxam.eval run --limit 5 --output-dir outputs/essai
```

Options par défaut du benchmark : `--number-language fr` (nombres en lettres françaises) et
`--lexique-statut valide` (seules les prononciations validées sont appliquées). Pour mesurer
aussi les propositions brouillon, relancez avec `--lexique-statut brouillon` dans un autre
dossier de sortie : le rapport signale alors clairement les prononciations non validées.

### 5. Écouter

Les audios sont dans `outputs/essai/audio/` : `{id}_brut.wav`, `{id}_normalise.wav`,
`{id}_lexique.wav`. Vérifiez qu'ils sont audibles, que les nombres sont lus et que rien n'est
coupé avant de lancer les 100 phrases.

### 6. Les 100 phrases

```bash
python -m xamxam.eval run --output-dir outputs/benchmark-100
```

Un `run` interrompu peut être relancé : les audios et transcriptions déjà obtenus viennent du
cache (`.cache/tts`, `.cache/stt`). `--no-cache` force de nouvelles requêtes.

### 7. Notation humaine

Remplissez `outputs/benchmark-100/humain/evaluation_humaine.csv` (300 lignes : 100 phrases ×
3 conditions) : `note_correction_wolof` et `note_prononciation_termes` de 1 à 5, et
`mots_mal_prononces` séparés par `;`. Un nouveau `run` n'écrase jamais une fiche existante.

### 8. Rapport

```bash
python -m xamxam.eval report --output-dir outputs/benchmark-100
```

`outputs/benchmark-100/rapport/resume.md` indique en tête la **langue des nombres** utilisée et
le **nombre de termes appliqués avec une prononciation validée et avec une prononciation
brouillon**, puis l'apport de chaque couche (normalisation, lexique) et les termes à améliorer.

## Remplacer le lexique par le lexique source (307 termes)

Le lexique source (schéma `id`, `terme_fr`, `domaine`, `wolof.prononciation`,
`wolof.valide_par`, `wolof.statut`, `phrases_test`…) se convertit sans perte de champ :

```bash
python -m xamxam.lexicon convert chemin/vers/lexique_source.json data/lexicon/xam_xam_lexique_v0.json
```

- Un terme n'est « valide » que si la source le dit **et** fournit une prononciation et un
  validateur ; sinon il est brouillon (statut d'origine conservé dans `autres`).
- Un terme sans prononciation reste dans le lexique mais n'est jamais appliqué.
- Les 30 termes cibles doivent figurer dans le lexique converti (un test le vérifie) : comparez
  avant d'écraser, puis relancez les étapes 1 à 3.
