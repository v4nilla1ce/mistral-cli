"""Shell command execution tool."""

import os
import platform
import re
import subprocess
from typing import Any, Optional

from .base import Tool, ToolResult

# Windows exit code meanings
WINDOWS_EXIT_CODES: dict[int, str] = {
    0: "Success",
    1: "General error",
    2: "File not found",
    3: "Path not found",
    5: "Access denied",
    9009: "Command not found (not in PATH)",
    -1073741510: "Process terminated (Ctrl+C)",
    -1073741819: "Access violation",
}

# Unix exit code meanings
UNIX_EXIT_CODES: dict[int, str] = {
    0: "Success",
    1: "General error",
    2: "Misuse of shell command",
    126: "Permission denied (not executable)",
    127: "Command not found",
    128: "Invalid exit argument",
    130: "Terminated by Ctrl+C",
    137: "Killed (SIGKILL)",
    139: "Segmentation fault",
}

# Stderr patterns and their hints
STDERR_PATTERNS: list[tuple[str, str]] = [
    # Windows-specific
    (r"'(\w+)' is not recognized", "Command '{0}' not found. Check if it's installed and in PATH."),
    (r"is not recognized as an internal or external command", "Command not found. Check spelling and PATH."),
    # Unix-specific
    (r"command not found", "Command not found. Check if it's installed and in PATH."),
    (r"No such file or directory", "File or directory not found. Check the path exists."),
    (r"Permission denied", "Permission denied. May need elevated permissions or check file permissions."),
    # Python-specific
    (r"python3.*not found|python3.*not recognized", "Try 'python' instead of 'python3' on Windows."),
    (r"No module named", "Python module not installed. Try 'pip install <module>'."),
    # Node-specific
    (r"npm ERR! code ENOENT", "File not found. Check package.json exists."),
    (r"node:.*MODULE_NOT_FOUND", "Node module not found. Try 'npm install'."),
    # Git-specific
    (r"not a git repository", "Not in a git repository. Run 'git init' or navigate to a repo."),
]


def _get_exit_code_meaning(code: int) -> str:
    """Get human-readable meaning for an exit code."""
    if platform.system() == "Windows":
        return WINDOWS_EXIT_CODES.get(code, "Unknown error")
    return UNIX_EXIT_CODES.get(code, "Unknown error")


def _compute_hint(exit_code: int, output: str, command: str) -> Optional[str]:
    """Compute a helpful hint based on exit code and output patterns."""
    # Check stderr patterns first (more specific)
    for pattern, hint_template in STDERR_PATTERNS:
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            # If pattern has a capture group, use it in the hint
            if match.groups():
                return hint_template.format(*match.groups())
            return hint_template

    # Fall back to exit code based hints
    if platform.system() == "Windows":
        if exit_code == 9009:
            # Extract command name for more specific hint
            cmd_name = command.split()[0] if command else "command"
            if cmd_name == "python3":
                return "Try 'python' instead of 'python3' on Windows."
            return f"'{cmd_name}' not found. Check if it's installed and in PATH."
    else:
        if exit_code == 127:
            cmd_name = command.split()[0] if command else "command"
            return f"'{cmd_name}' not found. Check if it's installed and in PATH."
        if exit_code == 126:
            return "Permission denied. Check file permissions or use 'chmod +x'."

    return None


class ShellTool(Tool):
    """Execute shell commands."""

    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command and return its output. "
            "Use this to run build commands, tests, git operations, "
            "or any other command-line tasks. Commands run in the current directory."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Working directory for the command. Defaults to current directory.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds. Defaults to 60.",
                },
            },
            "required": ["command"],
        }

    @property
    def requires_confirmation(self) -> bool:
        return True

    # Commands that are generally safe (read-only)
    SAFE_COMMANDS = {
        "ls",
        "dir",
        "pwd",
        "echo",
        "cat",
        "head",
        "tail",
        "grep",
        "find",
        "which",
        "whereis",
        "type",
        "git status",
        "git log",
        "git diff",
        "git branch",
        "git remote -v",
        "python --version",
        "python3 --version",
        "pip list",
        "pip show",
        "npm list",
        "node --version",
        "cargo --version",
        "rustc --version",
    }

    def execute(
        self,
        command: str,
        working_dir: str | None = None,
        timeout: int = 60,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            # Resolve working directory
            cwd = os.path.abspath(working_dir) if working_dir else os.getcwd()

            if not os.path.isdir(cwd):
                return ToolResult(False, "", f"Directory not found: {cwd}")

            # Execute command
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            # Combine stdout and stderr
            output_parts = []
            if result.stdout:
                output_parts.append(result.stdout)
            if result.stderr:
                output_parts.append(f"[stderr]\n{result.stderr}")

            output = "\n".join(output_parts).strip()

            # Truncate if too long
            max_output = 10000
            if len(output) > max_output:
                output = output[:max_output] + f"\n\n... [Truncated: {len(output)} chars total]"

            if result.returncode == 0:
                return ToolResult(True, output or "(no output)")
            else:
                code = result.returncode
                meaning = _get_exit_code_meaning(code)
                hint = _compute_hint(code, output, command)
                return ToolResult(
                    success=False,
                    output=output,
                    error=f"Exit code {code}: {meaning}",
                    exit_code=code,
                    hint=hint,
                )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error=f"Command timed out after {timeout} seconds",
                hint="Consider increasing timeout or breaking into smaller commands.",
            )
        except FileNotFoundError:
            cmd_name = command.split()[0] if command else "command"
            return ToolResult(
                success=False,
                output="",
                error=f"Command not found: {cmd_name}",
                exit_code=127 if platform.system() != "Windows" else 9009,
                hint=f"'{cmd_name}' is not installed or not in PATH.",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def format_confirmation(
        self, command: str, working_dir: str | None = None, **kwargs: Any
    ) -> str:
        cwd = working_dir or os.getcwd()
        return f"Execute command:\n```\n$ {command}\n```\nIn directory: {cwd}"

    def is_safe_command(self, command: str) -> bool:
        """Check if a command is in the safe list.

        This can be used by the agent to skip confirmation for read-only commands.
        """
        cmd_lower = command.lower().strip()

        # Check exact matches and prefixes
        for safe in self.SAFE_COMMANDS:
            if cmd_lower == safe or cmd_lower.startswith(safe + " "):
                return True

        return False

    def _apply_os_aliases(self, command: str) -> str:
        """Translate unix-style commands to Windows equivalents if needed."""
        if platform.system() != "Windows":
            return command
            
        parts = command.split()
        if not parts:
            return command
            
        base_cmd = parts[0].lower()
        
        # Mapping common unix commands to Windows
        aliases = {
            "ls": "dir",
            "rm": "del /q" if "-rf" in command else "del",
            "cp": "copy",
            "mv": "move",
            "cat": "type",
            "clear": "cls",
            "pwd": "cd",
            "touch": "type nul >",
            "grep": "findstr",
        }
        
        if base_cmd in aliases:
            # Handle specific flags or complex replacements if needed
            # For now, simple replacement of the command verb
            new_cmd = aliases[base_cmd]
            
            # Special handling
            if base_cmd == "touch":
                # touch file -> type nul > file
                if len(parts) > 1:
                    return f"type nul > {parts[1]}"
            elif base_cmd == "grep":
                 # grep pattern file -> findstr pattern file
                 return command.replace("grep", "findstr")
            elif base_cmd == "rm" and "-rf" in command:
                 # rm -rf dir -> rmdir /s /q dir
                 target = parts[-1] 
                 return f"rmdir /s /q {target}"
            
            # Simple replacement
            return command.replace(parts[0], new_cmd, 1)
            
        return command

    def execute(
        self,
        command: str,
        working_dir: str | None = None,
        timeout: int = 60,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            # Smart OS Aliasing
            original_command = command
            command = self._apply_os_aliases(command)
            
            # Resolve working directory
            cwd = os.path.abspath(working_dir) if working_dir else os.getcwd()

            if not os.path.isdir(cwd):
                return ToolResult(False, "", f"Directory not found: {cwd}")

            # Execute command
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            # Combine stdout and stderr
            output_parts = []
            if original_command != command:
                output_parts.append(f"[debug] Aliased '{original_command}' -> '{command}'")
                
            if result.stdout:
                output_parts.append(result.stdout)
            if result.stderr:
                output_parts.append(f"[stderr]\n{result.stderr}")

            output = "\n".join(output_parts).strip()

            # Truncate if too long
            max_output = 10000
            if len(output) > max_output:
                output = output[:max_output] + f"\n\n... [Truncated: {len(output)} chars total]"

            if result.returncode == 0:
                return ToolResult(True, output or "(no output)")
            else:
                code = result.returncode
                meaning = _get_exit_code_meaning(code)
                hint = _compute_hint(code, output, command)
                
                # Check if it was an aliasing failure
                if code != 0 and original_command != command:
                     hint = (hint or "") + f"\nNote: Command was aliased from '{original_command}'. Try using 'filesystem' tool instead."

                return ToolResult(
                    success=False,
                    output=output,
                    error=f"Exit code {code}: {meaning}",
                    exit_code=code,
                    hint=hint,
                )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error=f"Command timed out after {timeout} seconds",
                hint="Consider increasing timeout or breaking into smaller commands.",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
