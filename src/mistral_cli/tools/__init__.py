"""Tool system for agentic capabilities."""

from .base import Tool, ToolResult
from .files import EditFileTool, ListFilesTool, ReadFileTool, WriteFileTool
from .project import ProjectContextTool, SearchFilesTool
from .shell import ShellTool

__all__ = [
    "Tool",
    "ToolResult",
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "ListFilesTool",
    "SearchFilesTool",
    "ProjectContextTool",
    "ShellTool",
]


def get_all_tools() -> list[Tool]:
    """Get instances of all available tools."""
    return [
        ReadFileTool(),
        ListFilesTool(),
        SearchFilesTool(),
        ProjectContextTool(),
        WriteFileTool(),
        EditFileTool(),
        ShellTool(),
    ]


def get_safe_tools() -> list[Tool]:
    """Get instances of tools that don't require confirmation."""
    return [t for t in get_all_tools() if not t.requires_confirmation]


def get_tool_schemas(tools: list[Tool]) -> list[dict]:
    """Convert tools to Mistral-compatible schema format."""
    return [t.schema() for t in tools]
