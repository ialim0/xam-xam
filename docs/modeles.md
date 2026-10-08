# Modèles de langage : Gemini

Le bot utilise l'API Gemini ([Google AI Studio](https://aistudio.google.com/apikey)) à deux
endroits :

- **l'agent tuteur** ([`src/xamxam/agent/`](../src/xamxam/agent/)) : à chaque message, il
  choisit quoi faire grâce à l'appel de fonctions (répondre en texte, résoudre l'exercice,
  envoyer une note vocale, proposer des boutons, lancer une vidéo) ;
- **la résolution** ([`src/xamxam/llm/gemini.py`](../src/xamxam/llm/gemini.py)) : la photo de
  l'exercice est envoyée **directement** au modèle, qui recopie l'énoncé, résout et rédige
  l'explication en wolof au format JSON décrit dans
  [`src/xamxam/llm/schema.py`](../src/xamxam/llm/schema.py). Le calcul est revérifié avec
  SymPy (Pythagore, Thalès) ; en cas d'erreur, le modèle reçoit une seule demande de
  correction. Un résultat qui reste faux n'est jamais transmis à l'agent.

## Configuration

| Variable | Rôle |
| --- | --- |
| `GEMINI_API_KEY` | Clé de [Google AI Studio](https://aistudio.google.com/apikey) (plan gratuit possible). Obligatoire pour le bot. |
| `GEMINI_MODEL` | Modèle principal, `gemini-3.5-flash` par défaut. |
| `GEMINI_FALLBACK_MODEL` | Repli, `gemini-3.6-flash` par défaut. |

## Choix du modèle (essais du 8 octobre 2026, clé gratuite)

| Modèle | Disponible en gratuit | Wolof (explication de Pythagore) |
| --- | --- | --- |
| `gemini-3.5-flash` | oui, 1 à 9 s | **le meilleur** : cohérent, nombres justes en wolof, sans symboles |
| `gemini-3.6-flash` | oui, environ 3 s | non comparé |
| `gemini-3.8-flash` | souvent saturé (503 « high demand ») | non mesuré |
| `gemini-3.5-flash-lite` | oui, environ 1 s | inutilisable : notation LaTeX, mots inventés, calcul faux |
| `gemini-3.1-pro-preview` | non (quota 0) | — |
| Ministral 3 14B (Mistral, pour comparer) | oui | wolof cassé, symboles |

Ces jugements portent sur un seul exemple et sur des critères visibles (nombres, symboles,
cohérence) : la qualité du wolof reste à faire évaluer par des locuteurs natifs.
Google ne publie pas les quotas du plan gratuit dans sa documentation : ils se lisent dans
[AI Studio](https://aistudio.google.com/rate-limit) et se réinitialisent chaque jour à
minuit, heure du Pacifique.

Détails des appels :

- route `POST https://generativelanguage.googleapis.com/v1beta/models/{modèle}:generateContent`,
  clé dans l'en-tête `x-goog-api-key` ;
- image en `inline_data` (base64) : JPEG, PNG, WebP, HEIC ou HEIF ;
- résolution : `responseMimeType: application/json`, schéma JSON rappelé dans le prompt
  système, réponse validée par pydantic, une seule réparation si le JSON est invalide ;
- agent : `tools.functionDeclarations`, au plus 6 étapes par message ; les parties renvoyées
  par Gemini (et leurs `thoughtSignature`) lui sont retransmises telles quelles ;
- robustesse : réessai après 1 s sur 429 et 5xx, passage au modèle de repli si le principal
  ne répond pas (délai dépassé compris), et disjoncteur qui écarte 5 minutes un modèle
  saturé ;
- les erreurs ne recopient jamais la réponse de l'API (qui peut citer l'élève) ni la clé.

**Confidentialité** : la photo et les messages de l'élève sont transmis à Google. Avec une
clé du niveau gratuit, Google peut utiliser ces contenus pour améliorer ses produits ; pour un
usage réel avec des élèves, utilisez une clé d'un projet facturé et relisez les
[conditions de l'API Gemini](https://ai.google.dev/gemini-api/terms).

## Traduction (mode `TRANSLATE_FROM_FRENCH`)

Aucun modèle de traduction n'est choisi. Licences **non commerciales à éviter** :

| Modèle | Licence | Source |
| --- | --- | --- |
| NLLB-200 (ex. `facebook/nllb-200-distilled-600M`) | CC BY-NC 4.0 | [Hugging Face](https://huggingface.co/facebook/nllb-200-distilled-600M) |
| SeamlessM4T v2 (`facebook/seamless-m4t-v2-large`) | CC BY-NC 4.0 | [Hugging Face](https://huggingface.co/facebook/seamless-m4t-v2-large) |

Tout traducteur retenu devra recopier les marqueurs `⟦T1⟧`, `⟦T2⟧`… qui protègent les termes du
lexique : une traduction où un marqueur manque ou est dupliqué est rejetée et journalisée.

## Comparer des modèles Gemini

La commande lit `GEMINI_API_KEY`.

```bash
python -m xamxam.eval llm --photos data/eval/photos --configs data/eval/configurations_llm.example.json
```

- `data/eval/photos/verite_terrain.csv` : `fichier, type_image (imprime|manuscrit), notion,
  type_calcul, donnees (nom=valeur;…), resultat_attendu`.
- `configurations.json` : une entrée par configuration, avec **vos** prix par million de
  jetons (aucun prix n'est codé en dur) :

```json
[
  {"nom": "flash-3.5", "modele": "gemini-3.5-flash",
   "prix_entree_par_million": 0, "prix_sortie_par_million": 0},
  {"nom": "flash-3.6", "modele": "gemini-3.6-flash"}
]
```

Sorties dans `outputs/llm/` : `resultats.csv` (un appel par ligne), `notation_wolof.csv` (à
remplir à la main) et `rapport.md` : JSON valide du premier coup, données extraites, résultat
correct après sympy, stabilité sur les répétitions, latence, coût estimé, et résultat selon
le type d'image.
