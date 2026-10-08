"""Agent tuteur : boucle d'outils pilotée par Gemini, mémoire courte, consignes."""

from xamxam.agent.loop import AgentRun, Toolbox, run_agent
from xamxam.agent.memory import Conversation, ConversationMemory, history_messages
from xamxam.agent.model import (
    AgentModel,
    GeminiAgentModel,
    ModelTurn,
    ScriptedAgentModel,
    ToolCall,
)
from xamxam.agent.prompt import TOOL_DECLARATIONS, AgentState, build_agent_prompt

__all__ = [
    "TOOL_DECLARATIONS",
    "AgentModel",
    "AgentRun",
    "AgentState",
    "Conversation",
    "ConversationMemory",
    "GeminiAgentModel",
    "ModelTurn",
    "ScriptedAgentModel",
    "ToolCall",
    "Toolbox",
    "build_agent_prompt",
    "history_messages",
    "run_agent",
]
