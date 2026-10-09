# Xam-Xam

**Un tuteur de mathématiques en wolof, sur WhatsApp, qui explique à voix haute.**

*Xam-xam* veut dire « savoir » en wolof. L'élève envoie la photo d'un exercice (Pythagore,
Thalès), une question écrite ou une note vocale ; Xam-Xam vérifie le calcul, puis
l'explique en notes vocales wolof, et peut aller jusqu'à une courte vidéo narrée si
l'élève ne comprend toujours pas.

Le cœur du projet est un travail de recherche : **faire lire correctement des
mathématiques à une voix de synthèse wolof**, qui à l'origine ignorait les symboles et
presque tous les chiffres.

> **État : prototype de recherche (octobre 2026).** Les textes wolof et les prononciations
> du lexique attendent la relecture de locuteurs natifs, et aucune écoute humaine n'a encore
> été réalisée. Les résultats ci-dessous viennent d'un juge automatique (reconnaissance
> vocale). Contributions bienvenues, voir [CONTRIBUTING.md](CONTRIBUTING.md).

## Le résultat principal

Sur 100 phrases de mathématiques, synthétisées par la voix wolof Kiriku puis réécoutées par
la reconnaissance vocale Kiriku :

| Ce qui « passe » dans l'audio | Texte brut | Après normalisation Xam-Xam |
| --- | ---: | ---: |
| Nombres de l'énoncé | 23,5 % | **81,4 %** |
| Éléments de formule (points, ², =, +, √) | 9,5 % | **64,3 %** |

Un exemple (phrase P008) :

| | Texte |
| --- | --- |
| Énoncé | BC² = 12² + 16² = 144 + 256 = 400 … √400 = 20 cm |
| Entendu, texte brut | *date 102 ci statakta nuwa saktit da dafa …* |
| Envoyé après normalisation | bee see au carré égale douze au carré plus seize au carré … |
| Entendu, après normalisation | *dc au carré égal 12 au carré plus 16 au carré égal 144 plus 256 egal 400 …* |

Un lexique de prononciations **non validé** a, lui, dégradé les résultats : nous le
publions comme résultat négatif, et le produit n'applique que des prononciations validées.

➡️ **[Lire la note de recherche](docs/recherche-prononciation.md)** : cause du problème,
solutions, exemples commentés, correction d'un biais de mesure et limites.

## Comment ça marche

```text
Élève (WhatsApp)
   │  photo, texte ou note vocale
   ▼
Agent tuteur ── Gemini (ou Rodium) : lit la photo, choisit ses outils
   │   ├─ résolution vérifiée par SymPy (aucun résultat chiffré non vérifié)
   │   ├─ note vocale : normalisation → lexique validé → TTS Kiriku → [réécoute STT]
   │   └─ vidéo narrée TimaLens, si l'élève ne comprend toujours pas
   ▼
Notes vocales wolof (texte en secours)
```

- **Pédagogie.** Explication courte puis « Dégg nga ? » (tu as compris ?). En cas de
  difficulté, l'agent reformule avec un exemple concret, puis propose une vidéo.
- **Garde-fous en code.** Résultat chiffré seulement via l'outil vérifié ; au plus 6 étapes
  par message ; limites par élève (messages par heure, vidéos par jour).
- **Vie privée.** Conversation gardée 1 h en mémoire vive uniquement ; ni photo ni audio
  d'élève conservé ; numéros hachés dans les journaux.

## Essayer en 2 minutes, sans aucune clé

Python 3.11+ et `ffmpeg`.

```bash
git clone https://github.com/ialim0/xam-xam.git
cd xam-xam
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest -q                                                   # 330+ tests, aucun appel réseau
python -m xamxam.eval report --output-dir results/benchmark-100
python tools/analyse_complementaire.py results/benchmark-100
```

Les deux dernières commandes recalculent les résultats publiés à partir des transcriptions
figées.

## Lancer le bot WhatsApp

| Service | Variables | Obligatoire ? |
| --- | --- | --- |
| Meta WhatsApp Cloud API | `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET` | oui |
| Modèle de langage | `GEMINI_API_KEY` ([clé gratuite](https://aistudio.google.com/apikey)), ou `LLM_PROVIDER=rodium` + `RODIUM_API_KEY` | oui (l'un ou l'autre) |
| Voix wolof Kiriku | `KVICC_TTS_URL`, `KVICC_STT_URL`, `KVICC_API_KEY` | non : sans elle, réponses en texte |
| Vidéo TimaLens | `TIMALENS_API_KEY` | non : sans elle, pas de vidéo |

1. **Configurer** : `cp .env.example .env`, puis remplir au moins Meta et la clé du modèle.
   Côté Meta, créez une application avec le produit WhatsApp
   ([guide officiel](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started)) ;
   elle fournit un numéro de test.
2. **Lancer** :
   ```bash
   set -a; source .env; set +a
   uvicorn --factory xamxam.whatsapp.app:create_app --port 8000
   curl localhost:8000/health        # bot_ready: true, missing_variables: []
   ```
3. **Exposer** le webhook en HTTPS, par exemple `cloudflared tunnel --url http://localhost:8000`.
4. **Brancher Meta** : *WhatsApp › Configuration* : URL `https://<tunnel>/webhook`, jeton
   `WHATSAPP_VERIFY_TOKEN`, abonnement au champ `messages`.
5. **Tester** : écrivez « salut » au numéro, puis envoyez la photo d'un exercice.

Toutes les options (mode texte, limites, langue des nombres, réécoute STT…) sont
commentées dans [`.env.example`](.env.example). Image Docker :
`docker build -t xamxam . && docker run --env-file .env -p 8000:8080 xamxam`.
Mise en ligne sur AWS sans nom de domaine : [docs/deploiement-aws.md](docs/deploiement-aws.md).

## Documentation

| Document | Contenu |
| --- | --- |
| [Note de recherche](docs/recherche-prononciation.md) | Démarche, solutions, exemples, résultats et limites. |
| [Résultats du benchmark](docs/resultats-100.md) | Tous les chiffres du run de 100 phrases. |
| [Protocole](docs/benchmark.md) | Refaire un run, écoute humaine à l'aveugle. |
| [Modèles de langage](docs/modeles.md) | Gemini ou Rodium, choix du modèle, confidentialité. |
| [Déploiement AWS](docs/deploiement-aws.md) | ECS Express Mode, secrets dans SSM. |
| [Contribuer](CONTRIBUTING.md) | Prononciations, phrases, code, recherche. |

## Organisation du code

| Chemin | Rôle |
| --- | --- |
| [`src/xamxam/normalize/`](src/xamxam/normalize/) | Lecture des nombres, unités, formules et noms de points. |
| [`src/xamxam/lexicon/`](src/xamxam/lexicon/), [`pronounce/`](src/xamxam/pronounce/) | Lexique de prononciations, validation, application. |
| [`src/xamxam/tts_alphabet.py`](src/xamxam/tts_alphabet.py) | Caractères réellement lus par les voix Kiriku. |
| [`src/xamxam/audio_feedback.py`](src/xamxam/audio_feedback.py) | Réécoute STT des formules et variantes ciblées. |
| [`src/xamxam/providers/`](src/xamxam/providers/) | TTS/STT Kiriku, mock, cache, découpage des longs textes. |
| [`src/xamxam/eval/`](src/xamxam/eval/) | Benchmark : génération, alignement, métriques, rapports, écoute à l'aveugle. |
| [`src/xamxam/agent/`](src/xamxam/agent/), [`llm/`](src/xamxam/llm/) | Agent tuteur, Gemini et Rodium, schéma de solution. |
| [`src/xamxam/verify/`](src/xamxam/verify/) | Vérification SymPy (Pythagore, Thalès). |
| [`src/xamxam/whatsapp/`](src/xamxam/whatsapp/), [`timalens/`](src/xamxam/timalens/) | Webhook WhatsApp, orchestration, vidéo. |
| [`data/`](data/), [`results/`](results/) | Corpus, lexique et résultats publiés (CC BY-SA 4.0). |

## Remerciements

La synthèse et la reconnaissance vocales wolof viennent des modèles **Kiriku**, mis à
disposition par les organisateurs du KVICC. Vidéos : **TimaLens**. Modèles de langage :
**Google Gemini**, ou via **RodiumAI**.

## Licences

Code : [MIT](LICENSE). Corpus, lexique et résultats textuels :
[CC BY-SA 4.0](data/LICENSE). Les API utilisées ont leurs propres conditions ; aucun audio
généré par ces services n'est distribué ici.

## English summary

Xam-Xam is a WhatsApp math tutor that explains exercises in Wolof voice notes. Its core is
research on making a Wolof TTS voice (Kiriku) read mathematics: the voice silently drops
symbols and most digits, so Xam-Xam rewrites formulas, numbers, units and point names into
words before synthesis. On a 100-sentence benchmark judged by Wolof speech recognition, the
share of numbers recovered from the audio rises from 23.5 % to 81.4 %, and formula elements
from 9.5 % to 64.3 %. A draft (unvalidated) pronunciation lexicon made things worse, so only
native-speaker-validated pronunciations are used. Results are machine-judged on a synthetic
corpus; human listening is the next step. The bot runs with a free Gemini key (or optionally
RodiumAI), verifies calculations with SymPy, and keeps no student media. See the
[research note](docs/recherche-prononciation.md) (in French).
