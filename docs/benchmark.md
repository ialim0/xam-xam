# Protocole du benchmark TTS → STT

Ce document décrit comment produire un **nouveau run**. L'instantané déjà obtenu, ses chiffres et ses limites sont dans [résultats du benchmark](resultats-100.md) ; les CSV figés sont dans [`results/benchmark-100/`](../results/benchmark-100/). Ne lancez pas un nouveau run dans ce dossier : utilisez `outputs/`, ignoré par Git.

## Corpus et conditions

[`data/eval/phrases_pythagore_thales.csv`](../data/eval/phrases_pythagore_thales.csv) contient 100 phrases synthétiques : 40 Pythagore, 40 Thalès et 20 situations concrètes. La colonne `wo` est envoyée au TTS ; son statut `brouillon` signifie qu'elle attend une relecture wolof. Les termes suivis figurent dans `termes_cibles`, séparés par `;`. Le [lexique](../data/lexicon/xam_xam_lexique_v0.json) contient les propositions de prononciation et leur statut.

Chaque phrase est traitée trois fois :

| Condition | Texte envoyé au TTS |
| --- | --- |
| `brut` | Colonne `wo` d'origine. |
| `normalise` | Même phrase après lecture des nombres, unités et expressions mathématiques. |
| `lexique` | Texte normalisé avec les prononciations du lexique activées pour le run. |

Pour mesurer les brouillons, il faut passer **explicitement** `--lexique-statut brouillon`. Le réglage par défaut `valide` n'applique que les entrées approuvées. Conservez le même fournisseur, les mêmes textes, la même langue de lecture et le même statut de lexique dans un run. Comparez les conditions d'un même run ; ne mélangez pas des sorties de dates ou de réglages différents.

### Valider le lexique avant un futur run

`python -m xamxam.lexicon export-validation` produit une fiche pour les termes cibles. Un locuteur natif renseigne `prononciation_validee` et `validateur` après écoute ; une proposition sans validation reste `brouillon`. `python -m xamxam.lexicon import-validation` refuse les lignes incomplètes ou les caractères ignorés par le TTS et met à jour le lexique. Pour évaluer seulement ces entrées approuvées, utilisez `--lexique-statut valide` et un nouveau dossier de sortie. Ne modifiez pas rétroactivement l'instantané publié.

## Prérequis

Python 3.11 ou plus récent, dépendances installées avec `pip install -e '.[dev]'`, et accès Kiriku pour obtenir de vrais audios. Copiez [`.env.example`](../.env.example) en `.env`, renseignez `KVICC_TTS_URL`, `KVICC_STT_URL` et `KVICC_API_KEY`, puis chargez le fichier dans votre environnement. Ne le versionnez pas. `--provider kvicc` échoue si le service n'est pas configuré ; `--provider mock` sert uniquement aux tests de code, car son audio silencieux et sa transcription exacte ne mesurent aucune prononciation.

```bash
cp .env.example .env
set -a; source .env; set +a
```

## Produire un run

```bash
python -m xamxam.lexicon
python -m xamxam.eval check
python -m xamxam.eval run --provider kvicc --lexique-statut brouillon \
  --output-dir outputs/nouveau-run
python -m xamxam.eval report --output-dir outputs/nouveau-run
```

`check` contrôle le format et la couverture du corpus sans appeler d'API. `run` produit les 300 WAV, les transcriptions et une fiche d'évaluation humaine vierge ; `report` calcule les tableaux. Pour un premier essai, ajoutez `--limit 5` **dans un autre dossier**. Les caches TTS/STT évitent de répéter des appels identiques ; `--no-cache` force de nouveaux appels. Notez la date, les URLs des services, la version du code, les options, le hash du corpus et du lexique : le fichier `run_info.json` actuel ne capture pas la version interne du service.

Si vous souhaitez préparer l'écoute sans STT :

```bash
python -m xamxam.eval audio --provider kvicc --lexique-statut brouillon \
  --output-dir outputs/ecoute
python -m xamxam.eval blind --output-dir outputs/ecoute
```

La commande `audio` crée aussi `audio/manifest.csv`. Vous pourrez ensuite lancer `run` dans **le même dossier** avec les mêmes options pour obtenir les transcriptions et le rapport ; le cache réutilise les audios correspondants.

## Évaluation humaine à l'aveugle

```bash
python -m xamxam.eval blind --output-dir outputs/nouveau-run
```

Transmettez à chaque évaluateur le contenu de `humain/aveugle/` seulement. La fiche et les audios anonymisés cachent la condition ; `humain/correspondance_aveugle.csv` reste chez l'organisateur. Demandez une note de 1 à 5 pour `note_correction_wolof` et `note_prononciation_termes`, puis les mots problématiques dans `mots_mal_prononces` séparés par `;`. Consignez aussi le nombre de locuteurs, leurs critères et les désaccords avant toute conclusion publique.

Après annotation :

```bash
python -m xamxam.eval unblind --output-dir outputs/nouveau-run
python -m xamxam.eval report --output-dir outputs/nouveau-run
```

`unblind` importe les notes dans `humain/evaluation_humaine.csv`. Les commandes préservent les fiches déjà remplies sauf demande explicite d'écrasement. Une note vide n'est pas une note nulle : le rapport indique le nombre réel d'évaluations.

## Lire les mesures

- `stt/transcriptions.csv` : texte effectivement envoyé, transcription, WER et chemin audio. Le WER compare le texte envoyé au TTS et le STT, après tokenisation ; il reflète aussi les variantes orthographiques et les erreurs du STT.
- `stt/termes.csv` : occurrences ciblées et occurrences absentes de la transcription sous une graphie acceptée. Ce compte n'est pas un jugement humain sur l'intelligibilité.
- `rapport/formules_stt.csv` : points de deux ou trois lettres, carrés, égalités, additions et racines attendus puis repérés ; les lettres seules sont exclues. `BC`, `B C` et `bee see` sont regroupés, et `15²` est accepté pour « quinze au carré ».
- `rapport/diagnostic_phrases.csv` : une ligne par phrase, avec les deux conditions transformées, les alertes, transcriptions et chemins audio. Le tri priorise les formules puis les termes manquants dans la version normalisée. Il sert à organiser l'écoute.
- `rapport/classement_termes.csv` et `rapport/resume.md` : agrégats par terme et par condition, paramètres et nombre de notes humaines.

Le benchmark mesure **la chaîne de prononciation**, pas le bot WhatsApp complet, l'extraction de photos, la justesse des explications ou l'apprentissage des élèves. Une amélioration STT doit être confirmée par l'écoute de locuteurs avant toute revendication de qualité vocale.

## Publier un nouvel instantané

Conservez les entrées, le commit du code, `run_info.json`, `stt/transcriptions.csv`, `stt/termes.csv`, les rapports dérivés et les notes humaines agrégées si leur diffusion est autorisée. Calculez des empreintes SHA-256. Évitez de mettre des WAV volumineux dans Git ; si vous les diffusez séparément, vérifiez au préalable les conditions de redistribution du fournisseur et reliez-les aux identifiants du CSV. Ne publiez aucune clé, aucun média d'élève et aucune fiche contenant des données personnelles.
