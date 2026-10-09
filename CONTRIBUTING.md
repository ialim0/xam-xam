# Contribuer à Xam-Xam

Merci de votre intérêt ! Xam-Xam avance surtout grâce à des **locuteurs natifs du wolof** :
ce sont eux qui peuvent dire si une voix est compréhensible. Pas besoin de savoir coder
pour aider.

| Vous êtes… | Vous pouvez… | Voir |
| --- | --- | --- |
| Locuteur ou locutrice du wolof | valider une prononciation, relire des phrases, écouter des audios à l'aveugle | [Prononciations](#1-proposer-ou-valider-une-prononciation), [Phrases](#2-relire-ou-ajouter-des-phrases), [Écoute](#3-écouter-à-laveugle) |
| Enseignant·e de mathématiques | proposer des exercices et des formulations d'élèves | [Phrases](#2-relire-ou-ajouter-des-phrases) |
| Chercheur·se | refaire un run, proposer une mesure, critiquer la méthode | [Recherche](#4-contribuer-à-la-recherche) |
| Développeur·se | corriger un bug, ajouter une notion, améliorer la lecture des formules | [Code](#5-contribuer-au-code) |

Pour toute contribution : ouvrez une *issue* pour en discuter, ou directement une *pull
request* vers `main`.

## 1. Proposer ou valider une prononciation

Le lexique ([`data/lexicon/xam_xam_lexique_v0.json`](data/lexicon/xam_xam_lexique_v0.json))
indique au TTS comment écrire un terme pour qu'il soit bien prononcé. **Seules les entrées
validées par un locuteur natif sont utilisées** par le bot : nos mesures ont montré que des
propositions non validées peuvent dégrader la voix (voir la
[note de recherche](docs/recherche-prononciation.md#5-deuxième-piste--un-lexique-de-prononciations-et-un-résultat-négatif)).

**Sans toucher au JSON** (le plus simple) :

```bash
python -m xamxam.lexicon export-validation     # fiche des termes à valider
# remplir prononciation_validee et validateur après écoute
python -m xamxam.lexicon import-validation     # contrôle et mise à jour du lexique
```

**En éditant le JSON**, une entrée ressemble à :

```json
{
  "term": "triangle rectangle",
  "pronunciation": "tiriyaangal regtaangal",
  "notion": "pythagore",
  "aliases": ["triangles rectangles"],
  "statut": "brouillon",
  "validated_by": "",
  "notes": ""
}
```

| Champ | Obligatoire | Description |
| --- | --- | --- |
| `term` | oui | Graphie du terme telle qu'elle apparaît dans les textes. |
| `pronunciation` | non | Réécriture à envoyer au TTS, en orthographe wolof. Sans prononciation, le terme n'est jamais réécrit. |
| `statut` | oui | `brouillon` ou `valide`. `valide` exige une prononciation et un validateur. |
| `notion` | non | Notion du programme : `pythagore`, `thales`, `concret`… |
| `aliases` | non | Autres graphies à reconnaître (pluriel, variantes). |
| `validated_by` | non | Nom ou pseudonyme du locuteur natif, choisi avec son accord. **Vide = non validé.** |
| `notes` | non | Contexte, hésitations, variantes régionales. |

Dans la description de la PR, indiquez la phrase où le TTS se trompe et, si possible, joignez
une note vocale de la bonne prononciation. Laissez `brouillon` tant qu'un locuteur natif n'a
pas réellement écouté le résultat.

Règles vérifiées automatiquement (`pytest`, ou `python -m xamxam.lexicon` pour un rapport
lisible) :

- une graphie (terme ou alias, sans tenir compte de la casse) n'apparaît qu'une fois ;
- aucun champ obligatoire vide, aucun champ inconnu ;
- **aucun caractère hors de l'alphabet du TTS** : la voix ignore silencieusement les autres
  (`²`, `√`, chiffres…). L'alphabet wolof contient notamment `ë ñ ó ŋ` ; la liste exacte est
  dans [`src/xamxam/tts_alphabet.py`](src/xamxam/tts_alphabet.py).

Les termes composés sont prioritaires : « triangle rectangle » passe avant « triangle ».

## 2. Relire ou ajouter des phrases

[`data/eval/phrases_pythagore_thales.csv`](data/eval/phrases_pythagore_thales.csv) contient
les colonnes `id, notion, contexte, fr, wo, termes_cibles`. `notion` vaut `pythagore`,
`thales` ou `concret` ; `termes_cibles` liste les termes à contrôler, séparés par `;`.

- **Relecture** : corrigez la colonne `wo` et dites-le dans la PR ; c'est aujourd'hui la
  contribution la plus utile.
- **Ajout** : de nouvelles notions (aires, fractions, équations) sont bienvenues ; vérifiez
  avec `python -m xamxam.eval check`.

Ne modifiez pas l'instantané publié dans `results/benchmark-100/` : il correspond au corpus
d'origine. Les nouveaux runs vont dans un nouveau dossier.

## 3. Écouter à l'aveugle

C'est l'étape qui manque le plus au projet. Un organisateur prépare des audios anonymisés
(`python -m xamxam.eval blind`, voir le [protocole](docs/benchmark.md#évaluation-humaine-à-laveugle)) ;
vous notez de 1 à 5 la correction du wolof et la prononciation des termes, sans savoir quelle
version vous écoutez. Signalez-vous dans une *issue* « Écoute ».

## 4. Contribuer à la recherche

- **Reproduire** : `python -m xamxam.eval report --output-dir results/benchmark-100` et
  `python tools/analyse_complementaire.py results/benchmark-100` recalculent tout sans API.
- **Nouveau run** : suivez le [protocole](docs/benchmark.md) avec vos accès Kiriku, dans un
  dossier `outputs/…`, et publiez les CSV, `run_info.json` et les empreintes.
- **Méthode** : une mesure biaisée, un test manquant, une interprétation trop forte ?
  Ouvrez une *issue* : la [note de recherche](docs/recherche-prononciation.md) liste déjà
  ses limites et sera corrigée.

Règle commune : un chiffre publié doit pouvoir être recalculé à partir des fichiers du dépôt,
et une amélioration mesurée par le STT n'est pas une preuve de compréhension humaine.

## 5. Contribuer au code

```bash
git clone https://github.com/ialim0/xam-xam.git && cd xam-xam
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
ruff check . && ruff format --check .
pytest
```

- Tous les tests passent **sans aucune clé ni réseau** (fournisseurs simulés). Un test qui
  appellerait une vraie API sera refusé.
- Commentaires et documentation en français ; noms de fonctions et de variables en anglais.
- Toute nouvelle variable d'environnement : dans `Settings` ou `BotSettings`, dans
  [`.env.example`](.env.example) avec un commentaire, et dans `tests/conftest.py` (un test
  le vérifie).
- Un bug de lecture de formule se corrige avec un test dans `tests/test_normalize.py` qui
  montre l'entrée et le texte attendu.
- Les PR ciblent `main` et doivent passer la CI (Ruff et tests).

Repères dans le code : voir l'[organisation du code](README.md#organisation-du-code).

## Ce qu'il ne faut jamais committer

- Une clé, un jeton ou un fichier `.env` (Meta, Gemini, Rodium, Kiriku, TimaLens, AWS).
- Une photo, une note vocale ou un numéro d'élève, même anonymisé à la main.
- Un enregistrement de tiers sans droit de redistribution, ou les WAV générés par Kiriku.

Si vous trouvez une faille de sécurité ou une donnée personnelle dans le dépôt, ne l'exposez
pas dans une *issue* publique : utilisez le signalement privé de GitHub
(*Security › Report a vulnerability*).

## Bienveillance

Le projet réunit des personnes de langues, de niveaux et de disciplines différents. Les
remarques portent sur le travail, jamais sur les personnes. Les variantes régionales du
wolof sont toutes légitimes : documentez-les dans `notes` plutôt que de les corriger.

## Licences

En contribuant, vous acceptez que votre code soit publié sous licence MIT, et vos
contributions au lexique, aux phrases et aux résultats textuels sous licence CC BY-SA 4.0.
