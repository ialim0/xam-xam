# Xam-Xam

Xam-Xam prépare des explications de mathématiques en wolof pour la synthèse vocale. Il lit les expressions mathématiques en mots, puis peut remplacer les termes difficiles à prononcer par des graphies adaptées au TTS. Un prototype de bot WhatsApp utilise cette chaîne pour répondre à des questions scolaires par la voix.

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

En production, seules les entrées du lexique au statut `valide` sont appliquées. Le benchmark publié a activé explicitement le statut `brouillon` pour tester les propositions existantes. Le bot ajoute une extraction de l'énoncé, un modèle de langage, une vérification des calculs Pythagore/Thalès avec SymPy et une réponse vocale. L'autocontrôle audio peut retranscrire une formule générée et essayer une variante lorsque ses éléments ne sont pas reconnus ; il ne valide pas la qualité linguistique.

## Essayer localement

Python 3.11 ou plus récent et `ffmpeg` sont nécessaires pour les fonctions audio du bot.

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

## Se repérer

| Chemin | Rôle |
| --- | --- |
| [`src/xamxam/normalize/`](src/xamxam/normalize/) | Lecture des nombres, unités, formules et noms de points. |
| [`src/xamxam/lexicon/`](src/xamxam/lexicon/) et [`pronounce/`](src/xamxam/pronounce/) | Validation et application du lexique. |
| [`src/xamxam/providers/`](src/xamxam/providers/) | Interfaces TTS/STT, Kiriku, mock et cache. |
| [`src/xamxam/eval/`](src/xamxam/eval/) | Génération des audios, alignement, métriques et rapports. |
| [`src/xamxam/whatsapp/`](src/xamxam/whatsapp/) | Webhook et orchestration du bot. |
| [`data/`](data/) | Phrases et lexique source, sous CC BY-SA 4.0. |
| [`results/benchmark-100/`](results/benchmark-100/) | Transcriptions et rapports figés ; les WAV ne sont pas dans Git. |

Le [guide de contribution](CONTRIBUTING.md) décrit la validation des prononciations et des phrases. Pour le bot : [configuration des modèles](docs/modeles.md), [auto-hébergement](docs/auto-hebergement.md), [déploiement AWS](docs/deploiement-aws.md) et [alternative GCP](docs/deploiement-gcp.md). La configuration est documentée dans [`.env.example`](.env.example) ; ne publiez jamais votre fichier `.env`.

## Licences

Code : [MIT](LICENSE). Corpus, lexique et résultats textuels : [CC BY-SA 4.0](data/LICENSE). Les API Kiriku, Meta, Bedrock et l'éventuel service vidéo ont leurs propres conditions ; aucun audio généré par ces services n'est distribué ici.

## English summary

Xam-Xam is a Wolof math speech preprocessing prototype with a WhatsApp bot. Its public 100-sentence benchmark compares raw text, math normalization and a **draft** pronunciation lexicon using TTS → STT. The draft lexicon did not improve the reported STT metrics, and no human listening scores are available yet. See the [results](docs/resultats-100.md) and [reproduction protocol](docs/benchmark.md).
