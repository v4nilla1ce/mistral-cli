"""Prompt building and conversation context management."""

from typing import Any, Optional


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

    def get_system_prompt(self) -> str:
        """Construct the system prompt with file contents.

        Returns:
            The system prompt including any file context.
        """
        base_prompt = (
            "You are a helpful AI coding assistant.\n"
            "Provide clear, concise answers.\n"
            "Do not repeat code or explanations unnecessarily."
        )

        if not self.files:
            return base_prompt

        context_str = "\n\nContext Files:"
        for path, content in self.files.items():
            context_str += f"\n\n--- File: {path} ---\n{content}\n"

        return base_prompt + context_str

    def prepare_messages(self, user_input: str) -> list[dict[str, str]]:
        """Prepare the full list of messages for the API.

        Args:
            user_input: The current user message.

        Returns:
            List of message dicts ready for the API.
        """
        # Dynamically construct the system message to reflect current files
        system_msg = {"role": "system", "content": self.get_system_prompt()}

        # Combine system msg + history + current input
        msgs = [system_msg] + self.messages + [{"role": "user", "content": user_input}]
        return msgs

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
