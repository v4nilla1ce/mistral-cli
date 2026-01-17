"""Tool for updating agent memory."""

from typing import Any, Dict

from ..memory import MemoryManager
from .base import Tool, ToolResult


class UpdateMemoryTool(Tool):
    """Tool to save facts or preferences to memory."""

    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager

    @property
    def name(self) -> str:
        return "update_memory"

    @property
    def description(self) -> str:
        return (
            "Save a fact or user preference to memory. "
            "Use this when the user asks you to remember something or provides a preference (e.g., 'I use pytest'). "
            "Scope can be 'global' (default) or 'project'."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The key to store the value under (e.g., 'preferred_test_runner').",
                },
                "value": {
                    "type": "string",
                    "description": "The value to store (e.g., 'pytest').",
                },
                "scope": {
                    "type": "string",
                    "enum": ["global", "project"],
                    "description": "The scope of the memory. 'global' for user-wide prefs, 'project' for this repo only.",
                    "default": "global",
                },
            },
            "required": ["key", "value"],
        }

    def execute(self, key: str, value: str, scope: str = "global") -> ToolResult:
        try:
            self.memory_manager.set(key, value, scope)
            return ToolResult(True, f"Memory updated: {key} = {value} ({scope})")
        except Exception as e:
            return ToolResult(False, "", f"Failed to update memory: {str(e)}")
