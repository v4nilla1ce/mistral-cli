"""Shell command execution tool."""

import os
import shlex
import subprocess
from typing import Any

from .base import Tool, ToolResult


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
                return ToolResult(
                    False,
                    output,
                    f"Command exited with code {result.returncode}",
                )

        except subprocess.TimeoutExpired:
            return ToolResult(False, "", f"Command timed out after {timeout} seconds")
        except FileNotFoundError:
            return ToolResult(False, "", f"Command not found: {command.split()[0]}")
        except Exception as e:
            return ToolResult(False, "", str(e))

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
