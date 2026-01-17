
import os
import shutil
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult

class FileSystemTool(Tool):
    """Perform file system operations using Python's shutil."""

    @property
    def name(self) -> str:
        return "filesystem"

    @property
    def description(self) -> str:
        return (
            "Perform file system operations like move, copy, delete, and list. "
            "Safer and more cross-platform than shell commands."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["list", "move", "copy", "delete", "mkdir"],
                    "description": "The operation to perform.",
                },
                "path": {
                    "type": "string",
                    "description": "Source path for the operation.",
                },
                "destination": {
                    "type": "string",
                    "description": "Destination path (for move/copy).",
                },
            },
            "required": ["operation", "path"],
        }

    @property
    def requires_confirmation(self) -> bool:
        # We can make 'list' safe
        return True

    def execute(self, operation: str, path: str, destination: str | None = None, **kwargs) -> ToolResult:
        try:
            path_obj = Path(path).resolve()
            
            if operation == "list":
                if not path_obj.exists():
                    return ToolResult(False, "", f"Path not found: {path}")
                if path_obj.is_file():
                    return ToolResult(True, f"{path_obj.name} (file)")
                
                # List directory
                items = sorted(path_obj.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
                output = []
                for item in items:
                    type_str = "DIR" if item.is_dir() else "FILE"
                    output.append(f"{type_str:<4} {item.name}")
                return ToolResult(True, "\n".join(output))

            elif operation == "mkdir":
                path_obj.mkdir(parents=True, exist_ok=True)
                return ToolResult(True, f"Directory created: {path}")

            elif operation == "delete":
                if not path_obj.exists():
                    return ToolResult(False, "", f"Path not found: {path}")
                
                if path_obj.is_dir():
                    shutil.rmtree(path_obj)
                else:
                    path_obj.unlink()
                return ToolResult(True, f"Deleted: {path}")

            elif operation in ["move", "copy"]:
                if not destination:
                    return ToolResult(False, "", f"Destination required for {operation}")
                
                start_path = path_obj
                dest_path = Path(destination).resolve()
                
                if not start_path.exists():
                    return ToolResult(False, "", f"Source not found: {path}")

                if operation == "move":
                    shutil.move(str(start_path), str(dest_path))
                    return ToolResult(True, f"Moved {path} to {destination}")
                else:
                    if start_path.is_dir():
                        shutil.copytree(str(start_path), str(dest_path))
                    else:
                        shutil.copy2(str(start_path), str(dest_path))
                    return ToolResult(True, f"Copied {path} to {destination}")

            else:
                return ToolResult(False, "", f"Unknown operation: {operation}")

        except Exception as e:
            return ToolResult(False, "", f"FileSystem error: {e}")

    def format_confirmation(self, operation: str, path: str, destination: str | None=None, **kwargs) -> str:
        if operation == "list":
            return f"List files in: {path}"
        if destination:
            return f"{operation.capitalize()} {path} -> {destination}"
        return f"{operation.capitalize()} {path}"
