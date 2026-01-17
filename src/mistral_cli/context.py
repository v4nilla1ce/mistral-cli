"""Prompt building and conversation context management."""

import json
import os
import platform
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

from .config import get_data_dir, get_system_prompt as get_config_system_prompt

console = Console()


@dataclass
class SystemEnvironment:
    """Cached system environment information."""

    os_name: str
    os_version: str
    shell: str
    cwd: str
    available_binaries: list[str]
    timestamp: str

    def format_block(self) -> str:
        """Format environment info as a prompt block."""
        binaries = ", ".join(self.available_binaries) if self.available_binaries else "none detected"
        return (
            f"## Environment\n"
            f"- OS: {self.os_name} {self.os_version}\n"
            f"- Shell: {self.shell}\n"
            f"- CWD: {self.cwd}\n"
            f"- Available: {binaries}\n"
            f"- Time: {self.timestamp}"
        )


def _detect_shell() -> str:
    """Detect the current shell."""
    if platform.system() == "Windows":
        # Check for PowerShell vs CMD
        comspec = os.environ.get("COMSPEC", "")
        # PSModulePath is set in PowerShell
        if os.environ.get("PSModulePath"):
            return "PowerShell"
        elif "cmd.exe" in comspec.lower():
            return "CMD"
        return "Windows Shell"
    else:
        shell = os.environ.get("SHELL", "/bin/sh")
        return Path(shell).name


def _detect_binaries() -> list[str]:
    """Detect available key binaries using shutil.which()."""
    binaries_to_check = [
        "python",
        "python3",
        "node",
        "npm",
        "git",
        "pip",
        "cargo",
        "rustc",
    ]
    available = []
    for binary in binaries_to_check:
        if shutil.which(binary):
            available.append(binary)
    return available


def get_system_environment() -> SystemEnvironment:
    """Get cached system environment information.

    This is evaluated once and cached for the session.
    """
    global _cached_environment
    if _cached_environment is None:
        _cached_environment = SystemEnvironment(
            os_name=platform.system(),
            os_version=platform.release(),
            shell=_detect_shell(),
            cwd=os.getcwd(),
            available_binaries=_detect_binaries(),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
    return _cached_environment


def refresh_system_environment() -> SystemEnvironment:
    """Force refresh of cached system environment."""
    global _cached_environment
    _cached_environment = None
    return get_system_environment()


# Module-level cache for environment info
_cached_environment: Optional[SystemEnvironment] = None


# Model token limits (approximate)
MODEL_TOKEN_LIMITS = {
    "mistral-tiny": 8000,
    "mistral-small": 8000,
    "mistral-medium": 32000,
    "mistral-large": 32000,
    "default": 8000,
}


def read_relevant_file(file_path: str, max_lines: int = 50) -> str:
    """Read the first `max_lines` of a file.

    Args:
        file_path: Path to the file to read.
        max_lines: Maximum number of lines to read.

    Returns:
        The file content or an error message.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            lines = file.readlines()
            content = "".join(lines[:max_lines])
            return content
    except FileNotFoundError:
        return f"Error: File {file_path} not found."
    except Exception as e:
        return f"Error reading file: {e}"


def search_in_file(file_path: str, keyword: str) -> str:
    """Search for a keyword in the file.

    Args:
        file_path: Path to the file to search.
        keyword: Keyword to search for (uses first word).

    Returns:
        Matching lines with line numbers, or a message if none found.
    """
    try:
        # Extract the first word from the keyword
        function_name = keyword.split()[0]
        matches = []
        with open(file_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if function_name in line:
                    matches.append(f"{i}:{line.strip()}")

        return "\n".join(matches) if matches else "No matches found."
    except Exception as e:
        return f"Error searching file: {e}"


def build_prompt(file_path: str, bug_description: str) -> str:
    """Build the prompt for Mistral API.

    Args:
        file_path: Path to the file with the bug.
        bug_description: Description of the bug.

    Returns:
        The constructed prompt string.
    """
    file_content = read_relevant_file(file_path)
    # Extract function name
    function_name = bug_description.split()[0]
    # Dynamic search
    error_context = search_in_file(file_path, function_name)

    def construct_final_prompt(content: str, context: str) -> str:
        return f"""
    File: {file_path}
    Content:
    {content}

    Error Context:
    {context}

    Task: The following error was reported: {bug_description}
    Suggest a fix for the code in {file_path}.
    Respond with the corrected code inside a Python code block (```python ... ```).
    """

    prompt = construct_final_prompt(file_content, error_context)

    # Token Truncation logic
    try:
        from .tokens import count_tokens

        limit = 4000
        if count_tokens(prompt) > limit:
            # Simple heuristic truncation to save tokens
            truncated_len = len(file_content) // 2
            file_content = (
                file_content[:truncated_len]
                + "\n\n... [Content Truncated due to Context Limit] ..."
            )
            prompt = construct_final_prompt(file_content, error_context)
    except ImportError:
        pass  # Tokenizer not available

    return prompt


class ConversationContext:
    """Manages chat state with file context and message history."""

    def __init__(self) -> None:
        """Initialize an empty conversation context."""
        self.files: dict[str, str] = {}  # path -> content
        self.messages: list[dict[str, str]] = []

    def add_file(self, file_path: str) -> tuple[bool, str]:
        """Add a file to the context.

        Args:
            file_path: Path to the file to add.

        Returns:
            Tuple of (success, message).
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                self.files[file_path] = f.read()
            return True, f"Added {file_path}"
        except Exception as e:
            return False, str(e)

    def remove_file(self, file_path: str) -> tuple[bool, str]:
        """Remove a file from the context.

        Args:
            file_path: Path to the file to remove.

        Returns:
            Tuple of (success, message).
        """
        if file_path in self.files:
            del self.files[file_path]
            return True, f"Removed {file_path}"
        return False, "File not in context."

    def get_system_prompt(self, include_environment: bool = True) -> str:
        """Construct the system prompt with file contents and environment info.

        Args:
            include_environment: Whether to include system environment info.

        Returns:
            The system prompt including environment and file context.
        """
        parts = []

        # Add environment block first (for agent awareness)
        if include_environment:
            env = get_system_environment()
            parts.append(env.format_block())
            parts.append(
                "\n## Instructions\n"
                "If a command fails, analyze the error. "
                "Do not repeat failed commands verbatim. "
                "Adapt based on the OS and available tools."
            )

        # Check for custom system prompt from config
        custom_prompt = get_config_system_prompt()
        if custom_prompt:
            parts.append(f"\n\n{custom_prompt}")
        else:
            parts.append(
                "\n\nYou are a helpful AI coding assistant.\n"
                "Provide clear, concise answers.\n"
                "Do not repeat code or explanations unnecessarily."
            )

        # Add file context
        if self.files:
            context_str = "\n\nContext Files:"
            for path, content in self.files.items():
                context_str += f"\n\n--- File: {path} ---\n{content}\n"
            parts.append(context_str)

        return "".join(parts)

    def prepare_messages(
        self, user_input: str, model: str = "mistral-small"
    ) -> list[dict[str, str]]:
        """Prepare the full list of messages for the API.

        Args:
            user_input: The current user message.
            model: The model being used (for token limit checking).

        Returns:
            List of message dicts ready for the API.
        """
        # Dynamically construct the system message to reflect current files
        system_msg = {"role": "system", "content": self.get_system_prompt()}

        # Combine system msg + history + current input
        msgs = [system_msg] + self.messages + [{"role": "user", "content": user_input}]

        # Check context size and warn if approaching limit
        self._check_context_size(msgs, model)

        return msgs

    def _check_context_size(
        self, messages: list[dict[str, str]], model: str = "mistral-small"
    ) -> None:
        """Check if context size is approaching the model's token limit.

        Args:
            messages: The full message list.
            model: The model being used.
        """
        try:
            from .tokens import count_tokens

            # Calculate total content
            total_content = "\n".join(msg["content"] for msg in messages)
            token_count = count_tokens(total_content)

            # Get model limit
            limit = MODEL_TOKEN_LIMITS.get(model, MODEL_TOKEN_LIMITS["default"])
            usage_percent = (token_count / limit) * 100

            if usage_percent >= 90:
                console.print(
                    f"[bold red]Warning: Context at {usage_percent:.0f}% capacity "
                    f"({token_count:,}/{limit:,} tokens). Consider using /clear.[/]"
                )
            elif usage_percent >= 80:
                console.print(
                    f"[yellow]Warning: Context at {usage_percent:.0f}% capacity "
                    f"({token_count:,}/{limit:,} tokens).[/]"
                )
        except ImportError:
            pass  # Tokenizer not available

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the history.

        Args:
            role: The message role ('user' or 'assistant').
            content: The message content.
        """
        self.messages.append({"role": role, "content": content})

    def clear(self) -> None:
        """Reset conversation and files."""
        self.files = {}
        self.messages = []

    def _get_sessions_dir(self) -> Path:
        """Get the sessions directory path."""
        sessions_dir = get_data_dir() / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        return sessions_dir

    def save_session(self, name: str) -> tuple[bool, str]:
        """Save the current session to disk.

        Args:
            name: Name for the session.

        Returns:
            Tuple of (success, message).
        """
        try:
            session_data = {
                "files": self.files,
                "messages": self.messages,
            }

            session_path = self._get_sessions_dir() / f"{name}.json"
            with open(session_path, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2)

            return True, f"Session saved: {name}"
        except Exception as e:
            return False, f"Failed to save session: {e}"

    def load_session(self, name: str) -> tuple[bool, str]:
        """Load a session from disk.

        Args:
            name: Name of the session to load.

        Returns:
            Tuple of (success, message).
        """
        try:
            session_path = self._get_sessions_dir() / f"{name}.json"

            if not session_path.exists():
                return False, f"Session not found: {name}"

            with open(session_path, "r", encoding="utf-8") as f:
                session_data = json.load(f)

            self.files = session_data.get("files", {})
            self.messages = session_data.get("messages", [])

            file_count = len(self.files)
            msg_count = len(self.messages)
            return True, f"Loaded session: {name} ({file_count} files, {msg_count} messages)"
        except Exception as e:
            return False, f"Failed to load session: {e}"

    def list_sessions(self) -> list[str]:
        """List all saved sessions.

        Returns:
            List of session names.
        """
        sessions_dir = self._get_sessions_dir()
        return [p.stem for p in sessions_dir.glob("*.json")]
