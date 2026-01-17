"""Tests for the Agent class."""

from unittest.mock import MagicMock, patch

import pytest

from mistral_cli.agent import Agent, AgentConfig, AgentState
from mistral_cli.api import ChatResponse, MistralAPI, ToolCall
from mistral_cli.tools import Tool, ToolResult
from mistral_cli.tools.base import Tool as BaseTool


class MockTool(BaseTool):
    """A mock tool for testing."""

    def __init__(self, name: str = "mock_tool", requires_confirm: bool = False):
        self._name = name
        self._requires_confirm = requires_confirm

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "A mock tool for testing"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "arg1": {"type": "string", "description": "Test argument"},
            },
            "required": ["arg1"],
        }

    @property
    def requires_confirmation(self) -> bool:
        return self._requires_confirm

    def execute(self, arg1: str = "", **kwargs) -> ToolResult:
        return ToolResult(success=True, output=f"Executed with: {arg1}")


class TestAgentConfig:
    """Tests for AgentConfig."""

    def test_default_config(self):
        config = AgentConfig()
        assert config.model == "mistral-small"
        assert config.max_iterations == 10
        assert not config.auto_confirm_safe
        assert not config.confirm_all

    def test_custom_config(self):
        config = AgentConfig(
            model="mistral-large",
            max_iterations=5,
            confirm_all=True,
        )
        assert config.model == "mistral-large"
        assert config.max_iterations == 5
        assert config.confirm_all


class TestAgentState:
    """Tests for AgentState."""

    def test_initial_state(self):
        state = AgentState()
        assert state.iteration == 0
        assert state.tool_calls_made == []
        assert not state.cancelled


class TestAgent:
    """Tests for the Agent class."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API client."""
        api = MagicMock(spec=MistralAPI)
        return api

    @pytest.fixture
    def agent(self, mock_api):
        """Create an agent with mock API."""
        tools = [MockTool("test_tool")]
        return Agent(api=mock_api, tools=tools)

    def test_agent_initialization(self, mock_api):
        agent = Agent(api=mock_api)
        assert agent.api == mock_api
        assert agent.config.model == "mistral-small"
        assert len(agent.tools) > 0

    def test_agent_with_custom_tools(self, mock_api):
        custom_tool = MockTool("custom")
        agent = Agent(api=mock_api, tools=[custom_tool])
        assert len(agent.tools) == 1
        assert agent.tools[0].name == "custom"

    def test_get_system_prompt(self, agent):
        prompt = agent.get_system_prompt()
        assert "test_tool" in prompt
        assert "tools" in prompt.lower()

    def test_list_tools(self, agent):
        tools = agent.list_tools()
        assert len(tools) == 1
        name, desc, needs_confirm = tools[0]
        assert name == "test_tool"
        assert not needs_confirm

    def test_add_remove_file(self, agent, tmp_path):
        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        # Add file
        success, msg = agent.add_file(str(test_file))
        assert success
        assert str(test_file) in agent.list_files()

        # Remove file
        success, msg = agent.remove_file(str(test_file))
        assert success
        assert str(test_file) not in agent.list_files()

    def test_clear(self, agent, tmp_path):
        # Add some state
        test_file = tmp_path / "test.py"
        test_file.write_text("test")
        agent.add_file(str(test_file))
        agent.context.add_message("user", "test message")

        # Clear
        agent.clear()
        assert len(agent.list_files()) == 0
        assert len(agent.context.messages) == 0

    def test_run_simple_response(self, agent, mock_api):
        """Test agent run with a simple text response (no tool calls)."""
        mock_api.chat.return_value = ChatResponse(
            content="Hello! How can I help?",
            tool_calls=[],
            finish_reason="stop",
        )

        response = agent.run("Hello")

        assert response == "Hello! How can I help?"
        assert mock_api.chat.called

    def test_run_with_tool_call(self, mock_api):
        """Test agent run with tool call and result."""
        tool = MockTool("test_tool", requires_confirm=False)
        config = AgentConfig(confirm_all=True)  # Skip confirmation
        agent = Agent(api=mock_api, config=config, tools=[tool])

        # First call returns tool call, second returns final response
        mock_api.chat.side_effect = [
            ChatResponse(
                content="Let me help with that.",
                tool_calls=[
                    ToolCall(id="call_1", name="test_tool", arguments={"arg1": "test"})
                ],
                finish_reason="tool_calls",
            ),
            ChatResponse(
                content="Done! I executed the tool.",
                tool_calls=[],
                finish_reason="stop",
            ),
        ]

        response = agent.run("Do something")

        assert "Done!" in response
        assert mock_api.chat.call_count == 2
        assert len(agent.state.tool_calls_made) == 1
        assert agent.state.tool_calls_made[0]["name"] == "test_tool"

    def test_run_max_iterations(self, mock_api):
        """Test that agent stops at max iterations."""
        tool = MockTool("test_tool")
        config = AgentConfig(max_iterations=2, confirm_all=True)
        agent = Agent(api=mock_api, config=config, tools=[tool])

        # Always return tool calls (infinite loop scenario)
        mock_api.chat.return_value = ChatResponse(
            content="Calling tool...",
            tool_calls=[
                ToolCall(id="call_1", name="test_tool", arguments={"arg1": "test"})
            ],
            finish_reason="tool_calls",
        )

        response = agent.run("Loop forever")

        assert "maximum iterations" in response.lower()
        assert agent.state.iteration == 2

    def test_run_unknown_tool(self, mock_api):
        """Test handling of unknown tool calls."""
        config = AgentConfig(confirm_all=True)
        agent = Agent(api=mock_api, config=config, tools=[])

        mock_api.chat.side_effect = [
            ChatResponse(
                content="Using tool...",
                tool_calls=[
                    ToolCall(id="call_1", name="unknown_tool", arguments={})
                ],
                finish_reason="tool_calls",
            ),
            ChatResponse(
                content="Tool not found, let me try another way.",
                tool_calls=[],
                finish_reason="stop",
            ),
        ]

        response = agent.run("Do something")

        # Should handle gracefully and continue
        assert mock_api.chat.call_count == 2

    def test_cancel(self, agent):
        """Test agent cancellation."""
        agent.cancel()
        assert agent.state.cancelled

    def test_callbacks(self, mock_api):
        """Test that callbacks are invoked correctly."""
        tool = MockTool("test_tool")
        config = AgentConfig(confirm_all=True)
        agent = Agent(api=mock_api, config=config, tools=[tool])

        # Track callback invocations
        callbacks_called = {
            "thinking": False,
            "tool_call": False,
            "tool_result": False,
            "response": False,
        }

        agent.on_thinking = lambda: callbacks_called.update({"thinking": True})
        agent.on_tool_call = lambda n, a: callbacks_called.update({"tool_call": True})
        agent.on_tool_result = lambda n, r: callbacks_called.update({"tool_result": True})
        agent.on_response = lambda c: callbacks_called.update({"response": True})

        mock_api.chat.side_effect = [
            ChatResponse(
                content="Using tool...",
                tool_calls=[
                    ToolCall(id="call_1", name="test_tool", arguments={"arg1": "test"})
                ],
            ),
            ChatResponse(content="Done!", tool_calls=[]),
        ]

        agent.run("Test callbacks")

        assert callbacks_called["thinking"]
        assert callbacks_called["tool_call"]
        assert callbacks_called["tool_result"]
        assert callbacks_called["response"]


class TestAgentConfirmation:
    """Tests for tool confirmation behavior."""

    @pytest.fixture
    def dangerous_tool(self):
        return MockTool("dangerous", requires_confirm=True)

    @pytest.fixture
    def safe_tool(self):
        return MockTool("safe", requires_confirm=False)

    def test_confirm_all_skips_confirmation(self):
        """Test that confirm_all=True skips all confirmations."""
        api = MagicMock(spec=MistralAPI)
        tool = MockTool("dangerous", requires_confirm=True)
        config = AgentConfig(confirm_all=True)
        agent = Agent(api=api, config=config, tools=[tool])

        api.chat.side_effect = [
            ChatResponse(
                content="Running...",
                tool_calls=[
                    ToolCall(id="1", name="dangerous", arguments={"arg1": "test"})
                ],
            ),
            ChatResponse(content="Done!", tool_calls=[]),
        ]

        # Should complete without prompting
        response = agent.run("Do dangerous thing")
        assert "Done!" in response

    def test_safe_tool_no_confirmation(self):
        """Test that safe tools don't require confirmation."""
        api = MagicMock(spec=MistralAPI)
        tool = MockTool("safe", requires_confirm=False)
        config = AgentConfig()  # Default config, no confirm_all
        agent = Agent(api=api, config=config, tools=[tool])

        api.chat.side_effect = [
            ChatResponse(
                content="Running...",
                tool_calls=[
                    ToolCall(id="1", name="safe", arguments={"arg1": "test"})
                ],
            ),
            ChatResponse(content="Done!", tool_calls=[]),
        ]

        # Should complete without prompting for safe tool
        response = agent.run("Do safe thing")
        assert "Done!" in response
