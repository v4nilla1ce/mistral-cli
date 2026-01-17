"""Base class for all tools."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ToolResult:
    """Result of a tool execution."""

    success: bool
    output: str
    error: Optional[str] = None
    exit_code: Optional[int] = None
    hint: Optional[str] = None

    def to_message(self) -> str:
        """Convert result to a message string for the model."""
        if self.success:
            return self.output

        parts = []
        if self.error:
            parts.append(f"Error: {self.error}")
        if self.output:
            parts.append(self.output)
        if self.hint:
            parts.append(f"Hint: {self.hint}")

        return "\n".join(parts) if parts else "Unknown error"


class Tool(ABC):
    """Abstract base class for all tools.

    Tools provide capabilities that the AI agent can use to interact
    with the system, such as reading files, executing commands, etc.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The unique identifier for this tool."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """A description of what this tool does (for the model)."""
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for the tool's parameters."""
        pass

    @property
    def requires_confirmation(self) -> bool:
        """Whether this tool requires human confirmation before execution.

        Override to return True for tools with side effects.
        """
        return False

    def schema(self) -> dict[str, Any]:
        """Generate Mistral-compatible tool schema.

        Returns:
            Dict with 'type' and 'function' keys matching Mistral's format.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with the given arguments.

        Args:
            **kwargs: Tool-specific arguments.

        Returns:
            ToolResult with success status and output/error.
        """
        pass

    def format_confirmation(self, **kwargs: Any) -> str:
        """Format a human-readable confirmation message.

        Override this for tools that require confirmation to provide
        context-specific confirmation prompts.

        Args:
            **kwargs: Tool-specific arguments.

        Returns:
            A string describing what the tool will do.
        """
        return f"Execute {self.name} with arguments: {kwargs}"
