"""Prompt templates for AI QA Automation.

This module contains prompt templates used by agents for structured generation tasks.
"""

from ai_qa.prompts.script_generation import (
    SCRIPT_GENERATION_PROMPT,
    SCRIPT_GENERATION_SYSTEM_PROMPT,
)
from ai_qa.prompts.test_extraction import TEST_CASE_EXTRACTION_PROMPT

__all__ = [
    "TEST_CASE_EXTRACTION_PROMPT",
    "SCRIPT_GENERATION_PROMPT",
    "SCRIPT_GENERATION_SYSTEM_PROMPT",
]
