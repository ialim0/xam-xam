# Rapport d'évaluation Xam-Xam

- Phrases évaluées : 100
- Lignes annotées par des évaluateurs humains : 0
- Conditions : **Texte brut** (`brut`), **Normalisé seul** (`normalise`), **Normalisé + lexique** (`lexique`). Chacune ajoute une couche à la précédente.

## Paramètres du run

- Langue des nombres : **français** (`--number-language fr`)
- Lexique : **prononciations validées et brouillons** (`--lexique-statut brouillon`)
- Termes appliqués avec une prononciation **validée** : 0 occurrence
- Termes appliqués avec une prononciation **brouillon** : 380 occurrence(s), 32 terme(s)
- ⚠️ Des prononciations brouillon ont été appliquées : les résultats de la condition « lexique » ne reflètent pas un lexique validé.

## Taux d'erreur sur les termes cibles

| Source | Texte brut | Normalisé seul | Normalisé + lexique |
| --- | --- | --- | --- |
| STT | 77,5 % | 75,0 % | 78,8 % |
| Humain | n/d | n/d | n/d |
| Combiné | 77,5 % | 75,0 % | 78,8 % |

La source « Combiné » compte une erreur dès que le STT ou un évaluateur la signale.

## Apport de chaque couche (source combinée)

| Couche | Taux avant | Taux après | Gain | Erreurs supprimées |
| --- | --- | --- | --- | --- |
| Normalisation (Texte brut → Normalisé seul) | 77,5 % | 75,0 % | +2,5 pts | 3,3 % |
| Lexique (Normalisé seul → Normalisé + lexique) | 75,0 % | 78,8 % | -3,8 pts | -5,1 % |
| Total Xam-Xam (Texte brut → Normalisé + lexique) | 77,5 % | 78,8 % | -1,3 pts | -1,6 % |

## Éléments mathématiques retrouvés par le STT

| Condition | Éléments reconnus | Éléments attendus | Phrases avec manque |
| --- | --- | --- | --- |
| Normalisé seul | 216 | 336 | 50 |
| Normalisé + lexique | 180 | 336 | 58 |

Les graphies d'un même nom de point (par exemple `BC` et `bee see`) sont regroupées. Un manque signalé par le STT peut aussi venir d'une erreur de reconnaissance.

## WER moyen de l'aller-retour TTS → STT

| Texte brut | Normalisé seul | Normalisé + lexique |
| --- | --- | --- |
| 66,8 % | 63,2 % | 70,6 % |

## Notes humaines moyennes (1 à 5)

| Condition | Lignes | Correction du wolof | Prononciation des termes |
| --- | --- | --- | --- |
| Texte brut | 0 | n/d | n/d |
| Normalisé seul | 0 | n/d | n/d |
| Normalisé + lexique | 0 | n/d | n/d |

## Termes à améliorer en priorité (top 10)

| Rang | Terme | Apparitions | Texte brut | Normalisé seul | Normalisé + lexique | Apport normalisation | Apport lexique |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | hypoténuse | 16 | 100,0 % | 100,0 % | 100,0 % | +0,0 pts | +0,0 pts |
| 2 | angle droit | 14 | 78,6 % | 78,6 % | 100,0 % | +0,0 pts | -21,4 pts |
| 3 | triangle rectangle | 13 | 92,3 % | 84,6 % | 100,0 % | +7,7 pts | -15,4 pts |
| 4 | réciproque | 9 | 100,0 % | 100,0 % | 100,0 % | +0,0 pts | +0,0 pts |
| 5 | alignés | 6 | 83,3 % | 83,3 % | 100,0 % | +0,0 pts | -16,7 pts |
| 6 | segment | 6 | 100,0 % | 100,0 % | 100,0 % | +0,0 pts | +0,0 pts |
| 7 | théorème de Pythagore | 6 | 100,0 % | 100,0 % | 100,0 % | +0,0 pts | +0,0 pts |
| 8 | théorème de Thalès | 6 | 100,0 % | 100,0 % | 100,0 % | +0,0 pts | +0,0 pts |
| 9 | arrondi | 5 | 100,0 % | 80,0 % | 100,0 % | +20,0 pts | -20,0 pts |
| 10 | dixième | 5 | 80,0 % | 100,0 % | 100,0 % | -20,0 pts | +0,0 pts |

Classement complet : `rapport/classement_termes.csv`.
Diagnostic des phrases : `rapport/diagnostic_phrases.csv`, classé par éléments mathématiques puis termes non repérés par le STT dans la version normalisée.
