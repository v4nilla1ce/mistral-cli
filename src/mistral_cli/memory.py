"""Active Memory "Hippocampus" for Mistral CLI agent.

Handles storage and retrieval of user preferences and facts across sessions.
Supports hierarchical scoping: Global (~/.local/share) and Project (.mistral/).
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union


class MemoryManager:
    """Manages agent memory across global and project scopes.
    
    Attributes:
        global_path: Path to global memory file.
        project_path: Path to project-specific memory file.
    """

    def __init__(self, global_path: Optional[Path] = None, project_path: Optional[Path] = None):
        """Initialize MemoryManager.

        Args:
            global_path: Custom path for global memory. Defaults to XDG share.
            project_path: Custom path for project memory. Defaults to .mistral/memory.json.
        """
        self.global_path = global_path or Path.home() / ".local" / "share" / "mistral-cli" / "memory.json"
        
        # Determine project path (current working directory)
        cwd = Path.cwd()
        self.project_path = project_path or cwd / ".mistral" / "memory.json"
        
        self.global_memory: Dict[str, Any] = {}
        self.project_memory: Dict[str, Any] = {}
        
        self._load_memory()

    def _load_memory(self) -> None:
        """Load memory from files."""
        self.global_memory = self._load_file(self.global_path)
        self.project_memory = self._load_file(self.project_path)

    def _load_file(self, path: Path) -> Dict[str, Any]:
        """Load JSON from a file, returning empty dict if missing/corrupt."""
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logging.warning(f"Failed to load memory from {path}: {e}")
            return {}

    def _save_file(self, path: Path, data: Dict[str, Any]) -> None:
        """Save dictionary to JSON file."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logging.error(f"Failed to save memory to {path}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value by key.
        
        Project memory takes precedence over Global memory.
        """
        if key in self.project_memory:
            return self.project_memory[key]
        return self.global_memory.get(key, default)

    def get_all(self) -> Dict[str, Any]:
        """Get all memory items.
        
        Merges Global and Project memory (Project overrides Global).
        """
        combined = self.global_memory.copy()
        combined.update(self.project_memory)
        return combined

    def set(self, key: str, value: Any, scope: str = "global") -> None:
        """Set a value in the specified scope.

        Args:
            key: Memory key.
            value: Value to store.
            scope: 'global' or 'project'.
        """
        if scope.lower() == "project":
            self.project_memory[key] = value
            self._save_file(self.project_path, self.project_memory)
        else:
            self.global_memory[key] = value
            self._save_file(self.global_path, self.global_memory)

    def delete(self, key: str, scope: str = "global") -> None:
        """Delete a key from the specified scope."""
        if scope.lower() == "project":
            if key in self.project_memory:
                del self.project_memory[key]
                self._save_file(self.project_path, self.project_memory)
        else:
            if key in self.global_memory:
                del self.global_memory[key]
                self._save_file(self.global_path, self.global_memory)

    def clear(self, scope: str = "all") -> None:
        """Clear memory.
        
        Args:
            scope: 'global', 'project', or 'all'.
        """
        if scope in ("project", "all"):
            self.project_memory = {}
            if self.project_path.exists():
                self._save_file(self.project_path, {})
        
        if scope in ("global", "all"):
            self.global_memory = {}
            if self.global_path.exists():
                self._save_file(self.global_path, {})
