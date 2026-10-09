# Xam-Xam

Xam-Xam prépare des explications de mathématiques en wolof pour la synthèse vocale. Il lit les expressions mathématiques en mots, puis peut remplacer les termes difficiles à prononcer par des graphies adaptées au TTS. Un prototype de bot WhatsApp utilise cette chaîne pour répondre à des exercices envoyés en photo, en texte ou par note vocale.

**État du projet, 8 octobre 2026 :** prototype de recherche. Le corpus de 100 phrases et les prononciations du lexique sont encore des brouillons à faire relire par des locuteurs natifs. Les résultats publiés ci-dessous reposent sur le STT ; aucune évaluation humaine n'a encore été remplie.

## Résultats disponibles

Nous avons testé 100 phrases de Pythagore, Thalès et situations concrètes, dans trois conditions : texte brut, normalisation mathématique, puis normalisation avec lexique **brouillon**. Chaque condition a été synthétisée et retranscrite, soit 300 aller-retours TTS → STT.

| Mesure STT | Brut | Normalisé | Normalisé + lexique brouillon |
| --- | ---: | ---: | ---: |
| Termes cibles non retrouvés, sur 236 occurrences | 77,5 % | 75,0 % | 78,8 % |
| WER moyen par phrase | 66,8 % | 63,2 % | 70,6 % |
| Éléments mathématiques retrouvés, sur 336 attendus | — | 216 | 180 |

La normalisation améliore légèrement ces indicateurs ; les propositions actuelles du lexique les dégradent dans ce run. **Ces chiffres ne démontrent pas une amélioration de la prononciation audible** : le STT peut mal transcrire une voix compréhensible, et les textes wolof n'ont pas été validés. Voir les [résultats et limites](docs/resultats-100.md), les [CSV publiés](results/benchmark-100/) et le [protocole](docs/benchmark.md).

## Fonctionnement

```text
texte ou exercice → lecture des formules → lexique validé → TTS → audio
                                              │
                              évaluation : audio → STT → métriques + écoute humaine
```

En production, seules les entrées du lexique au statut `valide` sont appliquées. Le benchmark publié a activé explicitement le statut `brouillon` pour tester les propositions existantes. Le bot est un agent tuteur conversationnel (Gemini) : il discute, lit la photo de l'exercice, vérifie les calculs Pythagore/Thalès avec SymPy, puis guide l'élève en wolof, du texte vers la note vocale (Kiriku) et jusqu'à une vidéo narrée (TimaLens) s'il ne comprend toujours pas. L'autocontrôle audio peut retranscrire une formule générée et essayer une variante lorsque ses éléments ne sont pas reconnus ; il ne valide pas la qualité linguistique.

## Essayer localement

Python 3.11 ou plus récent est nécessaire, ainsi que `ffmpeg` pour les notes vocales.

```bash
git clone https://github.com/ialim0/xam-xam.git
cd xam-xam
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
python -m xamxam.eval check
python -m xamxam.eval report --output-dir results/benchmark-100
```

La dernière commande recalcule les tableaux publiés **sans clé API** à partir des transcriptions figées. Pour refaire un benchmark audio, suivez [docs/benchmark.md](docs/benchmark.md) et choisissez explicitement `--provider kvicc`. Sans configuration Kiriku, le fournisseur `auto` utilise un mock ; ses résultats ne sont pas des mesures de prononciation.

## Démarrer le bot WhatsApp sur sa machine

Il faut une **clé RodiumAI** et une **application Meta** avec le produit WhatsApp ([démarrage WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started)), qui fournit un numéro de test. Gemini direct reste accepté pour les anciens déploiements.

| Service | Variables | Sans lui |
| --- | --- | --- |
| Meta WhatsApp Cloud | `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET` | le bot ne démarre pas (503) |
| RodiumAI | `RODIUM_API_KEY` | le bot ne démarre pas (503) |
| Kiriku (KVICC) | `KVICC_TTS_URL`, `KVICC_STT_URL`, `KVICC_API_KEY` | réponses en texte ; notes vocales non écoutées |
| TimaLens | `TIMALENS_API_KEY` | pas de vidéo |

1. **Configurer.** Copiez `.env.example` en `.env` et remplissez au moins les variables Meta et `RODIUM_API_KEY`. Le modèle par défaut est `google/gemini-3.8-flash`, avec `google/gemini-3.7-flash` en repli. Dans la console Meta : le jeton d'accès (`WHATSAPP_TOKEN`), l'identifiant du numéro (`WHATSAPP_PHONE_NUMBER_ID`) et la clé secrète de l'application (`WHATSAPP_APP_SECRET`, dans *Paramètres de l'application › Général*). `WHATSAPP_VERIFY_TOKEN` est une chaîne de votre choix.

2. **Lancer le serveur.**

   ```bash
   set -a; source .env; set +a
   uvicorn --factory xamxam.whatsapp.app:create_app --port 8000
   ```

   Vérifiez avec `curl localhost:8000/health` : `bot_ready` doit valoir `true`, `missing_variables` doit être vide ; `voice` et `video` indiquent si Kiriku et TimaLens sont actifs.

3. **Exposer le webhook.** Meta exige une URL publique en HTTPS. Ouvrez un tunnel dans un second terminal, par exemple `cloudflared tunnel --url http://localhost:8000` ou `ngrok http 8000`, et notez l'adresse obtenue.

4. **Brancher Meta.** Dans *WhatsApp › Configuration*, indiquez `https://<adresse-du-tunnel>/webhook` comme URL de rappel et votre `WHATSAPP_VERIFY_TOKEN` comme jeton de vérification, puis abonnez-vous au champ `messages`. Ajoutez votre propre numéro parmi les destinataires autorisés du numéro de test.

5. **Tester.** Écrivez `salut` au numéro de test, puis envoyez la photo d'un exercice de Pythagore ou de Thalès. Le bot affiche « en train d'écrire », répond en quelques secondes au texte, et attend 8 s après une photo ou une note vocale pour les regrouper.

### Comment l'agent répond

Dès qu'un message arrive, l'élève reçoit l'autocollant animé « Néggal tuuti » (patiente un peu) pendant le traitement, suivi, quel que soit le mode, d'une note vocale « Néggal tuuti, maa ngi koy xool » générée une seule fois puis réutilisée (cache TTS sur disque, média gardé chez Meta ; texte modifiable via la clé `waiting_audio` de `XAMXAM_MESSAGES_PATH`). `XAMXAM_WAITING_STICKER=false` retire les deux. Par défaut, l'élève ne reçoit **que des notes vocales en wolof** : salutations, explications, accusés de réception et messages d'erreur. Le texte ne sert qu'en secours, si la synthèse Kiriku échoue. Sans Kiriku, ou avec `XAMXAM_REPLY_MODE=texte`, le bot répond par écrit et propose des boutons (« 🔊 Écouter », « 🎬 Vidéo », « ✅ Compris »).

À chaque message, l'agent choisit lui-même ses outils : résoudre l'exercice (lecture de la photo, vérification SymPy), envoyer une note vocale, lancer une vidéo, et en mode texte écrire ou proposer des boutons.

- Une salutation ou une question de cours reçoit une réponse courte.
- Un exercice reçoit une explication (données, étapes, réponse vérifiée), puis « Dégg nga ? ».
- Si l'élève ne comprend pas (« dégguma »), l'agent reformule autrement, avec un exemple concret ; s'il ne comprend toujours pas, il le prévient et lance seul la vidéo.

Garde-fous en code : un résultat chiffré ne peut venir que de l'outil de résolution vérifié ; au plus 6 étapes par message ; une vidéo à la fois et 5 par jour par élève (`XAMXAM_VIDEOS_PER_DAY`). La conversation est gardée **1 h en mémoire vive** (`XAMXAM_MEMORY_MINUTES`) : rien n'est écrit sur disque, et ni les photos ni les audios des élèves ne sont conservés.

Avec `TIMALENS_API_KEY`, l'agent peut transformer son explication wolof en vidéo tableau blanc au format vertical. Si Kiriku est configuré, la note vocale envoyée à l'élève est transmise à TimaLens et sert de narration : on entend la même voix, et les scènes suivent ses mots. Sans Kiriku, une voix wolof de TimaLens lit le texte. Seul l'audio généré par Xam-Xam est envoyé, jamais la note vocale de l'élève. L'aperçu est gratuit ; le rendu consomme des crédits TimaLens, que `TIMALENS_MAX_CREDITS` permet de plafonner par vidéo. La vidéo arrive quelques minutes après l'explication, sous forme de vidéo WhatsApp, ou de lien si elle dépasse la taille acceptée. Le projet TimaLens (explication, énoncé et réponse) reste dans votre compte TimaLens ; la photo de l'élève ne lui est pas envoyée.

Le `Dockerfile` construit la même application : `docker build -t xamxam . && docker run --env-file .env -p 8000:8080 xamxam`.

Pour la mise en ligne sur AWS (ECS Express Mode, URL HTTPS fournie, secrets dans SSM Parameter Store, sans nom de domaine) : [docs/deploiement-aws.md](docs/deploiement-aws.md).

## Se repérer

| Chemin | Rôle |
| --- | --- |
| [`src/xamxam/normalize/`](src/xamxam/normalize/) | Lecture des nombres, unités, formules et noms de points. |
| [`src/xamxam/lexicon/`](src/xamxam/lexicon/) et [`pronounce/`](src/xamxam/pronounce/) | Validation et application du lexique. |
| [`src/xamxam/providers/`](src/xamxam/providers/) | Interfaces TTS/STT, Kiriku, mock et cache. |
| [`src/xamxam/eval/`](src/xamxam/eval/) | Génération des audios, alignement, métriques et rapports. |
| [`src/xamxam/whatsapp/`](src/xamxam/whatsapp/) | Webhook et orchestration du bot. |
| [`src/xamxam/agent/`](src/xamxam/agent/) | Agent tuteur : boucle d'outils, consignes, mémoire courte. |
| [`src/xamxam/llm/`](src/xamxam/llm/) | Appel à Gemini (photo + question), schéma JSON de la solution. |
| [`src/xamxam/timalens/`](src/xamxam/timalens/) | Vidéo narrée de l'explication (optionnelle). |
| [`deploy/aws/`](deploy/aws/) | Scripts de déploiement AWS : secrets SSM et service ECS Express Mode. |
| [`data/`](data/) | Phrases et lexique source, sous CC BY-SA 4.0. |
| [`results/benchmark-100/`](results/benchmark-100/) | Transcriptions et rapports figés ; les WAV ne sont pas dans Git. |

Le [guide de contribution](CONTRIBUTING.md) décrit la validation des prononciations et des phrases. Le choix et l'évaluation du modèle sont décrits dans [docs/modeles.md](docs/modeles.md). La configuration est documentée dans [`.env.example`](.env.example) ; ne publiez jamais votre fichier `.env`.

## Licences

Code : [MIT](LICENSE). Corpus, lexique et résultats textuels : [CC BY-SA 4.0](data/LICENSE). Les API Kiriku, Meta, Gemini et TimaLens ont leurs propres conditions ; aucun audio généré par ces services n'est distribué ici.

## English summary

Xam-Xam is a Wolof math speech preprocessing prototype with a WhatsApp bot. The bot is a conversational tutor agent built on Gemini function calling: it chats, reads exercise photos, checks Pythagoras/Thales results with SymPy, and escalates from text to Wolof voice notes (Kiriku) to a narrated TimaLens video when the student is stuck. It runs locally with a free Gemini key, a Meta test number and an HTTPS tunnel. Its public 100-sentence benchmark compares raw text, math normalization and a **draft** pronunciation lexicon using TTS → STT. The draft lexicon did not improve the reported STT metrics, and no human listening scores are available yet. See the [results](docs/resultats-100.md) and [reproduction protocol](docs/benchmark.md).
