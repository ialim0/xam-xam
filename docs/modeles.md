# Modèles de langage : choix, licences et disponibilité

Xam-Xam n'utilise que des **modèles à poids ouverts**. Ce document recense les modèles de
vision candidats, leur licence et leur disponibilité, avec les sources consultées le
**6 octobre 2026**. Toute information non vérifiée est marquée **« à vérifier »**.

## Politique et liste blanche

- Le bot ne démarre qu'avec un modèle présent dans
  [`src/xamxam/llm/modeles_autorises.json`](../src/xamxam/llm/modeles_autorises.json).
  Le modèle doit accepter les images et, pour Bedrock, être proposé dans `BEDROCK_REGION`.
- Critère actuel de la liste : **licence Apache 2.0** et **entrée image**. Les modèles sous
  licence maison (Gemma 3, Llama, Pixtral, Kimi, Nemotron) sont documentés ci-dessous mais
  **pas autorisés** ; les ajouter est une décision à prendre en revue (PR).
- Pour chaque modèle, le fichier indique : identifiant, provider, licence et lien officiel,
  régions, `supports_vision`, `supports_tool_use`, et la source.
- `supports_tool_use` reflète la carte du modèle sur Bedrock : « appel d'outils côté client »
  listé pour le point d'accès `bedrock-runtime` (celui de l'API Converse). Quand il est vrai,
  Xam-Xam force le JSON par un appel d'outil ; sinon, schéma dans le prompt et une tentative
  de réparation.

## Candidats sur Amazon Bedrock

Source : cartes des modèles Bedrock (liens dans la dernière colonne). Licences : métadonnées
des dépôts officiels sur Hugging Face et textes de licence.

| Modèle | ID Bedrock (`bedrock-runtime`) | Licence | Converse + image | Outils (runtime) | Sorties structurées (runtime) | eu-west-3 Paris | af-south-1 Le Cap | Liste blanche |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Qwen3 VL 235B A22B | `qwen.qwen3-vl-235b-a22b` | [Apache 2.0](https://github.com/QwenLM/Qwen3-VL/blob/main/LICENSE) | oui | non listé | non | non | non | **oui** |
| Mistral Large 3 | `mistral.mistral-large-3-675b-instruct` | [Apache 2.0](https://huggingface.co/mistralai/Mistral-Large-3-675B-Instruct-2512) | oui | non listé | oui | non | non | **oui** |
| Ministral 3 14B (« Ministral 14B 3.0 ») | `mistral.ministral-3-14b-instruct` | [Apache 2.0](https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512) | oui | non listé | oui | non | non | **oui** |
| Ministral 3 8B | `mistral.ministral-3-8b-instruct` | [Apache 2.0](https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512) | oui | non listé | oui | non | non | **oui** |
| Gemma 3 12B IT | `google.gemma-3-12b-it` | [Gemma Terms of Use](https://ai.google.dev/gemma/terms) | oui | non listé | oui | non | non | non (licence) |
| Gemma 3 4B IT | `google.gemma-3-4b-it` | [Gemma Terms of Use](https://ai.google.dev/gemma/terms) | oui | non listé | non listé | non | non | non (licence) |
| Gemma 4 31B | `google.gemma-4-31b` (`bedrock-mantle` seulement) | [Apache 2.0](https://ai.google.dev/gemma/docs/gemma_4_license) | **non** : pas d'API Converse | — | — | non | non | non sur Bedrock (oui en auto-hébergé) |
| Pixtral Large | `mistral.pixtral-large-2502-v1:0`, profil `eu.mistral.pixtral-large-2502-v1:0` | [Mistral Research License](https://mistral.ai/licenses/MRL-0.1.md) | oui | **oui** | non | **oui, profil EU** | non | non (licence) |
| Llama 3.2 11B Instruct | `meta.llama3-2-11b-instruct-v1:0` | [Llama 3.2 Community License](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/LICENSE) | oui | non listé | non | non | non | non (licence) |
| Llama 4 Maverick 17B | `meta.llama4-maverick-17b-instruct-v1:0` | [Llama 4 Community License](https://www.llama.com/llama4/license/) | oui | **oui** | non | non | non | non (licence) |
| Nemotron Nano 12B v2 VL | `nvidia.nemotron-nano-12b-v2` | [NVIDIA Open Model License](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/) | oui | non listé | oui | non | non | non (licence) |
| Kimi K2.5 | `moonshotai.kimi-k2.5` | [MIT modifiée](https://huggingface.co/moonshotai/Kimi-K2.5/blob/main/LICENSE) | oui | non listé | oui | non | non | non (licence) |

Régions « in-region » des modèles de la liste blanche, d'après leurs cartes :

| Modèle | Régions |
| --- | --- |
| Qwen3 VL 235B A22B | us-east-1, us-east-2, us-west-2, eu-south-1, eu-west-1, eu-west-2, ap-northeast-1, ap-south-1, ap-southeast-2, sa-east-1 |
| Mistral Large 3 | us-east-1, us-east-2, us-west-2, ap-northeast-1, ap-south-1, ap-southeast-2, sa-east-1 (**aucune en Europe**) |
| Ministral 3 14B | us-east-1, us-east-2, us-west-2, eu-south-1, eu-west-1, eu-west-2, eu-central-1, eu-north-1, ap-northeast-1, ap-south-1, ap-southeast-2, ap-southeast-3, ap-southeast-4, sa-east-1 |
| Ministral 3 8B | us-east-1, us-east-2, us-west-2, eu-south-1, eu-west-1, eu-west-2, ap-northeast-1, ap-south-1, ap-southeast-2, sa-east-1 |

Modèles listés sur Bedrock mais **dont la carte n'a pas été consultée** : Gemma 4 26B-A4B,
Gemma 4 E2B, Ministral 3B, Llama 3.2 90B, Llama 4 Scout, Kimi K3 — licence, vision et
régions **à vérifier**.

### Ce que cela implique pour Xam-Xam

- **Paris (eu-west-3)** : aucun modèle de la liste blanche n'y est proposé. Le seul modèle de
  vision à poids ouverts appelable depuis Paris est Pixtral Large, via le profil
  d'inférence EU (requêtes routées vers Francfort, Stockholm, Irlande ou Paris), mais sa
  licence de recherche l'exclut.
- **Le Cap (af-south-1)** : aucun des modèles ci-dessus n'y est proposé.
- **Configuration par défaut** : `BEDROCK_REGION=eu-west-1` (Irlande) et
  `BEDROCK_MODEL_ID=mistral.ministral-3-14b-instruct`. Les photos et transcriptions sont
  traitées dans l'UE, hors de Paris.
- **Choix définitif** : après l'évaluation sur photos réelles entre **Qwen3 VL 235B**,
  **Mistral Large 3** et **Ministral 3 14B** (configurations prêtes dans
  [`data/eval/configurations_llm.example.json`](../data/eval/configurations_llm.example.json)).
  Mistral Large 3 n'étant proposé dans aucune région européenne, il est évalué depuis
  `us-east-1` : à garder en tête pour la résidence des données s'il était retenu.
- **Appel d'outils** : aucun modèle de la liste blanche ne le documente sur `bedrock-runtime`
  ; ils passent donc par le prompt et la réparation. Plusieurs documentent en revanche les
  **sorties structurées** (Mistral Large 3, Ministral 3 8B et 14B). **Règle de décision** :
  elles seront implémentées si l'évaluation donne moins de **90 %** de JSON valide du premier
  coup pour le modèle retenu.
- **Accès au modèle** dans le compte AWS (abonnement ou activation éventuels) : **à vérifier**
  dans la console Bedrock avant le déploiement.

## Candidats auto-hébergés

Mêmes familles, servies par vLLM ou Ollama (voir [auto-hebergement.md](auto-hebergement.md)).
L'identifiant est celui du dépôt Hugging Face (nom servi par défaut par vLLM).

| Modèle | Identifiant | Licence | Liste blanche |
| --- | --- | --- | --- |
| Qwen3-VL 8B Instruct | `Qwen/Qwen3-VL-8B-Instruct` | [Apache 2.0](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct) | **oui** |
| Qwen3-VL 32B Instruct | `Qwen/Qwen3-VL-32B-Instruct` | [Apache 2.0](https://huggingface.co/Qwen/Qwen3-VL-32B-Instruct) | **oui** |
| Ministral 3 8B Instruct | `mistralai/Ministral-3-8B-Instruct-2512` | [Apache 2.0](https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512) | **oui** |
| Ministral 3 14B Instruct | `mistralai/Ministral-3-14B-Instruct-2512` | [Apache 2.0](https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512) | **oui** |
| Gemma 4 31B IT | `google/gemma-4-31B-it` | [Apache 2.0](https://ai.google.dev/gemma/docs/gemma_4_license) | **oui** |
| Gemma 3 12B / 27B IT | `google/gemma-3-12b-it`, `google/gemma-3-27b-it` | [Gemma Terms of Use](https://ai.google.dev/gemma/terms) | non (licence) |

## Licences restrictives : ce qu'elles disent

- **Llama 3.2 et Llama 4** : la politique d'usage acceptable de Meta précise que, pour les
  modèles multimodaux, les droits de la licence « ne sont pas accordés » aux personnes
  domiciliées ou aux entreprises ayant leur établissement principal dans l'Union européenne
  (les utilisateurs finaux d'un produit qui les intègre ne sont pas concernés). Sources :
  [USE_POLICY Llama 3.2](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/USE_POLICY.md),
  [USE_POLICY Llama 4](https://github.com/meta-llama/llama-models/blob/main/models/llama4/USE_POLICY.md).
  Les deux licences prévoient aussi des conditions supplémentaires au-delà de 700 millions
  d'utilisateurs actifs mensuels.
- **Pixtral Large (Mistral Research License)** : usage limité aux « fins de recherche »,
  définies comme non commerciales ; sont exclus notamment les tests ou preuves de concept
  destinés à générer un revenu et toute distribution par une entité commerciale, y compris via
  un service hébergé ([texte](https://mistral.ai/licenses/MRL-0.1.md)). Sur Bedrock, ce sont les
  [conditions des modèles tiers d'AWS](https://aws.amazon.com/legal/bedrock/third-party-models/)
  qui s'appliquent : portée exacte **à vérifier** juridiquement.
- **Kimi K2.5 (MIT modifiée)** : au-delà de 100 millions d'utilisateurs actifs mensuels ou de
  20 millions de dollars de revenu mensuel, afficher « Kimi K2.5 » dans l'interface
  ([LICENSE](https://huggingface.co/moonshotai/Kimi-K2.5/blob/main/LICENSE)).
- **Gemma 3 (Gemma Terms of Use)** : conditions propres à Google, accès soumis à acceptation
  sur Hugging Face ; détail des restrictions **à vérifier** dans les
  [conditions](https://ai.google.dev/gemma/terms). Gemma 4, lui, est sous Apache 2.0.
- **NVIDIA Open Model License** : restrictions **à vérifier** dans le
  [texte de la licence](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/).

## Traduction (mode `TRANSLATE_FROM_FRENCH`)

Aucun modèle de traduction n'est choisi. Licences **non commerciales à éviter** :

| Modèle | Licence | Source |
| --- | --- | --- |
| NLLB-200 (ex. `facebook/nllb-200-distilled-600M`) | CC BY-NC 4.0 | [Hugging Face](https://huggingface.co/facebook/nllb-200-distilled-600M) |
| SeamlessM4T v2 (`facebook/seamless-m4t-v2-large`) | CC BY-NC 4.0 | [Hugging Face](https://huggingface.co/facebook/seamless-m4t-v2-large) |

Tout traducteur retenu devra recopier les marqueurs `⟦T1⟧`, `⟦T2⟧`… qui protègent les termes du
lexique : une traduction où un marqueur manque ou est dupliqué est rejetée et journalisée.

## Comparer les modèles

```bash
python -m xamxam.eval llm --photos data/eval/photos --configs configurations.json --repetitions 3
```

- `data/eval/photos/verite_terrain.csv` : `fichier, type_image (imprime|manuscrit), notion,
  type_calcul, donnees (nom=valeur;…), resultat_attendu`.
- `configurations.json` : une entrée par configuration, avec **vos** prix par million de
  jetons (aucun prix n'est codé en dur) :

```json
[
  {"nom": "ministral-14b-irlande", "provider": "bedrock", "modele": "mistral.ministral-3-14b-instruct",
   "region": "eu-west-1", "prix_entree_par_million": 0, "prix_sortie_par_million": 0},
  {"nom": "qwen3-vl-8b-local", "provider": "selfhosted", "modele": "Qwen/Qwen3-VL-8B-Instruct",
   "base_url": "http://localhost:8000/v1"}
]
```

Sorties dans `outputs/llm/` : `resultats.csv` (un appel par ligne), `notation_wolof.csv` (à
remplir à la main) et `rapport.md` : JSON valide du premier coup, données extraites, résultat
correct après sympy, stabilité sur les répétitions, latence, coût estimé, et résultat selon
le type d'image. `--allow-unlisted` permet d'évaluer un candidat absent de la liste blanche.
