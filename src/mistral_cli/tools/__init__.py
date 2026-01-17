"""Tool system for agentic capabilities."""

from .base import Tool, ToolResult
from .files import EditFileTool, ListFilesTool, ReadFileTool, WriteFileTool
from .filesystem import FileSystemTool
from .project import ProjectContextTool, SearchFilesTool
from .semantic import SemanticSearchTool
from .shell import ShellTool

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
]


def get_all_tools() -> list[Tool]:
    """Get instances of all available tools."""
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
    ]


def get_safe_tools() -> list[Tool]:
    """Get instances of tools that don't require confirmation."""
    return [t for t in get_all_tools() if not t.requires_confirmation]


def get_tool_schemas(tools: list[Tool]) -> list[dict]:
    """Convert tools to Mistral-compatible schema format."""
    return [t.schema() for t in tools]
