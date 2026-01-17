"""Agent loop for agentic capabilities."""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm

from .api import ChatResponse, MistralAPI, ToolCall
from .context import ConversationContext
from .memory import MemoryManager
from .tools import Tool, ToolResult, get_all_tools, get_tool_schemas
from .tools.memory import UpdateMemoryTool
from .tools.verifier import VerifyTool
from .verifier import Verifier

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


class PlanStatus(Enum):
    """Status of a plan or plan step."""

    PENDING = "pending"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class PlanStep:
    """A single step in an execution plan."""

    number: int
    description: str
    status: PlanStatus = PlanStatus.PENDING
    tool_name: Optional[str] = None


@dataclass
class Plan:
    """Execution plan for complex tasks."""

    summary: str
    steps: list[PlanStep] = field(default_factory=list)
    status: PlanStatus = PlanStatus.PENDING
    requires_confirmation: bool = True

    @classmethod
    def parse_from_response(cls, content: str) -> Optional["Plan"]:
        """Parse a plan from model response containing <plan> block.

        Args:
            content: The model's response text.

        Returns:
            A Plan object if a valid plan block was found, None otherwise.
        """
        plan_match = re.search(r"<plan>(.*?)</plan>", content, re.DOTALL)
        if not plan_match:
            return None

        plan_text = plan_match.group(1).strip()
        lines = plan_text.split("\n")

        summary = ""
        steps = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Match numbered steps: "1. Do something" or "Step 1: Do something"
            step_match = re.match(r"(?:Step\s+)?(\d+)[.):]\s*(.+)", line)
            if step_match:
                steps.append(
                    PlanStep(
                        number=int(step_match.group(1)),
                        description=step_match.group(2).strip(),
                    )
                )
            elif not steps:
                # First non-step line becomes summary
                summary = line

        if not steps:
            return None

        return cls(
            summary=summary or "Execution Plan",
            steps=steps,
            requires_confirmation=len(steps) > 3,
        )

    def format_for_display(self) -> str:
        """Format plan for Rich display.

        Returns:
            Markdown-formatted string representation of the plan.
        """
        lines = [f"**{self.summary}**\n"]
        for step in self.steps:
            status_icon = {
                PlanStatus.PENDING: "[ ]",
                PlanStatus.APPROVED: "[~]",
                PlanStatus.EXECUTING: "[>]",
                PlanStatus.COMPLETED: "[x]",
                PlanStatus.CANCELLED: "[-]",
            }.get(step.status, "[ ]")
            lines.append(f"{status_icon} {step.number}. {step.description}")
        return "\n".join(lines)

    def mark_step_executing(self, step_number: int) -> None:
        """Mark a step as currently executing."""
        for step in self.steps:
            if step.number == step_number:
                step.status = PlanStatus.EXECUTING
                break

    def mark_step_completed(self, step_number: int) -> None:
        """Mark a step as completed."""
        for step in self.steps:
            if step.number == step_number:
                step.status = PlanStatus.COMPLETED
                break


# Complexity detection constants
COMPLEXITY_KEYWORDS = {
    "refactor",
    "implement",
    "migrate",
    "redesign",
    "create",
    "build",
    "add feature",
    "multiple files",
    "across the",
    "entire",
    "all files",
    "comprehensive",
    "full",
    "complete overhaul",
}
COMPLEXITY_WORD_THRESHOLD = 50


def is_complex_request(user_input: str) -> bool:
    """Determine if a request requires planning.

    A request is considered complex if:
    - Contains more than 50 words
    - Contains complexity keywords (refactor, implement, migrate, etc.)
    - References multiple files explicitly

    Args:
        user_input: The user's request text.

    Returns:
        True if planning should be triggered, False otherwise.
    """
    # Word count check
    words = user_input.split()
    if len(words) > COMPLEXITY_WORD_THRESHOLD:
        return True

    # Keyword check (case-insensitive)
    lower_input = user_input.lower()
    for keyword in COMPLEXITY_KEYWORDS:
        if keyword in lower_input:
            return True

    # Multi-file reference check
    file_refs = re.findall(
        r"\b[\w/\\]+\.(py|js|ts|tsx|jsx|go|rs|java|c|cpp|h|hpp|md|json|yaml|yml)\b",
        user_input,
    )
    if len(file_refs) >= 2:
        return True

    return False


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
        load_mcp: bool = True,
    ):
        """Initialize the agent.

        Args:
            api: The Mistral API client.
            config: Agent configuration.
            tools: List of tools to make available. Defaults to all tools.
            load_mcp: Whether to load tools from configured MCP servers.
        """
        self.api = api
        self.config = config or AgentConfig()
        self.tools = tools or get_all_tools()
        self.tool_map = {t.name: t for t in self.tools}
        self.context = ConversationContext()
        self.state = AgentState()

        # Initialize memory
        self.memory_manager = MemoryManager()
        
        # Add memory tool if not present
        if "update_memory" not in self.tool_map:
            memory_tool = UpdateMemoryTool(self.memory_manager)
            self.tools.append(memory_tool)
            self.tool_map[memory_tool.name] = memory_tool

        # Initialize verifier
        self.verifier = Verifier()
        
        # Add verifier tool if not present
        if "verify_change" not in self.tool_map:
            verify_tool = VerifyTool(self.verifier)
            self.tools.append(verify_tool)
            self.tool_map[verify_tool.name] = verify_tool

        # MCP integration
        self.mcp_manager: Optional["MCPManager"] = None
        if load_mcp:
            self._load_mcp_tools()

        # Planning state
        self.current_plan: Optional[Plan] = None
        self.planning_mode: bool = False  # Explicit planning via /plan command

        # Callbacks for UI integration
        self.on_thinking: Optional[Callable[[], None]] = None
        self.on_tool_call: Optional[Callable[[str, dict], None]] = None
        self.on_tool_result: Optional[Callable[[str, ToolResult], None]] = None
        self.on_response: Optional[Callable[[str], None]] = None
        self.on_plan: Optional[Callable[[Plan], None]] = None  # Called when plan is generated

    def _load_mcp_tools(self) -> None:
        """Load tools from configured MCP servers."""
        from .config import get_mcp_servers
        from .mcp_client import MCPManager, MCPServerConfig

        server_configs = get_mcp_servers()
        if not server_configs:
            return

        self.mcp_manager = MCPManager()

        for cfg in server_configs:
            try:
                mcp_config = MCPServerConfig(
                    name=cfg.get("name", "unnamed"),
                    transport=cfg.get("transport", "stdio"),
                    command=cfg.get("command"),
                    url=cfg.get("url"),
                    env=cfg.get("env"),
                    timeout=cfg.get("timeout", 30),
                )
                if self.mcp_manager.add_server(mcp_config):
                    # Merge MCP tools with built-in tools
                    mcp_tools = self.mcp_manager.clients[mcp_config.name].get_tools()
                    self.tools.extend(mcp_tools)
                    for t in mcp_tools:
                        self.tool_map[t.name] = t
            except Exception:
                continue  # Skip failed servers

    def __del__(self):
        """Clean up MCP connections."""
        if self.mcp_manager:
            self.mcp_manager.disconnect_all()

    def get_system_prompt(self) -> str:
        """Build the system prompt with tool awareness."""
        base_prompt = self.context.get_system_prompt()

        # Inject memory
        memories = self.memory_manager.get_all()
        if memories:
            memory_section = "\n\n## User Preferences & Facts\n"
            for k, v in memories.items():
                memory_section += f"- **{k}**: {v}\n"
            base_prompt += memory_section

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
        self.current_plan = None

        # Determine if planning is needed
        needs_planning = self.planning_mode or is_complex_request(user_input)

        # Reset planning_mode after capturing it (one-shot)
        was_planning_mode = self.planning_mode
        self.planning_mode = False

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

            # Check for plan in response (only on first iteration for complex requests)
            if needs_planning and self.current_plan is None and response.content:
                plan = Plan.parse_from_response(response.content)
                if plan:
                    self.current_plan = plan

                    # Notify via callback
                    if self.on_plan:
                        self.on_plan(plan)

                    # Confirm plan if needed (explicit planning mode or >3 steps)
                    if (was_planning_mode or plan.requires_confirmation) and not self.config.confirm_all:
                        if not self._confirm_plan(plan):
                            self.current_plan.status = PlanStatus.CANCELLED
                            return "Plan cancelled by user."
                        plan.status = PlanStatus.APPROVED

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

                # Mark plan as completed if we had one
                if self.current_plan:
                    self.current_plan.status = PlanStatus.COMPLETED

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

    def _confirm_plan(self, plan: Plan) -> bool:
        """Show plan and get user confirmation.

        Args:
            plan: The plan to confirm.

        Returns:
            True if confirmed, False otherwise.
        """
        console.print()
        console.print(
            Panel(
                Markdown(plan.format_for_display()),
                title="[yellow]Proposed Plan[/yellow]",
                border_style="yellow",
            )
        )

        try:
            return Confirm.ask("[yellow]Execute this plan?[/yellow]", default=True)
        except KeyboardInterrupt:
            return False

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
