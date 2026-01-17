"""Base class for all tools."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Optional


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

    def to_mcp_schema(self) -> dict[str, Any]:
        """Generate MCP-compatible tool schema.

        Returns:
            Dict matching MCP tool definition format.
        """
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.parameters,
        }


class MCPToolWrapper(Tool):
    """Wrapper for tools from MCP servers.

    This class allows MCP server tools to be used alongside
    built-in tools in the agent.
    """

    def __init__(
        self,
        schema: dict[str, Any],
        executor: Callable[[str, dict], ToolResult],
        server_name: str = "mcp",
    ):
        """Initialize the MCP tool wrapper.

        Args:
            schema: MCP tool definition with name, description, inputSchema.
            executor: Callable that executes the tool (name, args) -> ToolResult.
            server_name: Name of the MCP server (for display).
        """
        self._schema = schema
        self._executor = executor
        self._server_name = server_name

    @property
    def name(self) -> str:
        return self._schema.get("name", "unknown")

    @property
    def description(self) -> str:
        base_desc = self._schema.get("description", "MCP tool")
        return f"[{self._server_name}] {base_desc}"

    @property
    def parameters(self) -> dict[str, Any]:
        return self._schema.get("inputSchema", {"type": "object", "properties": {}})

    @property
    def requires_confirmation(self) -> bool:
        # MCP tools require confirmation by default for safety
        return True

    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the MCP tool.

        Args:
            **kwargs: Tool arguments.

        Returns:
            ToolResult from the MCP server.
        """
        try:
            return self._executor(self.name, kwargs)
        except Exception as e:
            return ToolResult(False, "", f"MCP tool execution failed: {e}")

    def format_confirmation(self, **kwargs: Any) -> str:
        """Format confirmation message for MCP tool."""
        args_str = "\n".join(f"  {k}: {v}" for k, v in kwargs.items())
        return f"Execute MCP tool '{self.name}' from server '{self._server_name}':\n{args_str}"
