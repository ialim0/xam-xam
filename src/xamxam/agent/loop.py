"""Boucle de l'agent : le modèle choisit un outil, lit son résultat, recommence ou s'arrête.

La boucle est bornée (`max_steps`) ; un outil inconnu ou en échec renvoie une erreur au
modèle au lieu d'interrompre la conversation. Si le modèle termine par du texte libre, ce
texte est envoyé à l'élève.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from xamxam.agent.model import AgentModel, tool_message
from xamxam.errors import XamXamError

logger = logging.getLogger(__name__)


class Toolbox(Protocol):
    declarations: list[dict[str, Any]]

    async def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]: ...

    async def say(self, text: str) -> None: ...


@dataclass
class AgentRun:
    steps: int = 0
    tools: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    stopped_by_limit: bool = False


async def run_agent(
    model: AgentModel,
    *,
    system: str,
    messages: list[dict[str, Any]],
    toolbox: Toolbox,
    max_steps: int = 6,
) -> AgentRun:
    run = AgentRun()
    messages = list(messages)
    while run.steps < max_steps:
        run.steps += 1
        turn = await asyncio.to_thread(model.next_turn, system, messages, toolbox.declarations)
        run.input_tokens += turn.input_tokens
        run.output_tokens += turn.output_tokens
        messages.append(turn.message)
        if not turn.calls:
            if turn.text:
                await toolbox.say(turn.text)
            return run
        for tool_call in turn.calls:
            run.tools.append(tool_call.name)
            try:
                result = await toolbox.execute(tool_call.name, tool_call.args)
            except XamXamError as exc:
                # Le message d'erreur ne contient pas de contenu de l'élève.
                logger.warning("Outil %s en échec : %s", tool_call.name, type(exc).__name__)
                result = {"statut": "erreur", "detail": type(exc).__name__}
            messages.append(tool_message(tool_call, result))
    run.stopped_by_limit = True
    logger.warning("Agent arrêté après %d étapes.", max_steps)
    return run
