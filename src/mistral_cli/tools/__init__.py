"""Tool system for agentic capabilities."""

from .base import Tool, ToolResult
from .files import EditFileTool, ListFilesTool, ReadFileTool, WriteFileTool
from .filesystem import FileSystemTool
from .project import ProjectContextTool, SearchFilesTool
from .semantic import SemanticSearchTool
from .shell import ShellTool
from .critic import CriticTool

__all__ = [
    "Tool",
    "ToolResult",
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "ListFilesTool",
    "FileSystemTool",
    "SearchFilesTool",
    "SemanticSearchTool",
    "ProjectContextTool",
    "ShellTool",
    "CriticTool",
]


def get_all_tools() -> list[Tool]:
    """Get instances of all available tools."""
    # Note: Some tools like CriticTool need dependencies (Critic) passed in.
    # get_all_tools currently instantiates them with defaults or fails if dep needed?
    # Actually, initializing `CriticTool` here requires a `Critic` instance.
    # The `Agent` initializes `CriticTool` manually.
    # So we might NOT want to include it in `get_all_tools` if it requires deps not available here.
    # But `Agent` calls `get_all_tools()` as default.
    # Check if `CriticTool` can have a default `Critic`.
    # Let's import logic inside.
    from ..critic import Critic
    return [
        ReadFileTool(),
        ListFilesTool(),
        FileSystemTool(),
        SearchFilesTool(),
        SemanticSearchTool(),
        ProjectContextTool(),
        WriteFileTool(),
        EditFileTool(),
        ShellTool(),
        CriticTool(Critic()),
    ]


def get_safe_tools() -> list[Tool]:
    """Get instances of tools that don't require confirmation."""
    return [t for t in get_all_tools() if not t.requires_confirmation]


def get_tool_schemas(tools: list[Tool]) -> list[dict]:
    """Convert tools to Mistral-compatible schema format."""
    return [t.schema() for t in tools]
