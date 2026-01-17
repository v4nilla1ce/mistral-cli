"""File operation tools."""

import fnmatch
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class ReadFileTool(Tool):
    """Read the contents of a file."""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read the contents of a file at the specified path. "
            "Returns the file content as text. Use this to examine code, "
            "configuration files, or any text-based files."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path to the file to read (relative or absolute).",
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum number of lines to read. Defaults to 500.",
                },
            },
            "required": ["path"],
        }

    def execute(self, path: str, max_lines: int = 500, **kwargs: Any) -> ToolResult:
        try:
            file_path = Path(path).resolve()

            if not file_path.exists():
                return ToolResult(False, "", f"File not found: {path}")

            if not file_path.is_file():
                return ToolResult(False, "", f"Not a file: {path}")

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            content = "".join(lines[:max_lines])

            if total_lines > max_lines:
                content += f"\n\n... [Truncated: showing {max_lines} of {total_lines} lines]"

            return ToolResult(True, content)

        except PermissionError:
            return ToolResult(False, "", f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(False, "", str(e))


class ListFilesTool(Tool):
    """List files in a directory."""

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return (
            "List files and directories at the specified path. "
            "Supports glob patterns for filtering (e.g., '*.py', '**/*.js'). "
            "Use this to explore project structure and find files."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory path to list. Defaults to current directory.",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g., '*.py', '**/*.js').",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Whether to list recursively. Defaults to False.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results. Defaults to 100.",
                },
            },
            "required": [],
        }

    def execute(
        self,
        path: str = ".",
        pattern: str = "*",
        recursive: bool = False,
        max_results: int = 100,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            dir_path = Path(path).resolve()

            if not dir_path.exists():
                return ToolResult(False, "", f"Directory not found: {path}")

            if not dir_path.is_dir():
                return ToolResult(False, "", f"Not a directory: {path}")

            results: list[str] = []
            glob_pattern = f"**/{pattern}" if recursive else pattern

            for item in dir_path.glob(glob_pattern):
                if len(results) >= max_results:
                    break

                rel_path = item.relative_to(dir_path)
                suffix = "/" if item.is_dir() else ""
                results.append(f"{rel_path}{suffix}")

            results.sort()
            output = "\n".join(results)

            if len(results) >= max_results:
                output += f"\n\n... [Truncated: showing {max_results} results]"

            return ToolResult(True, output or "(empty directory)")

        except PermissionError:
            return ToolResult(False, "", f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(False, "", str(e))


class WriteFileTool(Tool):
    """Write content to a file (creates backup first)."""

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Write content to a file. Creates the file if it doesn't exist, "
            "or overwrites if it does (after creating a backup). "
            "Use this to create new files or replace file contents entirely."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path to the file to write.",
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file.",
                },
            },
            "required": ["path", "content"],
        }

    @property
    def requires_confirmation(self) -> bool:
        return True

    def execute(self, path: str, content: str, **kwargs: Any) -> ToolResult:
        try:
            file_path = Path(path).resolve()

            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Create backup if file exists
            backup_path = None
            if file_path.exists():
                backup_path = self._create_backup(file_path)

            # Write the new content
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            msg = f"Wrote {len(content)} bytes to {path}"
            if backup_path:
                msg += f" (backup: {backup_path})"

            return ToolResult(True, msg)

        except PermissionError:
            return ToolResult(False, "", f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(False, "", str(e))

    def _create_backup(self, file_path: Path) -> str:
        """Create a backup of the file and register it."""
        from ..backup import add_backup_entry
        from ..config import get_backup_dir

        backup_dir = get_backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{file_path.name}.{timestamp}.bak"
        backup_path = backup_dir / backup_name

        shutil.copy(file_path, backup_path)
        add_backup_entry(str(file_path), str(backup_path))

        return str(backup_path)

    def format_confirmation(self, path: str, content: str, **kwargs: Any) -> str:
        file_path = Path(path).resolve()
        exists = file_path.exists()

        lines = content.count("\n") + 1
        preview_lines = content.split("\n")[:10]
        preview = "\n".join(preview_lines)
        if len(content.split("\n")) > 10:
            preview += "\n... (truncated)"

        action = "Overwrite" if exists else "Create"
        return f"{action} file: {path}\n\nContent ({lines} lines):\n```\n{preview}\n```"


class EditFileTool(Tool):
    """Edit specific parts of a file using search and replace."""

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "Edit a file by replacing specific text. Searches for 'old_text' "
            "and replaces it with 'new_text'. Creates a backup before editing. "
            "Use this for targeted edits instead of rewriting entire files."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The path to the file to edit.",
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact text to find and replace.",
                },
                "new_text": {
                    "type": "string",
                    "description": "The text to replace it with.",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences. Defaults to False (first only).",
                },
            },
            "required": ["path", "old_text", "new_text"],
        }

    @property
    def requires_confirmation(self) -> bool:
        return True

    def execute(
        self,
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            file_path = Path(path).resolve()

            if not file_path.exists():
                return ToolResult(False, "", f"File not found: {path}")

            # Read current content
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if old_text not in content:
                return ToolResult(False, "", f"Text not found in {path}")

            # Count occurrences
            occurrences = content.count(old_text)

            # Create backup
            write_tool = WriteFileTool()
            backup_path = write_tool._create_backup(file_path)

            # Perform replacement
            if replace_all:
                new_content = content.replace(old_text, new_text)
                replaced = occurrences
            else:
                new_content = content.replace(old_text, new_text, 1)
                replaced = 1

            # Write changes
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return ToolResult(
                True,
                f"Replaced {replaced} occurrence(s) in {path} (backup: {backup_path})",
            )

        except PermissionError:
            return ToolResult(False, "", f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(False, "", str(e))

    def format_confirmation(
        self,
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False,
        **kwargs: Any,
    ) -> str:
        mode = "all occurrences" if replace_all else "first occurrence"
        return (
            f"Edit file: {path} ({mode})\n\n"
            f"Find:\n```\n{old_text}\n```\n\n"
            f"Replace with:\n```\n{new_text}\n```"
        )
