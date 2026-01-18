"""JSON-RPC server for VS Code extension integration.

This module implements a JSON-RPC 2.0 server over stdio with newline-delimited
JSON (ndjson) framing. It exposes the agent and chat capabilities for use by
the VS Code extension.

Protocol:
- Each message is a single line of JSON terminated by \n
- Requests have an "id" field; notifications do not
- Server sends events as notifications (no id field)
"""

import json
import sys
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from queue import Empty, Queue
from typing import Any, Callable, Optional

from .agent import Agent, AgentConfig
from .api import MistralAPI
from .config import get_api_key
from .context import ConversationContext
from .tokens import count_tokens
from .tools import ToolResult


class ServerState(Enum):
    """Server lifecycle states."""
    IDLE = "idle"
    RUNNING = "running"
    PROCESSING = "processing"
    SHUTDOWN = "shutdown"


@dataclass
class PendingConfirmation:
    """Tracks a tool call awaiting user confirmation."""
    tool_call_id: str
    tool_name: str
    arguments: dict
    event: threading.Event = field(default_factory=threading.Event)
    approved: bool = False


class JSONRPCServer:
    """JSON-RPC 2.0 server over stdio.

    Provides methods for chat and agent operations, with event notifications
    for streaming responses and tool confirmations.
    """

    def __init__(self):
        """Initialize the server."""
        self.state = ServerState.IDLE
        self.api: Optional[MistralAPI] = None
        self.agent: Optional[Agent] = None
        self.context = ConversationContext()
        self.model = "mistral-small"

        # Pending tool confirmations
        self.pending_confirmations: dict[str, PendingConfirmation] = {}

        # Message queues
        self._output_lock = threading.Lock()
        self._shutdown_event = threading.Event()

        # Method handlers
        self._methods: dict[str, Callable] = {
            "initialize": self._handle_initialize,
            "shutdown": self._handle_shutdown,
            "chat": self._handle_chat,
            "agent.run": self._handle_agent_run,
            "agent.cancel": self._handle_agent_cancel,
            "agent.confirm": self._handle_agent_confirm,
            "context.add": self._handle_context_add,
            "context.remove": self._handle_context_remove,
            "context.list": self._handle_context_list,
            "context.clear": self._handle_context_clear,
            "model.set": self._handle_model_set,
            "model.get": self._handle_model_get,
        }

    def run(self) -> None:
        """Run the server main loop."""
        self.state = ServerState.RUNNING

        # Read from stdin line by line
        try:
            for line in sys.stdin:
                if self._shutdown_event.is_set():
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    message = json.loads(line)
                    self._handle_message(message)
                except json.JSONDecodeError as e:
                    self._send_error(None, -32700, f"Parse error: {e}")

        except KeyboardInterrupt:
            pass
        finally:
            self.state = ServerState.SHUTDOWN

    def _handle_message(self, message: dict) -> None:
        """Handle an incoming JSON-RPC message.

        Args:
            message: The parsed JSON-RPC message.
        """
        # Validate JSON-RPC 2.0 format
        if message.get("jsonrpc") != "2.0":
            self._send_error(
                message.get("id"),
                -32600,
                "Invalid Request: missing or invalid jsonrpc version"
            )
            return

        method = message.get("method")
        params = message.get("params", {})
        msg_id = message.get("id")  # None for notifications

        if not method:
            self._send_error(msg_id, -32600, "Invalid Request: missing method")
            return

        # Find and execute handler
        handler = self._methods.get(method)
        if not handler:
            self._send_error(msg_id, -32601, f"Method not found: {method}")
            return

        try:
            result = handler(params)
            if msg_id is not None:  # Only send response for requests, not notifications
                self._send_result(msg_id, result)
        except Exception as e:
            self._send_error(msg_id, -32603, f"Internal error: {e}")

    def _send_result(self, msg_id: Any, result: Any) -> None:
        """Send a successful response.

        Args:
            msg_id: The request ID.
            result: The result data.
        """
        response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": result,
        }
        self._send_message(response)

    def _send_error(self, msg_id: Any, code: int, message: str, data: Any = None) -> None:
        """Send an error response.

        Args:
            msg_id: The request ID (can be None).
            code: JSON-RPC error code.
            message: Error message.
            data: Optional additional error data.
        """
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data

        response: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": error,
        }
        self._send_message(response)

    def _send_notification(self, method: str, params: dict) -> None:
        """Send a notification (event) to the client.

        Args:
            method: The notification method name.
            params: Notification parameters.
        """
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        self._send_message(notification)

    def _send_message(self, message: dict) -> None:
        """Write a message to stdout.

        Args:
            message: The message to send.
        """
        with self._output_lock:
            sys.stdout.write(json.dumps(message) + "\n")
            sys.stdout.flush()

    # =========================================================================
    # Event emitters
    # =========================================================================

    def _emit_content_delta(self, text: str) -> None:
        """Emit streaming content chunk."""
        self._send_notification("content.delta", {"text": text})

    def _emit_content_done(self, full_text: str) -> None:
        """Emit content completion."""
        self._send_notification("content.done", {"full_text": full_text})

    def _emit_thinking_update(self, thought: str) -> None:
        """Emit agent thinking step."""
        self._send_notification("thinking.update", {"thought": thought})

    def _emit_tool_pending(
        self, tool_call_id: str, tool: str, args: dict
    ) -> None:
        """Emit tool call awaiting confirmation."""
        self._send_notification("tool.pending", {
            "tool_call_id": tool_call_id,
            "tool": tool,
            "arguments": args,
        })

    def _emit_tool_result(
        self, tool_call_id: str, success: bool, output: str
    ) -> None:
        """Emit tool execution result."""
        self._send_notification("tool.result", {
            "tool_call_id": tool_call_id,
            "success": success,
            "output": output,
        })

    def _emit_token_usage(
        self, prompt_tokens: int, completion_tokens: int, total_tokens: int
    ) -> None:
        """Emit token usage statistics."""
        self._send_notification("token.usage", {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": total_tokens,
        })

    def _emit_error(self, code: str, message: str) -> None:
        """Emit error notification."""
        self._send_notification("error", {"code": code, "message": message})

    # =========================================================================
    # Method handlers
    # =========================================================================

    def _handle_initialize(self, params: dict) -> dict:
        """Initialize the server with API credentials.

        Args:
            params: May contain "api_key" and "model".

        Returns:
            Server capabilities.
        """
        api_key = params.get("api_key") or get_api_key()
        if not api_key:
            raise ValueError("No API key configured")

        self.api = MistralAPI(api_key=api_key)
        self.model = params.get("model", self.model)

        return {
            "capabilities": {
                "streaming": True,
                "agent": True,
                "tools": True,
            },
            "version": "1.0.0",
        }

    def _handle_shutdown(self, params: dict) -> dict:
        """Shutdown the server."""
        self._shutdown_event.set()
        return {"status": "ok"}

    def _handle_chat(self, params: dict) -> dict:
        """Handle simple chat completion.

        Args:
            params: Contains "message" and optional "context_files".

        Returns:
            Chat response with content.
        """
        if not self.api:
            raise ValueError("Server not initialized")

        message = params.get("message")
        if not message:
            raise ValueError("Missing 'message' parameter")

        context_files = params.get("context_files", [])

        # Add context files
        for file_path in context_files:
            self.context.add_file(file_path)

        # Build messages with context
        messages = self.context.prepare_messages(message, model=self.model)

        # Calculate input tokens
        prompt_text = " ".join(m.get("content", "") for m in messages)
        prompt_tokens = count_tokens(prompt_text)

        # Stream response
        full_response = ""
        try:
            stream = self.api.chat(messages, model=self.model, stream=True)
            if isinstance(stream, list):
                # Error fallback
                full_response = stream[0] if stream else ""
                self._emit_content_delta(full_response)
            else:
                for chunk in stream:
                    full_response += chunk
                    self._emit_content_delta(chunk)
        except Exception as e:
            self._emit_error("chat_error", str(e))
            raise

        self._emit_content_done(full_response)

        # Update conversation history
        self.context.add_message("user", message)
        self.context.add_message("assistant", full_response)

        # Emit token usage
        completion_tokens = count_tokens(full_response)
        self._emit_token_usage(prompt_tokens, completion_tokens, prompt_tokens + completion_tokens)

        return {"content": full_response}

    def _handle_agent_run(self, params: dict) -> dict:
        """Run agent task.

        Args:
            params: Contains "task" and optional "context_files".

        Returns:
            Agent response.
        """
        if not self.api:
            raise ValueError("Server not initialized")

        task = params.get("task")
        if not task:
            raise ValueError("Missing 'task' parameter")

        context_files = params.get("context_files", [])
        auto_confirm = params.get("auto_confirm", False)

        # Create agent with custom callbacks
        config = AgentConfig(
            model=self.model,
            confirm_all=auto_confirm,
            auto_confirm_safe=True,
        )

        self.agent = Agent(api=self.api, config=config)

        # Add context files
        for file_path in context_files:
            self.agent.add_file(file_path)

        # Set up callbacks
        self.agent.on_thinking = lambda: self._emit_thinking_update("Processing...")
        self.agent.on_tool_call = self._on_agent_tool_call
        self.agent.on_tool_result = self._on_agent_tool_result
        self.agent.on_response = lambda content: self._emit_content_delta(content)

        # Run agent
        try:
            result = self.agent.run(task)
            self._emit_content_done(result)
            return {"content": result}
        except Exception as e:
            self._emit_error("agent_error", str(e))
            raise
        finally:
            self.agent = None

    def _on_agent_tool_call(self, tool_name: str, arguments: dict) -> None:
        """Handle agent tool call - may require confirmation.

        Args:
            tool_name: Name of the tool being called.
            arguments: Tool arguments.
        """
        tool_call_id = str(uuid.uuid4())

        # Check if tool requires confirmation
        if self.agent:
            tool = self.agent.tool_map.get(tool_name)
            if tool and tool.requires_confirmation:
                # Create pending confirmation
                pending = PendingConfirmation(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    arguments=arguments,
                )
                self.pending_confirmations[tool_call_id] = pending

                # Emit event and wait for confirmation
                self._emit_tool_pending(tool_call_id, tool_name, arguments)

                # Wait for confirmation (with timeout)
                if not pending.event.wait(timeout=300):  # 5 minute timeout
                    pending.approved = False

                del self.pending_confirmations[tool_call_id]

                if not pending.approved:
                    self.agent.cancel()
                    return

        self._emit_thinking_update(f"Running {tool_name}...")

    def _on_agent_tool_result(self, tool_name: str, result: ToolResult) -> None:
        """Handle agent tool result.

        Args:
            tool_name: Name of the tool that executed.
            result: Tool execution result.
        """
        self._emit_tool_result(
            tool_call_id="",  # We don't track individual IDs here
            success=result.success,
            output=result.output if result.success else result.error,
        )

    def _handle_agent_cancel(self, params: dict) -> dict:
        """Cancel running agent task."""
        if self.agent:
            self.agent.cancel()
        return {"status": "ok"}

    def _handle_agent_confirm(self, params: dict) -> dict:
        """Confirm or deny a pending tool call.

        Args:
            params: Contains "tool_call_id" and "approved".

        Returns:
            Confirmation status.
        """
        tool_call_id = params.get("tool_call_id")
        approved = params.get("approved", False)

        if not tool_call_id:
            raise ValueError("Missing 'tool_call_id' parameter")

        pending = self.pending_confirmations.get(tool_call_id)
        if not pending:
            raise ValueError(f"No pending confirmation for {tool_call_id}")

        pending.approved = approved
        pending.event.set()

        return {"status": "ok", "approved": approved}

    def _handle_context_add(self, params: dict) -> dict:
        """Add file to context.

        Args:
            params: Contains "file_path".

        Returns:
            Success status.
        """
        file_path = params.get("file_path")
        if not file_path:
            raise ValueError("Missing 'file_path' parameter")

        success, message = self.context.add_file(file_path)

        # Emit token usage update
        if success:
            total_tokens = sum(
                count_tokens(content) for content in self.context.files.values()
            )
            self._emit_token_usage(total_tokens, 0, total_tokens)

        return {"success": success, "message": message}

    def _handle_context_remove(self, params: dict) -> dict:
        """Remove file from context.

        Args:
            params: Contains "file_path".

        Returns:
            Success status.
        """
        file_path = params.get("file_path")
        if not file_path:
            raise ValueError("Missing 'file_path' parameter")

        success, message = self.context.remove_file(file_path)
        return {"success": success, "message": message}

    def _handle_context_list(self, params: dict) -> dict:
        """List context files.

        Returns:
            List of file paths and token counts.
        """
        files = []
        for path, content in self.context.files.items():
            files.append({
                "path": path,
                "tokens": count_tokens(content),
            })

        total_tokens = sum(f["tokens"] for f in files)

        return {
            "files": files,
            "total_tokens": total_tokens,
        }

    def _handle_context_clear(self, params: dict) -> dict:
        """Clear context files and/or history.

        Args:
            params: May contain "files" and/or "history" booleans.
        """
        clear_files = params.get("files", True)
        clear_history = params.get("history", True)

        if clear_files:
            self.context.files = {}
        if clear_history:
            self.context.messages = []

        return {"status": "ok"}

    def _handle_model_set(self, params: dict) -> dict:
        """Set the model to use.

        Args:
            params: Contains "model" name.
        """
        model = params.get("model")
        if not model:
            raise ValueError("Missing 'model' parameter")

        self.model = model
        return {"model": self.model}

    def _handle_model_get(self, params: dict) -> dict:
        """Get current model name."""
        return {"model": self.model}


def run_server() -> None:
    """Entry point to run the JSON-RPC server."""
    server = JSONRPCServer()
    server.run()
