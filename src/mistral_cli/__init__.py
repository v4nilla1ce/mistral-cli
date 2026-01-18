"""Mistral CLI - A command-line tool for code analysis using Mistral AI."""

__version__ = "0.9.0"
__author__ = "Mistral CLI Contributors"

from .api import MistralAPI
from .context import ConversationContext, build_prompt

__all__ = ["MistralAPI", "ConversationContext", "build_prompt", "__version__"]
