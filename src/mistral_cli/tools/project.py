"""Project context and search tools."""

import fnmatch
import os
import re
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class SearchFilesTool(Tool):
    """Search for text patterns in files."""

    @property
    def name(self) -> str:
        return "search_files"

    @property
    def description(self) -> str:
        return (
            "Search for text or regex patterns in files within a directory. "
            "Returns matching lines with file paths and line numbers. "
            "Use this to find code, functions, or specific content."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The text or regex pattern to search for.",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in. Defaults to current directory.",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Glob pattern for files to search (e.g., '*.py'). Defaults to '*'.",
                },
                "regex": {
                    "type": "boolean",
                    "description": "Treat pattern as regex. Defaults to False.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum matches to return. Defaults to 50.",
                },
            },
            "required": ["pattern"],
        }

    # Common directories/files to skip
    SKIP_DIRS = {
        ".git",
        ".svn",
        ".hg",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        "env",
        ".env",
        "dist",
        "build",
        ".tox",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "egg-info",
    }

    def execute(
        self,
        pattern: str,
        path: str = ".",
        file_pattern: str = "*",
        regex: bool = False,
        max_results: int = 50,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            dir_path = Path(path).resolve()

            if not dir_path.exists():
                return ToolResult(False, "", f"Directory not found: {path}")

            # Compile regex if needed
            if regex:
                try:
                    compiled = re.compile(pattern)
                except re.error as e:
                    return ToolResult(False, "", f"Invalid regex: {e}")
            else:
                compiled = None

            results: list[str] = []

            for root, dirs, files in os.walk(dir_path):
                # Skip common non-project directories
                dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]

                for filename in files:
                    if not fnmatch.fnmatch(filename, file_pattern):
                        continue

                    file_path = Path(root) / filename

                    try:
                        matches = self._search_file(
                            file_path, pattern, compiled, max_results - len(results)
                        )
                        results.extend(matches)

                        if len(results) >= max_results:
                            break
                    except (UnicodeDecodeError, PermissionError):
                        continue

                if len(results) >= max_results:
                    break

            if not results:
                return ToolResult(True, f"No matches found for: {pattern}")

            output = "\n".join(results)
            if len(results) >= max_results:
                output += f"\n\n... [Truncated: showing {max_results} results]"

            return ToolResult(True, output)

        except Exception as e:
            return ToolResult(False, "", str(e))

    def _search_file(
        self,
        file_path: Path,
        pattern: str,
        compiled: re.Pattern | None,
        max_matches: int,
    ) -> list[str]:
        """Search a single file for matches."""
        matches = []

        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line_num, line in enumerate(f, 1):
                if compiled:
                    if compiled.search(line):
                        matches.append(f"{file_path}:{line_num}: {line.rstrip()}")
                else:
                    if pattern in line:
                        matches.append(f"{file_path}:{line_num}: {line.rstrip()}")

                if len(matches) >= max_matches:
                    break

        return matches


class ProjectContextTool(Tool):
    """Gather project context and structure information."""

    @property
    def name(self) -> str:
        return "project_context"

    @property
    def description(self) -> str:
        return (
            "Analyze a project directory to gather context about its structure, "
            "programming languages, frameworks, and key files. "
            "Use this to understand an unfamiliar codebase quickly."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The project root directory. Defaults to current directory.",
                },
            },
            "required": [],
        }

    # File patterns that indicate project types
    PROJECT_INDICATORS = {
        "Python": ["*.py", "pyproject.toml", "setup.py", "requirements.txt", "Pipfile"],
        "JavaScript/Node": ["*.js", "*.ts", "package.json", "tsconfig.json"],
        "Rust": ["*.rs", "Cargo.toml"],
        "Go": ["*.go", "go.mod"],
        "Java": ["*.java", "pom.xml", "build.gradle"],
        "C/C++": ["*.c", "*.cpp", "*.h", "CMakeLists.txt", "Makefile"],
        "Ruby": ["*.rb", "Gemfile"],
        "PHP": ["*.php", "composer.json"],
    }

    # Important files to highlight
    IMPORTANT_FILES = [
        "README.md",
        "README.rst",
        "README.txt",
        "LICENSE",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        ".gitignore",
        "Makefile",
        "Dockerfile",
        "docker-compose.yml",
        ".env.example",
    ]

    def execute(self, path: str = ".", **kwargs: Any) -> ToolResult:
        try:
            dir_path = Path(path).resolve()

            if not dir_path.exists():
                return ToolResult(False, "", f"Directory not found: {path}")

            if not dir_path.is_dir():
                return ToolResult(False, "", f"Not a directory: {path}")

            context = []

            # Project name
            context.append(f"# Project: {dir_path.name}")
            context.append("")

            # Detect project types
            detected_types = self._detect_project_types(dir_path)
            if detected_types:
                context.append(f"**Languages/Frameworks:** {', '.join(detected_types)}")
                context.append("")

            # Important files
            important = self._find_important_files(dir_path)
            if important:
                context.append("**Key Files:**")
                for f in important:
                    context.append(f"- {f}")
                context.append("")

            # Directory structure (top-level)
            context.append("**Directory Structure:**")
            context.append("```")
            structure = self._get_structure(dir_path, max_depth=2)
            context.append(structure)
            context.append("```")

            # File statistics
            stats = self._get_file_stats(dir_path)
            context.append("")
            context.append("**File Statistics:**")
            for ext, count in sorted(stats.items(), key=lambda x: -x[1])[:10]:
                context.append(f"- {ext}: {count} files")

            return ToolResult(True, "\n".join(context))

        except Exception as e:
            return ToolResult(False, "", str(e))

    def _detect_project_types(self, dir_path: Path) -> list[str]:
        """Detect programming languages and frameworks used."""
        detected = []

        for project_type, patterns in self.PROJECT_INDICATORS.items():
            for pattern in patterns:
                # Check top-level and one level deep
                if list(dir_path.glob(pattern)) or list(dir_path.glob(f"*/{pattern}")):
                    detected.append(project_type)
                    break

        return detected

    def _find_important_files(self, dir_path: Path) -> list[str]:
        """Find important project files."""
        found = []
        for filename in self.IMPORTANT_FILES:
            if (dir_path / filename).exists():
                found.append(filename)
        return found

    def _get_structure(self, dir_path: Path, max_depth: int = 2) -> str:
        """Generate a tree-like directory structure."""
        lines = []
        self._walk_structure(dir_path, lines, "", max_depth, 0)
        return "\n".join(lines)

    def _walk_structure(
        self,
        path: Path,
        lines: list[str],
        prefix: str,
        max_depth: int,
        current_depth: int,
    ) -> None:
        """Recursively build directory tree."""
        if current_depth > max_depth:
            return

        # Skip hidden and common non-project directories
        skip_dirs = {".git", ".svn", "__pycache__", "node_modules", ".venv", "venv"}

        try:
            items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError:
            return

        # Filter out hidden files at deeper levels
        if current_depth > 0:
            items = [i for i in items if not i.name.startswith(".")]

        dirs = [i for i in items if i.is_dir() and i.name not in skip_dirs]
        files = [i for i in items if i.is_file()]

        # Limit items shown
        if len(dirs) > 10:
            dirs = dirs[:10]
        if len(files) > 15:
            files = files[:15]

        for i, item in enumerate(dirs + files):
            is_last = i == len(dirs) + len(files) - 1
            connector = "└── " if is_last else "├── "
            suffix = "/" if item.is_dir() else ""

            lines.append(f"{prefix}{connector}{item.name}{suffix}")

            if item.is_dir() and current_depth < max_depth:
                extension = "    " if is_last else "│   "
                self._walk_structure(
                    item, lines, prefix + extension, max_depth, current_depth + 1
                )

    def _get_file_stats(self, dir_path: Path) -> dict[str, int]:
        """Count files by extension."""
        stats: dict[str, int] = {}
        skip_dirs = {".git", ".svn", "__pycache__", "node_modules", ".venv", "venv"}

        for root, dirs, files in os.walk(dir_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            for filename in files:
                ext = Path(filename).suffix or "(no extension)"
                stats[ext] = stats.get(ext, 0) + 1

        return stats
