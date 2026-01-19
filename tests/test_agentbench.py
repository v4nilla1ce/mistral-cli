"""Tests for AgentBench integration."""
import json
import unittest
from unittest.mock import MagicMock

from mistral_cli.agentbench import AgentBenchSession
from mistral_cli.api import ChatResponse, ToolCall


class TestAgentBenchSession(unittest.TestCase):
    def setUp(self):
        self.session = AgentBenchSession(api_key="fake-key")
        # Mock the API to avoid real calls
        self.session.api = MagicMock()

    def test_step_tool_call(self):
        """Test that the session correctly handles a tool call response."""
        # Setup mock response: a tool call to 'execute' with 'ls'
        mock_response = ChatResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="call_123",
                    name="execute",
                    arguments={"command": "ls -la"}
                )
            ],
            raw={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call_123",
                                    "type": "function",
                                    "function": {
                                        "name": "execute",
                                        "arguments": '{"command": "ls -la"}'
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        )
        self.session.api.chat.return_value = mock_response

        # Step
        observation = "Task: List files"
        result = self.session.step(observation)

        # Verify
        self.assertEqual(result, {"action": "ls -la"})
        self.session.api.chat.assert_called_once()
        
        # Verify history update
        # 1. Add Obs (User) -> messages=[System, User]
        # 2. Call API
        # 3. Add Response (Asst) -> messages=[System, User, Asst]
        self.assertEqual(len(self.session.messages), 3) 
        self.assertEqual(self.session.messages[1]["content"], "Task: List files")
        self.assertEqual(self.session.messages[2]["role"], "assistant")

    def test_step_text_response(self):
        """Test that the session handles text responses (thoughts)."""
        mock_response = ChatResponse(
            content="I need to check the directory.",
            tool_calls=[],
            raw={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "I need to check the directory."
                        }
                    }
                ]
            }
        )
        self.session.api.chat.return_value = mock_response

        result = self.session.step("Start")
        # Quotes should be escaped in echo
        self.assertEqual(result, {"action": "echo 'I need to check the directory.'"})

    def test_step_history_building(self):
        """Test that history is built correctly across steps."""
        # First step (User prompt -> Tool Call)
        mock_resp1 = ChatResponse(
            tool_calls=[ToolCall(id="call_1", name="execute", arguments={"command": "ls"})],
            raw={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "execute", "arguments": '{"command": "ls"}'}
                                }
                            ]
                        }
                    }
                ]
            }
        )
        self.session.api.chat.side_effect = [mock_resp1, None] # Set second to None initially
        
        self.session.step("Prompt")
        
        # Second step (Observation -> Text)
        mock_resp2 = ChatResponse(
            content="Done",
            raw={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Done"
                        }
                    }
                ]
            }
        )
        self.session.api.chat.side_effect = [mock_resp1, mock_resp2]
        
        result = self.session.step("file.txt") # Observation from `ls`
        
        # Verify history
        # 0: System
        # 1: User (Prompt)
        # 2: Assistant (Tool Call ls)
        # 3: Tool (Result of ls -> "file.txt")
        # 4: Assistant (Done)
        self.assertEqual(len(self.session.messages), 5)
        self.assertEqual(self.session.messages[3]["role"], "tool")
        self.assertEqual(self.session.messages[3]["content"], "file.txt")
        self.assertEqual(self.session.messages[3]["tool_call_id"], "call_1")

if __name__ == "__main__":
    unittest.main()
