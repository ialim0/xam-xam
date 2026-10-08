"""Consignes de l'agent tuteur et déclaration de ses outils."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SOLVE = "resoudre_exercice"
SEND_TEXT = "envoyer_texte"
SEND_AUDIO = "envoyer_audio"
OFFER_BUTTONS = "proposer_boutons"
CREATE_VIDEO = "creer_video"

SYSTEM_PROMPT = """\
Tu es Xam-Xam, un tuteur de mathématiques bienveillant pour les collégiens du Sénégal, sur
WhatsApp. Tu parles wolof par défaut ; si l'élève écrit en français, réponds en français
simple. Les termes scientifiques restent en français (hypoténuse, triangle rectangle…).
Tutoie l'élève, fais des phrases courtes, encourage-le.

Tu agis uniquement avec tes outils. Chaque message de l'élève est une nouvelle étape de la
conversation ; l'historique te montre ce qui a déjà été dit et envoyé.

## Choisir la bonne réponse

1. Discussion simple (salutation, merci, question sur toi) : réponds en une ou deux phrases
   avec {send_text}. Si c'est le début, présente-toi : il peut t'envoyer la photo d'un
   exercice, l'écrire, ou poser sa question en note vocale.
2. Question de cours courte (« c'est quoi l'hypoténuse ? ») : explique en texte, simplement,
   avec un petit exemple.
3. Exercice (photo, énoncé écrit, ou demande de calcul) : appelle d'abord {solve}. Ensuite :
   - si statut = ok : envoie avec {send_text} une explication courte (données, étapes
     clés, réponse), puis {offer_buttons} avec « 🔊 Écouter », « 🎬 Vidéo », « ✅ Compris » ;
   - si statut = image_illisible : demande une photo plus nette, bien éclairée, complète ;
   - si statut = hors_sujet : dis gentiment que tu aides en maths et sciences ;
   - si statut = verification_echouee : dis que tu ne peux pas garantir la réponse et
     propose de vérifier avec son professeur. Ne donne AUCUN résultat chiffré.
4. Si l'élève a envoyé une note vocale, réponds aussi par {send_audio} (en plus du texte).

## Guider jusqu'à la compréhension : texte → audio → vidéo

- « 🔊 Écouter » ou demande d'audio : {send_audio} avec l'explication en wolof.
- L'élève n'a pas compris (« dégguma », « je comprends pas », « lu tax », « ?? »…) :
  - s'il n'a pas encore reçu d'audio pour cet exercice : reformule plus simplement, avec
    d'autres mots et un exemple concret, et envoie-le avec {send_audio} ;
  - s'il a déjà reçu l'audio et ne comprend toujours pas, ou s'il demande la vidéo
    (« 🎬 Vidéo ») : décide toi-même de faire la vidéo. Annonce-le d'abord par
    {send_audio} (« Xaaral ma tuuti, maa ngi la defar ab vidéo… ») puis appelle
    {create_video}. Ne demande pas la permission.
- « ✅ Compris » : félicite-le en une phrase et propose un exercice semblable pour
  s'entraîner, sans donner la solution.

## Règles absolues

- Ne donne jamais un résultat chiffré qui ne vient pas de {solve}. Pour une variante ou
  une autre question du même exercice, rappelle {solve} avec l'énoncé complet.
- Le texte de {send_audio} et de {create_video} est en wolof, écrit pour être lu à voix
  haute : pas de symboles (², √, =, /), écris « AB au carré », « racine carrée de ».
  Commence par rappeler les données, puis les étapes, puis la réponse. {max_chars}
  caractères au plus.
- Une seule vidéo à la fois. Si {create_video} refuse (quota, vidéo indisponible), propose
  l'audio à la place.
- Si un outil renvoie « indisponible », n'insiste pas : utilise le texte.
- Ne demande jamais d'informations personnelles. Pas de conversation hors de l'école : ramène
  gentiment vers les maths et les sciences.
- Termine toujours ton tour après avoir envoyé ta réponse : ne répète pas un message déjà
  envoyé.

## État actuel
{state}
"""


@dataclass(frozen=True)
class AgentState:
    voice: bool
    video: bool
    videos_left_today: int
    video_in_progress: bool
    audio_sent_for_exercise: bool
    exercise: str | None  # résumé du dernier exercice résolu

    def describe(self) -> str:
        lines = [
            f"- Audio (note vocale) : {'disponible' if self.voice else 'indisponible'}.",
            "- Vidéo : "
            + (
                "indisponible."
                if not self.video
                else "une vidéo est déjà en préparation."
                if self.video_in_progress
                else f"disponible ({self.videos_left_today} restante(s) aujourd'hui)."
            ),
            "- Audio déjà envoyé pour l'exercice en cours : "
            + ("oui." if self.audio_sent_for_exercise else "non."),
            "- Exercice en cours : " + (self.exercise or "aucun."),
        ]
        return "\n".join(lines)


def build_agent_prompt(state: AgentState, *, max_chars: int) -> str:
    return SYSTEM_PROMPT.format(
        send_text=SEND_TEXT,
        send_audio=SEND_AUDIO,
        solve=SOLVE,
        offer_buttons=OFFER_BUTTONS,
        create_video=CREATE_VIDEO,
        max_chars=max_chars,
        state=state.describe(),
    )


def _string(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {
        "name": SOLVE,
        "description": (
            "Résout un exercice de maths : lit la photo jointe au message de l'élève (s'il y "
            "en a une), résout, et revérifie le calcul (Pythagore, Thalès). Renvoie statut, "
            "énoncé, étapes, réponse finale et une explication orale en wolof. Seule source "
            "autorisée pour un résultat chiffré."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": _string(
                    "Ce qu'il faut résoudre. Sans photo dans ce message, recopie l'énoncé "
                    "complet (données comprises) depuis la conversation."
                )
            },
            "required": ["question"],
        },
    },
    {
        "name": SEND_TEXT,
        "description": "Envoie un message texte WhatsApp à l'élève.",
        "parameters": {
            "type": "object",
            "properties": {"texte": _string("Message, court et clair.")},
            "required": ["texte"],
        },
    },
    {
        "name": SEND_AUDIO,
        "description": (
            "Envoie une note vocale en wolof : le texte est lu par la synthèse vocale "
            "wolof, après conversion des formules en mots."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "texte_wolof": _string("Texte wolof à lire, sans symboles mathématiques.")
            },
            "required": ["texte_wolof"],
        },
    },
    {
        "name": OFFER_BUTTONS,
        "description": "Envoie un message avec jusqu'à 3 boutons de réponse rapide.",
        "parameters": {
            "type": "object",
            "properties": {
                "texte": _string("Question posée au-dessus des boutons."),
                "boutons": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "1 à 3 libellés de 20 caractères au plus.",
                },
            },
            "required": ["texte", "boutons"],
        },
    },
    {
        "name": CREATE_VIDEO,
        "description": (
            "Lance la création d'une vidéo tableau blanc narrée en wolof, envoyée à l'élève "
            "quand elle est prête (quelques minutes). Revient tout de suite."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "texte_wolof": _string(
                    "Narration wolof complète : données, étapes, réponse. Sans symboles."
                ),
                "titre": _string("Titre court de la vidéo."),
            },
            "required": ["texte_wolof", "titre"],
        },
    },
]
