"""AI agent package for the AI QA automation pipeline.

All pipeline agents (Alice, Bob, Mary, Sarah, Jack) subclass BaseAgent
and follow the same lifecycle: Start → Processing → ReviewRequest → Done.
"""

from ai_qa.agents.alice import AliceAgent
from ai_qa.agents.base import AgentState, BaseAgent
from ai_qa.agents.bob import BobAgent
from ai_qa.agents.mary import MaryAgent
from ai_qa.agents.sarah import SarahAgent

__all__ = ["AgentState", "BaseAgent", "AliceAgent", "BobAgent", "MaryAgent", "SarahAgent"]
