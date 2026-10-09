# Résultats du benchmark de prononciation — 100 phrases

**Instantané : 8 octobre 2026.** Ces résultats décrivent un prototype et un corpus synthétique. Ils sont publiés avec les transcriptions et calculs dans [`results/benchmark-100/`](../results/benchmark-100/). Aucune note d'écoute humaine n'est disponible.

## Question et protocole

Nous cherchons à savoir si la lecture des formules et un lexique phonétique améliorent la restitution de phrases de mathématiques en wolof par une chaîne TTS → STT.

Le corpus contient 100 phrases : 40 sur Pythagore, 40 sur Thalès et 20 situations concrètes. Il est généré par [`tools/phrases_benchmark_100.py`](../tools/phrases_benchmark_100.py) et conservé dans [`data/eval/phrases_pythagore_thales.csv`](../data/eval/phrases_pythagore_thales.csv). La colonne wolof porte le statut **brouillon**. Les 30 termes cibles sont répertoriés dans le [lexique](../data/lexicon/xam_xam_lexique_v0.json), où leurs prononciations sont également **brouillon**.

Pour chacune des 100 phrases, trois textes ont été envoyés au TTS Kiriku puis les audios retranscrits par le STT Kiriku :

1. **Brut** : phrase d'origine, avec les symboles.
2. **Normalisé** : nombres, unités, formules et noms de points rendus en mots.
3. **Lexique** : texte normalisé avec les prononciations brouillon appliquées.

Le troisième bras est **expérimental**. Il ne correspond pas au réglage par défaut du produit, qui n'applique que les entrées validées. Le run compte 300 transcriptions et 0 notation humaine. Les paramètres enregistrés sont dans [`run_info.json`](../results/benchmark-100/run_info.json). La version exacte des modèles TTS/STT et leurs réglages internes n'ont pas été enregistrés.

## Mesures

| Indicateur | Brut | Normalisé | Lexique brouillon |
| --- | ---: | ---: | ---: |
| Termes cibles non retrouvés | 183/236 (77,5 %) | 177/236 (75,0 %) | 186/236 (78,8 %) |
| WER moyen par phrase | 66,8 % | 63,2 % | 70,6 % |
| Éléments de formule retrouvés | non calculé | 216/336 | 180/336 |
| Phrases avec au moins un élément de formule manquant | non calculé | 50/100 | 58/100 |
| Notes humaines | 0 | 0 | 0 |

**Terme non retrouvé** signifie qu'aucune graphie acceptée (terme, alias ou prononciation activée) n'a été trouvée dans la transcription STT pour une occurrence cible. Le dénominateur de 236 est le nombre d'occurrences des termes cibles, identique dans les trois conditions. Ce n'est pas un taux de mots réellement incompris par des élèves.

Le **WER** est la distance d'édition mot à mot entre le texte envoyé au TTS et la transcription STT, divisée par le nombre de mots du texte envoyé, puis moyennée sur les phrases. Il dépend de l'orthographe choisie et des erreurs du STT. Les **éléments de formule** sont les noms de points de deux ou trois lettres, carrés, signes égal, additions et racines attendus dans la source ; le contrôle accepte plusieurs graphies d'un point et l'exposant `²` transcrit par le STT. Les lettres seules sont exclues du contrôle, car trop ambiguës.

### Avec une référence commune aux trois conditions

Le WER ci-dessus compare chaque transcription au texte envoyé **dans sa condition** : la
référence change d'une condition à l'autre, et « douze » transcrit « 12 » compte comme une
erreur. Ce biais pénalise la normalisation. L'[analyse complémentaire](../results/benchmark-100/analyse_complementaire/resume.md)
compare les trois conditions à la même référence, la phrase d'origine
([`tools/analyse_complementaire.py`](../tools/analyse_complementaire.py), sans API) :

| Indicateur | Brut | Normalisé | Lexique brouillon |
| --- | ---: | ---: | ---: |
| Nombres de l'énoncé retrouvés | 62/264 (23,5 %) | 215/264 (81,4 %) | 214/264 (81,1 %) |
| Phrases dont tous les nombres sont retrouvés | 1/61 | 32/61 | 35/61 |
| Éléments de formule retrouvés | 32/336 (9,5 %) | 216/336 (64,3 %) | 180/336 (53,6 %) |

En comparaison appariée, la normalisation améliore le compte de nombres de 52 phrases sur
61, en dégrade 4 (test de signe, p < 10⁻¹⁰). Le lexique brouillon dégrade les éléments de
formule de 30 phrases et en améliore 11 (p ≈ 0,004). La démarche et des exemples commentés
sont dans la [note de recherche](recherche-prononciation.md).

## Où se concentrent les alertes

Dans la condition normalisée, les termes les plus souvent absents sous une graphie acceptée sont :

| Terme | Occurrences non retrouvées |
| --- | ---: |
| hypoténuse | 16/16 |
| angle droit | 11/14 |
| triangle rectangle | 11/13 |
| côté | 10/19 |
| mètres | 9/10 |
| réciproque | 9/9 |
| rapport | 8/11 |
| diagonale | 8/8 |

Le [classement complet](../results/benchmark-100/rapport/classement_termes.csv) et le [diagnostic des 100 phrases](../results/benchmark-100/rapport/diagnostic_phrases.csv) donnent les comptes et les transcriptions. Dans ce dernier, le classement est déterministe : éléments mathématiques non repérés dans la condition normalisée, puis termes non repérés, puis WER décroissant. Il sert à organiser l'écoute, **pas à attribuer une note de qualité audio**.

| Phrase | Signal STT dans la condition normalisée |
| --- | --- |
| `P038` | 6 éléments de formule et 2 termes non repérés ; nombres et opérations fragmentés. |
| `T029` | 6 éléments, surtout les noms de points ou segments, et 2 occurrences de « milieu ». |
| `P017` | 6 éléments ; transcription limitée à « seetal côté e » pour un énoncé plus long. |
| `P037` | 6 éléments, dont quatre noms de points ; les longueurs sont partiellement retranscrites. |
| `T039` | 5 noms de points et deux occurrences de « perpendiculaire » non repérés. |

Le cas `P002` montre la prudence nécessaire : le STT restitue `BC au carré`, `AB au carré` et `AC au carré`, mais manque encore certains marqueurs. Le cas `C020` écrit directement `3² plus 4² égale 5²` ; l'exposant est donc traité comme un carré reconnu. Une variante orthographique ou une erreur STT ne prouve pas que l'audio était incompréhensible.

## Interprétation et limites

La normalisation fait passer le taux de termes non retrouvés de 77,5 % à 75,0 % et le WER moyen de 66,8 % à 63,2 % ; avec une référence commune, son effet est bien plus net : les nombres retrouvés passent de 23,5 % à 81,4 % et les éléments de formule de 9,5 % à 64,3 %. Le lexique brouillon fait ensuite monter ces taux à 78,8 % et 70,6 %. **Nous ne revendiquons pas de gain de prononciation apporté par le lexique dans son état actuel.** Les 32 termes effectivement réécrits dans le run ne sont pas validés ; 30 d'entre eux sont des cibles du benchmark.

Les 100 phrases sont synthétiques et portent sur deux notions mathématiques. Le wolof, les noms de lettres et les prononciations n'ont pas été relus exhaustivement par des locuteurs natifs. Un seul moteur STT a servi de juge automatique, et il peut partager des biais avec le TTS. Le WER et les recherches exactes de termes confondent parfois variation d'écriture et incompréhension. Sans écoute humaine à l'aveugle, ces résultats ne mesurent ni la compréhension d'un élève ni l'efficacité pédagogique. Le bot complet, l'extraction de photos et les modèles de langage ne sont pas évalués par ce benchmark.

## Données, reproduction et suite

Les [fichiers publiés](../results/benchmark-100/README.md) comprennent les textes envoyés, les transcriptions, les comptes par terme, le diagnostic par phrase, les paramètres disponibles et le résumé. Les **300 WAV ne sont pas dans Git** ; l'examen indépendant du signal audio exige une distribution séparée et une vérification des conditions de redistribution du fournisseur. La capture ne permet pas de rejouer à l'identique les modèles externes, dont la version n'est pas figée. Le [protocole](benchmark.md) explique comment recalculer les rapports localement et lancer un nouveau run.

La prochaine étape expérimentale est de faire écouter à l'aveugle les trois versions de chaque phrase, de relire le wolof et les prononciations proposées, puis de refaire le benchmark avec un lexique réellement validé. Les cinq phrases ci-dessus fournissent une première file d'écoute, pas un résultat humain anticipé.
