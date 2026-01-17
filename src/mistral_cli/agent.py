"""Agent loop for agentic capabilities."""

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm

from .api import ChatResponse, MistralAPI, ToolCall
from .context import ConversationContext
from .tools import Tool, ToolResult, get_all_tools, get_tool_schemas

console = Console()


# Circuit breaker thresholds
MAX_CONSECUTIVE_FAILURES = 3  # Same tool failing repeatedly
MAX_TOTAL_FAILURES = 5  # Total failures in one run


@dataclass
class AgentConfig:
    """Configuration for the agent."""

    model: str = "mistral-small"
    max_iterations: int = 10
    auto_confirm_safe: bool = False  # Auto-confirm safe commands (read-only)
    confirm_all: bool = False  # Skip all confirmations (trusted mode)
    circuit_breaker: bool = True  # Enable circuit breaker for failure protection


@dataclass
class AgentState:
    """Tracks agent execution state."""

    iteration: int = 0
    tool_calls_made: list[dict] = field(default_factory=list)
    cancelled: bool = False
    # Failure tracking for self-correction
    consecutive_failures: int = 0
    total_failures: int = 0
    last_failed_command: Optional[str] = None


class Agent:
    """Manages agentic conversation with tool execution.

    The agent implements a loop that:
    1. Sends user input to the model
    2. If the model requests tool calls, executes them (with confirmation)
    3. Sends tool results back to the model
    4. Repeats until the model provides a final response or max iterations reached
    """

    def __init__(
        self,
        api: MistralAPI,
        config: Optional[AgentConfig] = None,
        tools: Optional[list[Tool]] = None,
    ):
        """Initialize the agent.

        Args:
            api: The Mistral API client.
            config: Agent configuration.
            tools: List of tools to make available. Defaults to all tools.
        """
        self.api = api
        self.config = config or AgentConfig()
        self.tools = tools or get_all_tools()
        self.tool_map = {t.name: t for t in self.tools}
        self.context = ConversationContext()
        self.state = AgentState()

        # Callbacks for UI integration
        self.on_thinking: Optional[Callable[[], None]] = None
        self.on_tool_call: Optional[Callable[[str, dict], None]] = None
        self.on_tool_result: Optional[Callable[[str, ToolResult], None]] = None
        self.on_response: Optional[Callable[[str], None]] = None

    def get_system_prompt(self) -> str:
        """Build the system prompt with tool awareness."""
        base_prompt = self.context.get_system_prompt()

        tool_info = "\n\nYou have access to the following tools:\n"
        for tool in self.tools:
            tool_info += f"\n- **{tool.name}**: {tool.description}"

        tool_info += (
            "\n\nUse tools when needed to accomplish the user's request. "
            "You can call multiple tools in sequence. "
            "Always explain what you're doing before calling a tool."
        )

        return base_prompt + tool_info

    def run(self, user_input: str) -> str:
        """Run the agent loop for a user input.

        Args:
            user_input: The user's message.

        Returns:
            The final response from the model.
        """
        self.state = AgentState()

        # Build messages
        messages = self._build_messages(user_input)

        # Main agent loop
        while self.state.iteration < self.config.max_iterations:
            self.state.iteration += 1

            if self.on_thinking:
                self.on_thinking()

            # Call the model
            response = self.api.chat(
                messages=messages,
                model=self.config.model,
                tools=get_tool_schemas(self.tools),
                tool_choice="auto",
                return_full_response=True,
            )

            if not isinstance(response, ChatResponse):
                # Error case - treat as final response
                return str(response)

            # Check for tool calls
            if response.has_tool_calls:
                # Execute tools and add results to messages
                tool_messages = self._handle_tool_calls(response, messages)

                if self.state.cancelled:
                    return "Operation cancelled by user."

                messages.extend(tool_messages)

                # Circuit breaker check
                if self.config.circuit_breaker:
                    if self.state.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        return (
                            f"Circuit breaker triggered: {self.state.consecutive_failures} "
                            f"consecutive failures on the same operation. "
                            f"Last failed command: {self.state.last_failed_command or 'N/A'}. "
                            "Please check the command or environment and try again."
                        )
                    if self.state.total_failures >= MAX_TOTAL_FAILURES:
                        return (
                            f"Circuit breaker triggered: {self.state.total_failures} "
                            f"total failures in this session. "
                            "Multiple operations are failing. Please review the errors above."
                        )
            else:
                # No tool calls - this is the final response
                final_content = response.content or ""

                # Store in conversation history
                self.context.add_message("user", user_input)
                self.context.add_message("assistant", final_content)

                if self.on_response:
                    self.on_response(final_content)

                return final_content

        # Max iterations reached
        return (
            f"Reached maximum iterations ({self.config.max_iterations}). "
            "The task may be incomplete."
        )

    def _build_messages(self, user_input: str) -> list[dict[str, Any]]:
        """Build the message list for the API."""
        system_msg = {"role": "system", "content": self.get_system_prompt()}

        # Include conversation history
        messages = [system_msg] + self.context.messages.copy()
        messages.append({"role": "user", "content": user_input})

        return messages

    def _handle_tool_calls(
        self, response: ChatResponse, messages: list[dict]
    ) -> list[dict[str, Any]]:
        """Handle tool calls from the model.

        Args:
            response: The ChatResponse with tool calls.
            messages: The current message list (to append assistant message).

        Returns:
            List of tool result messages to append.
        """
        # Add assistant message with tool calls
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": response.content}

        if response.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in response.tool_calls
            ]

        messages.append(assistant_msg)

        # Execute each tool call
        tool_results = []

        for tool_call in response.tool_calls:
            if self.on_tool_call:
                self.on_tool_call(tool_call.name, tool_call.arguments)

            result = self._execute_tool(tool_call)

            if self.state.cancelled:
                break

            if self.on_tool_result:
                self.on_tool_result(tool_call.name, result)

            # Track the call
            self.state.tool_calls_made.append(
                {
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                    "success": result.success,
                }
            )

            # Update failure tracking
            if result.success:
                self.state.consecutive_failures = 0
                self.state.last_failed_command = None
            else:
                self.state.consecutive_failures += 1
                self.state.total_failures += 1
                # Track failed command for shell tools
                if tool_call.name == "shell":
                    self.state.last_failed_command = tool_call.arguments.get("command")

            # Add tool result message
            # Note: Hints are already included in result.to_message() for self-correction.
            # We cannot inject a separate system message here because Mistral API
            # doesn't allow 'system' role after 'tool' role.
            tool_results.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.name,
                    "content": result.to_message(),
                }
            )

        return tool_results

    def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a single tool call.

        Args:
            tool_call: The tool call to execute.

        Returns:
            The tool result.
        """
        tool = self.tool_map.get(tool_call.name)

        if not tool:
            return ToolResult(False, "", f"Unknown tool: {tool_call.name}")

        # Check if confirmation is needed
        if tool.requires_confirmation and not self.config.confirm_all:
            # Check for auto-confirm safe commands
            if self.config.auto_confirm_safe:
                from .tools.shell import ShellTool

                if isinstance(tool, ShellTool):
                    cmd = tool_call.arguments.get("command", "")
                    if tool.is_safe_command(cmd):
                        return tool.execute(**tool_call.arguments)

            # Show confirmation
            if not self._confirm_tool_execution(tool, tool_call.arguments):
                self.state.cancelled = True
                return ToolResult(False, "", "Cancelled by user")

        try:
            return tool.execute(**tool_call.arguments)
        except Exception as e:
            return ToolResult(False, "", f"Tool execution failed: {e}")

    def _confirm_tool_execution(self, tool: Tool, arguments: dict) -> bool:
        """Show confirmation prompt for a tool.

        Args:
            tool: The tool to confirm.
            arguments: The tool arguments.

        Returns:
            True if confirmed, False otherwise.
        """
        confirmation_text = tool.format_confirmation(**arguments)

        console.print()
        console.print(
            Panel(
                Markdown(confirmation_text),
                title=f"[yellow]Tool: {tool.name}[/yellow]",
                border_style="yellow",
            )
        )

        try:
            return Confirm.ask("[yellow]Execute this tool?[/yellow]", default=True)
        except KeyboardInterrupt:
            return False

    def cancel(self) -> None:
        """Cancel the current agent loop."""
        self.state.cancelled = True

    def clear(self) -> None:
        """Clear conversation history."""
        self.context.clear()
        self.state = AgentState()

    def add_file(self, path: str) -> tuple[bool, str]:
        """Add a file to the conversation context."""
        return self.context.add_file(path)

    def remove_file(self, path: str) -> tuple[bool, str]:
        """Remove a file from the conversation context."""
        return self.context.remove_file(path)

    def list_files(self) -> list[str]:
        """List files in the conversation context."""
        return list(self.context.files.keys())

    def list_tools(self) -> list[tuple[str, str, bool]]:
        """List available tools.

        Returns:
            List of (name, description, requires_confirmation) tuples.
        """
        return [
            (t.name, t.description, t.requires_confirmation) for t in self.tools
        ]
