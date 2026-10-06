# Contribuer à Xam-Xam

Merci de votre aide ! La contribution la plus précieuse est **l'ajout ou la correction de
prononciations** dans le lexique.

## Proposer ou corriger une prononciation

1. Ouvrez une *issue* « Prononciation » ou directement une *pull request* vers la branche `staging`.
2. Modifiez `data/lexicon/xam_xam_lexique_v0.json` en respectant le format ci-dessous.
3. Indiquez dans la description :
   - le terme et la prononciation proposée ;
   - si possible un enregistrement audio (note vocale) de la bonne prononciation ;
   - la phrase d'exemple dans laquelle le TTS se trompe.
4. Un **locuteur natif** relit la proposition. Une fois validée, il ajoute son nom (ou pseudonyme)
   dans `validated_by`, passe `statut` à `valide`, et la PR peut être fusionnée.

Pour les termes cibles du benchmark, le plus simple est le fichier
`data/lexicon/termes_cibles_a_valider.csv` : remplir `prononciation_validee` et `validateur`, puis
`python -m xamxam.lexicon import-validation` (voir [docs/benchmark.md](docs/benchmark.md)).

### Format d'une entrée

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
| `statut` | oui | `brouillon` ou `valide`. Seules les prononciations `valide` sont appliquées par défaut (bot et évaluation) ; `valide` exige une prononciation et un validateur. |
| `notion` | non | Notion du programme : `pythagore`, `thales`, `concret`… |
| `aliases` | non | Autres graphies à reconnaître (pluriel, variantes). |
| `validated_by` | non | Locuteur natif qui a validé. **Vide = non validé.** |
| `notes` | non | Contexte, hésitations, variantes régionales. |

Règles vérifiées automatiquement (`pytest`, ou `python -m xamxam.lexicon` pour un rapport lisible) :

- une même graphie (terme ou alias, sans tenir compte de la casse) ne peut apparaître qu'une fois ;
- aucun champ obligatoire vide, aucun champ inconnu ;
- **aucun caractère hors de l'alphabet du TTS** dans les graphies et les prononciations. Le TTS
  ignore silencieusement tout autre caractère (`²`, `√`, chiffres au-delà de 10…). L'alphabet
  wolof contient notamment `ë ñ ó ŋ` ; le pulaar a ses propres lettres (`ɓ ɗ ƴ ŋ`). La liste
  exacte est dans `src/xamxam/tts_alphabet.py`.

Les termes composés n'ont pas besoin d'ordre particulier : « triangle rectangle » est toujours
prioritaire sur « triangle ».

## Ajouter des phrases d'évaluation

`data/eval/phrases_pythagore_thales.csv` contient les colonnes
`id, notion, contexte, fr, wo, termes_cibles`. `notion` vaut `pythagore`, `thales` ou `concret` ;
`termes_cibles` liste les termes à contrôler, séparés par `;`. Les traductions wolof doivent être
relues par un locuteur natif.

## Contribuer au code

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest
```

- Commentaires en français, noms de fonctions et de variables en anglais.
- Tous les tests doivent passer **sans aucune clé** (providers mock).
- Ne commitez jamais de clé ni de fichier `.env`.
- Les PR se font vers `staging`, `main` reçoit les versions stables.

## Licences

En contribuant, vous acceptez que votre code soit publié sous licence MIT, et vos contributions au
lexique et aux jeux de phrases sous licence CC BY-SA 4.0.
