# Faire dire des mathématiques à une voix wolof : démarche et résultats

*Note de recherche du projet Xam-Xam. Toutes les mesures citées se recalculent sans clé API
à partir des fichiers de [`results/benchmark-100/`](../results/benchmark-100/) (voir
[Reproduire](#reproduire)).*

## Résumé

Une voix de synthèse wolof (TTS Kiriku) lit mal un énoncé de mathématiques : elle ignore
les symboles et la plupart des chiffres. Nous avons cherché pourquoi, construit une couche
de prétraitement qui réécrit les formules en mots, puis mesuré l'effet sur 100 phrases avec
un aller-retour TTS → STT (reconnaissance vocale Kiriku). Avec une référence commune aux
trois conditions testées :

| Ce que le STT retrouve dans l'audio | Texte brut | Normalisé | Normalisé + lexique brouillon |
| --- | ---: | ---: | ---: |
| Nombres de l'énoncé | 62/264 (23,5 %) | **215/264 (81,4 %)** | 214/264 (81,1 %) |
| Éléments de formule (points, ², =, +, √) | 32/336 (9,5 %) | **216/336 (64,3 %)** | 180/336 (53,6 %) |

La normalisation multiplie par 3,5 les nombres restitués : sur les 61 phrases qui
contiennent des nombres, elle en améliore 52, en dégrade 4 et en laisse 5 inchangées
(test de signe, p < 10⁻¹⁰). Le lexique de prononciations
**brouillon**, lui, dégrade les formules (30 phrases moins bonnes, 11 meilleures,
p ≈ 0,004) : c'est un résultat négatif que nous publions comme tel, et la raison pour
laquelle le produit n'applique que des prononciations validées par des locuteurs natifs.

Ces chiffres viennent d'un juge automatique (le STT) sur un corpus synthétique : ils
mesurent ce qui « passe » dans l'audio, pas la compréhension d'un élève. Les limites sont
détaillées [plus bas](#limites).

## 1. Le problème : un énoncé de maths devient du bruit

Prenons la phrase P008 du corpus, une étape classique de Pythagore en wolof :

> BC² = 12² + 16² = 144 + 256 = 400, kon BC mooy racine carrée 400, maanaam √400 = 20 cm.

Envoyée telle quelle au TTS, puis réécoutée par le STT, elle devient :

> date 102 ci statakta nuwa saktit da dafa kon bés mooy racine carré ka dafa maanaam ke
> mbaag da sante ndax na sa

Aucun des 8 nombres n'est retrouvé, et un seul des 12 éléments de formule. Les mots
wolof (« kon », « mooy », « maanaam ») passent ; les mathématiques disparaissent.

## 2. Chercher la cause : l'alphabet de la voix

**Hypothèse.** Le TTS ne « rate » pas les symboles par hasard : il ne sait pas les lire.

**Vérification.** Les voix Kiriku sont des modèles Coqui VITS dont la configuration
publique (champs `characters` et `punctuations`) liste les caractères connus. Nous l'avons
recopiée dans [`src/xamxam/tts_alphabet.py`](../src/xamxam/tts_alphabet.py). Tout autre
caractère est **ignoré silencieusement**, et le serveur ne convertit lui-même que les
nombres de 0 à 10. Sur la phrase P008 :

```python
>>> unsupported_characters("BC² = 12² + 16² = 144 + 256 = 400, … √400 = 20 cm.")
['+', '0', '1', '2', '4', '5', '6', '=', '²', '√']
```

**Conséquence.** Le problème n'est pas la prononciation d'un mot difficile mais la
*disparition* de l'information. La solution doit donc intervenir **avant** le TTS : tout
ce que la voix doit dire doit être écrit avec son alphabet.

Cette découverte est devenue une règle vérifiée en continu : aucune entrée du lexique ne
peut contenir un caractère hors de l'alphabet (test automatique et
`python -m xamxam.lexicon`).

## 3. Première solution : écrire les formules en mots

Le normaliseur ([`src/xamxam/normalize/`](../src/xamxam/normalize/)) réécrit, de façon
déterministe :

| Élément | Exemple | Lu comme |
| --- | --- | --- |
| Nombres entiers et décimaux | `144`, `8,6` | « cent quarante-quatre », « huit virgule six » |
| Puissances, racines | `12²`, `√400` | « douze au carré », « racine carrée de quatre cents » |
| Opérateurs et relations | `=`, `+`, `×`, `≈`, `//` | « égale », « plus », « fois », « environ égal à », « parallèle à » |
| Unités | `cm`, `m²`, `km/h` | « centimètres », « mètres carrés », « kilomètres par heure » |
| Fractions | `3/8`, `½` | « trois sur huit », « un demi » |
| Noms de points | `BC`, `MNP` | « bee see », « em en pee » (nom de chaque lettre) |

Sur P008 :

> bee see au carré égale douze au carré plus seize au carré égale cent quarante-quatre
> plus deux cent cinquante-six égale quatre cents, kon bee see mooy racine carrée quatre
> cents, maanaam racine carrée de quatre cents égale vingt centimètres.

Ce que le STT entend désormais :

> dc au carré égal 12 au carré plus 16 au carré égal 144 plus 256 egal 400 kon pc mooy
> racine carré 400 maanaam racine carré de 400 egal 20 centimétre

**8 nombres sur 8** et **10 éléments de formule sur 12** sont retrouvés. Restent des
confusions de lettres (`bee see` entendu « dc » puis « pc ») : la lecture des noms de
points est le point faible suivant.

Deux choix de conception sont à noter :

- **Nombres en français par défaut.** Au Sénégal, les mathématiques s'enseignent en
  français et les élèves disent « cent quarante-quatre ». La lecture en wolof
  (« téeméer ak ñeent fukk ak ñeent ») existe (`XAMXAM_NUMBER_LANGUAGE=wo`) mais n'a pas
  été évaluée ici.
- **Règles et non modèle.** Le normaliseur est un ensemble de règles testées (plus de 300
  tests unitaires dans le projet) : il ne peut pas inventer un nombre, contrairement à un
  modèle de langage qui réécrirait la phrase.

### Un cas extrême : la voix qui boucle

Pour P033 (« AB = 8 cm, BC = 11 cm, AC = 14 cm ; 8² + 11² = 185, 14² = 196 »), le texte
brut produit une transcription qui se répète :

> ko tey yi 8 7a ak faata 8 na lii di rëy refa xa ni rëy rené na xa ni rëy rené na xa ni
> rëy rené na

Après normalisation, les 12 éléments de formule sont retrouvés :

> fa tey ab égale 8 centimètre bc égale 1 centimètre ac égale 14 centimètre 18 o carré
> plus 11 o carré égale 185 14 o carré égale 186

On voit aussi les limites : « onze » entendu « 1 », « cent quatre-vingt-seize » entendu
« 186 ». Restituer la structure ne garantit pas chaque chiffre.

## 4. Mesurer honnêtement : le piège du WER

Le rapport d'origine utilisait le **WER** (taux d'erreur par mot) entre le texte envoyé au
TTS et la transcription. Il donnait un gain modeste à la normalisation (66,8 % → 63,2 %).
En relisant les transcriptions, nous avons constaté que cette mesure était biaisée
**contre** la normalisation :

1. **La référence change d'une condition à l'autre.** En condition brute, la référence
   contient `12` ; en condition normalisée, elle contient `douze`.
2. **Le STT écrit les nombres en chiffres.** Quand la voix dit « douze » et que le STT
   écrit « 12 », le WER compte une erreur, alors que l'information est parfaitement passée.

La phrase T022 le montre :

| Condition | Transcription STT | WER |
| --- | --- | ---: |
| Brut | ci configuration bi distance am tollu na 7 5 cën te distance am tollu na **7 5** cën | 27,8 % |
| Normalisé | ci configuration bi distance a am tollu na 7 5 cm te distance a bett tollu na **12 5** cm | 59,1 % |

La version brute répète la première mesure et perd « 12,5 cm » ; la version normalisée
restitue les deux. Le WER la juge pourtant deux fois pire.

**Correction de méthode.** Nous avons ajouté deux mesures qui utilisent la **même
référence**, la phrase d'origine, pour les trois conditions
([`tools/analyse_complementaire.py`](../tools/analyse_complementaire.py)) :

- **nombres retrouvés** : chaque nombre de l'énoncé est cherché dans la transcription, en
  chiffres ou en toutes lettres ;
- **éléments de formule retrouvés** : le contrôle déjà utilisé par le bot
  (`check_math_audio`), qui accepte `BC`, `B C` ou `bee see` pour un même point et `15²`
  pour « quinze au carré », appliqué cette fois aussi à la condition brute.

Ce sont les chiffres du [résumé](#résumé). Le WER reste publié, avec cette mise en garde.

## 5. Deuxième piste : un lexique de prononciations, et un résultat négatif

**Hypothèse.** Certains termes français (« hypoténuse », « triangle rectangle ») sont mal
dits par une voix entraînée sur du wolof ; les réécrire en orthographe wolof
(« ipoteniws », « tiriyaangal regtaangal ») devrait aider.

**Expérience.** 32 termes ont reçu une proposition de prononciation, au statut
**brouillon** (non validée par des locuteurs natifs), appliquée dans la troisième
condition.

**Résultat.** Les nombres ne bougent pas (81,4 % → 81,1 %), mais les éléments de formule
baissent (64,3 % → 53,6 %), et les termes ciblés ne sont pas mieux reconnus (75,0 % →
78,8 % non retrouvés). Exemple, P008 :

| Condition | Envoyé au TTS | Entendu par le STT |
| --- | --- | --- |
| Normalisé | … kon **bee see** mooy **racine carrée** quatre cents … | … kon pc mooy racine carré 400 … |
| Lexique | … kon **bee see** mooy **rasin kaare** quatre cents … | … kon beissier mooy rarañ carré 400 … |

« racine carrée » était déjà bien restitué ; sa réécriture le dégrade. Deux explications
sont possibles et non départagées : les propositions sont mauvaises, ou le STT (entraîné
sur le même type de données que le TTS) reconnaît mieux l'orthographe française d'origine
que nos graphies. Seule une écoute humaine tranchera.

**Ce que nous en avons fait.** Le lexique reste dans le projet, mais **seules les entrées
au statut `valide`** (validées par un locuteur natif nommé) sont appliquées par défaut,
dans le bot comme dans l'évaluation. Le circuit de validation est outillé
(`python -m xamxam.lexicon export-validation` / `import-validation`, voir
[CONTRIBUTING](../CONTRIBUTING.md)).

## 6. Troisième piste : laisser la machine se réécouter

Dans le bot, une formule peut être générée puis **réécoutée** par le STT avant d'être
envoyée ([`src/xamxam/audio_feedback.py`](../src/xamxam/audio_feedback.py),
`XAMXAM_AUDIO_SELF_CHECK=true`). Si des éléments manquent, une variante ciblée est
synthétisée : « au carré » → « puissance deux », « égale » → « égal à », noms de points
reliés par des tirets (« bee-see »). La variante n'est gardée que si elle fait retrouver
**plus** d'éléments **sans en perdre**, dans la limite de deux essais et de 55 s d'audio.

Ce mécanisme est **désactivé par défaut** (chaque contrôle ajoute au moins un appel STT,
et chaque variante un appel TTS de plus) et **n'a pas encore été mesuré** : l'évaluation
(`python -m xamxam.eval`) ne l'utilise pas, le benchmark publié a donc été produit sans lui. C'est l'une des
prochaines expériences.

## 7. Ce que l'élève reçoit

Ces briques forment la chaîne utilisée par le bot WhatsApp :

```text
explication wolof (agent) → normalisation → lexique validé → TTS Kiriku → [réécoute STT] → note vocale
```

Le calcul lui-même ne vient jamais du modèle de langage seul : la résolution est
revérifiée avec SymPy (Pythagore, Thalès) avant toute explication.

## Limites

- **Juge automatique.** Le STT Kiriku sert de juge ; il peut partager les biais du TTS et
  mal transcrire une voix compréhensible. Aucune écoute humaine n'a encore été faite.
- **Corpus synthétique et non relu.** 100 phrases générées, sur deux notions (Pythagore,
  Thalès) ; le wolof n'a pas été relu exhaustivement par des locuteurs natifs.
- **Un seul run.** Les versions exactes des modèles Kiriku n'ont pas été consignées ; les
  300 WAV ne sont pas redistribués.
- **Comptage des nombres.** La recherche des nombres en toutes lettres peut, rarement,
  compter un mot comme « six » qui ne désignait pas le nombre attendu ; ce biais touche les
  trois conditions de la même façon.
- **Pas de mesure pédagogique.** Rien ici ne mesure ce qu'un élève comprend ou apprend.

## Prochaines étapes

1. Écoute à l'aveugle des trois versions par des locuteurs natifs
   (`python -m xamxam.eval blind`, voir le [protocole](benchmark.md)).
2. Validation du lexique, puis nouveau run avec `--lexique-statut valide`.
3. Mesure de la réécoute STT (section 6) sur les phrases où des points sont mal compris.
4. Meilleure lecture des noms de points, principale source d'erreurs restante.

## Reproduire

Depuis la racine du dépôt, sans clé API :

```bash
pip install -e '.[dev]'
python -m xamxam.eval report --output-dir results/benchmark-100   # rapport d'origine
python tools/analyse_complementaire.py results/benchmark-100       # référence commune
sha256sum -c results/benchmark-100/SHA256SUMS                      # intégrité des données
```

Pour refaire les appels TTS/STT avec vos propres accès Kiriku, suivez
[le protocole](benchmark.md) dans un nouveau dossier de sortie.
