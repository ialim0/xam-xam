"""Prompts envoyés au modèle."""

from __future__ import annotations

import json
from collections.abc import Iterable

from xamxam.llm.base import ProblemInput
from xamxam.llm.schema import solution_json_schema

SYSTEM_PROMPT_TEMPLATE = """\
Tu es Xam-Xam, un professeur de mathématiques de collège au Sénégal. Un élève t'envoie
la photo d'un exercice et/ou une question orale en wolof (transcrite automatiquement,
donc parfois imparfaite). Tu réponds uniquement avec un objet JSON conforme au schéma.

Champs :
- statut : « ok » ; « image_illisible » si la photo est floue, coupée ou illisible ;
  « hors_sujet » si ce n'est pas un exercice de mathématiques ou de sciences.
  Si le statut n'est pas « ok », laisse les autres champs textuels vides et calcul.type « aucun ».
- enonce : l'énoncé recopié fidèlement, en français.
- notion : « pythagore », « thales » ou « autre ».
- etapes : la résolution étape par étape, en français, une étape par élément.
- reponse_finale : la réponse finale courte, en français, avec l'unité.
- termes_cles : les termes scientifiques utilisés.
- calcul : le calcul principal, pour qu'il soit revérifié.
  * pythagore_hypotenuse : donnees « cote1 », « cote2 » (côtés de l'angle droit).
  * pythagore_cote : donnees « hypotenuse », « cote » (côté connu de l'angle droit).
  * pythagore_reciproque : donnees « a », « b », « c » (c le plus long) ; resultat « oui » si
    le triangle est rectangle, sinon « non ».
  * thales_longueur : écris l'égalité de rapports sous la forme a/b = c/x, donnees « a »,
    « b », « c » ; resultat = x.
  * thales_reciproque : donnees « a », « b », « c », « d » ; resultat « oui » si a/b = c/d.
  * aucun : pour tout autre exercice.
  Les longueurs sont des nombres dans la même unité. resultat contient seulement la valeur
  trouvée, sous forme exacte et/ou arrondie, par exemple « √52 ≈ 7,21 » ou « 4,5 ».
{explanation_fields}

Consignes pour {explanation_field} :
- Commence toujours par rappeler les données lues dans l'énoncé.
- Explique ensuite la résolution étape par étape, puis donne la réponse finale.
- {language_rule}, phrases courtes, ton encourageant, tutoiement.
- Garde les termes scientifiques en français, écrits exactement comme dans cette liste :
  {lexicon_terms}
- Écris les calculs en clair (« AB au carré »), sans symboles comme ², √ ou =.
- {max_chars} caractères au maximum.
"""

_WOLOF_FIELDS = (
    "- explication_wo : l'explication orale destinée à l'élève, en wolof.\n"
    "- explication_fr : laisse ce champ vide."
)
_FRENCH_FIELDS = (
    "- explication_fr : l'explication orale destinée à l'élève, en français simple ;\n"
    "  elle sera traduite en wolof ensuite.\n"
    "- explication_wo : laisse ce champ vide."
)


def build_system_prompt(
    lexicon_terms: Iterable[str],
    max_chars: int,
    *,
    translate_from_french: bool = False,
    include_schema: bool = False,
) -> str:
    """Prompt système. `include_schema` ajoute le schéma JSON pour les modèles qui ne
    reçoivent pas de contrainte de sortie (ni appel d'outils, ni response_format)."""
    terms = ", ".join(sorted(set(lexicon_terms))) or "(lexique vide)"
    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        lexicon_terms=terms,
        max_chars=max_chars,
        explanation_fields=_FRENCH_FIELDS if translate_from_french else _WOLOF_FIELDS,
        explanation_field="explication_fr" if translate_from_french else "explication_wo",
        language_rule="Français simple" if translate_from_french else "Wolof simple",
    )
    if include_schema:
        schema = json.dumps(solution_json_schema(), ensure_ascii=False)
        prompt += (
            "\nRéponds uniquement avec un objet JSON conforme à ce schéma, sans texte autour :\n"
            + schema
            + "\n"
        )
    return prompt


def build_user_prompt(problem: ProblemInput) -> str:
    """Texte accompagnant l'image éventuelle."""
    parts = []
    if problem.image:
        parts.append("La photo de l'exercice est jointe.")
    if problem.transcript:
        parts.append(f"Question orale de l'élève (transcription) : {problem.transcript}")
    if problem.text:
        parts.append(f"Message écrit de l'élève : {problem.text}")
    if problem.previous is not None and problem.correction:
        parts.append(
            "Ta réponse précédente contient une erreur de calcul. "
            f"{problem.correction} Corrige etapes, reponse_finale, calcul et explication_wo "
            "en conséquence. Réponse précédente :\n"
            + problem.previous.model_dump_json(by_alias=True)
        )
    return "\n\n".join(parts)
