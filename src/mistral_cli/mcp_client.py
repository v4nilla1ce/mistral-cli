"""MCP (Model Context Protocol) client implementation."""

import json
import logging
import os
import subprocess
import threading
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Any, Optional

from .tools.base import MCPToolWrapper, Tool, ToolResult

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""

    name: str
    transport: str  # "stdio" or "sse"
    command: Optional[list[str]] = None  # For stdio transport
    url: Optional[str] = None  # For SSE transport
    env: Optional[dict[str, str]] = None  # Additional environment variables
    timeout: int = 30  # Connection/request timeout in seconds


@dataclass
class MCPClient:
    """Client for communicating with an MCP server."""

    config: MCPServerConfig
    _process: Optional[subprocess.Popen] = field(default=None, repr=False)
    _tools: list[dict] = field(default_factory=list, repr=False)
    _request_id: int = field(default=0, repr=False)
    _response_queue: Queue = field(default_factory=Queue, repr=False)
    _reader_thread: Optional[threading.Thread] = field(default=None, repr=False)
    _connected: bool = field(default=False, repr=False)

    def connect(self) -> bool:
        """Connect to the MCP server.

        Returns:
            True if connection successful, False otherwise.
        """
        if self.config.transport == "stdio":
            return self._connect_stdio()
        elif self.config.transport == "sse":
            return self._connect_sse()
        return False

    def _connect_stdio(self) -> bool:
        """Connect via stdio transport."""
        if not self.config.command:
            logger.error("No command specified for stdio transport")
            return False

        try:
            # Expand environment variables in command
            env = os.environ.copy()
            if self.config.env:
                for key, value in self.config.env.items():
                    env[key] = os.path.expandvars(value)

            self._process = subprocess.Popen(
                self.config.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1,
            )

            # Start reader thread
            self._reader_thread = threading.Thread(
                target=self._read_responses, daemon=True
            )
            self._reader_thread.start()

            # Initialize connection (MCP handshake)
            response = self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "mistral-cli", "version": "0.4.0"},
                },
            )

            if response and response.get("capabilities") is not None:
                # Send initialized notification
                self._send_notification("notifications/initialized", {})

                # Fetch available tools
                tools_response = self._send_request("tools/list", {})
                if tools_response and "tools" in tools_response:
                    self._tools = tools_response["tools"]
                    self._connected = True
                    logger.info(
                        f"Connected to MCP server '{self.config.name}' "
                        f"with {len(self._tools)} tools"
                    )
                    return True

        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            self.disconnect()

        return False

    def _connect_sse(self) -> bool:
        """Connect via HTTP SSE transport.

        Note: SSE transport is not yet implemented.
        """
        logger.warning("SSE transport not yet implemented")
        return False

    def _read_responses(self) -> None:
        """Background thread to read responses from server."""
        if not self._process or not self._process.stdout:
            return

        try:
            for line in self._process.stdout:
                line = line.strip()
                if line:
                    try:
                        response = json.loads(line)
                        self._response_queue.put(response)
                    except json.JSONDecodeError:
                        logger.debug(f"Non-JSON line from MCP server: {line}")
        except Exception as e:
            logger.debug(f"Reader thread ended: {e}")

    def _send_request(self, method: str, params: dict) -> Optional[dict]:
        """Send a JSON-RPC request to the server.

        Args:
            method: The RPC method name.
            params: Method parameters.

        Returns:
            The result dict if successful, None otherwise.
        """
        if not self._process or not self._process.stdin:
            return None

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        try:
            self._process.stdin.write(json.dumps(request) + "\n")
            self._process.stdin.flush()

            # Wait for response with matching ID
            start_id = self._request_id
            while True:
                try:
                    response = self._response_queue.get(timeout=self.config.timeout)
                    if response.get("id") == start_id:
                        if "error" in response:
                            logger.error(f"MCP error: {response['error']}")
                            return None
                        return response.get("result")
                    # Put back non-matching responses (notifications, etc.)
                    # In a more robust implementation, we'd handle these separately
                except Empty:
                    logger.error(f"Timeout waiting for MCP response to {method}")
                    return None
        except Exception as e:
            logger.error(f"Failed to send MCP request: {e}")
            return None

    def _send_notification(self, method: str, params: dict) -> None:
        """Send a JSON-RPC notification (no response expected).

        Args:
            method: The notification method name.
            params: Notification parameters.
        """
        if not self._process or not self._process.stdin:
            return

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        try:
            self._process.stdin.write(json.dumps(notification) + "\n")
            self._process.stdin.flush()
        except Exception as e:
            logger.debug(f"Failed to send notification: {e}")

    def call_tool(self, name: str, arguments: dict) -> ToolResult:
        """Call a tool on the MCP server.

        Args:
            name: Tool name.
            arguments: Tool arguments.

        Returns:
            ToolResult with the tool output or error.
        """
        if not self._connected:
            return ToolResult(False, "", "MCP server not connected")

        response = self._send_request(
            "tools/call",
            {
                "name": name,
                "arguments": arguments,
            },
        )

        if response is None:
            return ToolResult(False, "", "MCP server did not respond")

        # Check for error in response
        if response.get("isError"):
            content = response.get("content", [])
            error_text = (
                content[0].get("text", "Unknown error")
                if content and isinstance(content, list)
                else "Unknown error"
            )
            return ToolResult(False, "", error_text)

        # Extract text content from response
        content = response.get("content", [])
        if isinstance(content, list):
            output_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    output_parts.append(item.get("text", ""))
            output = "\n".join(output_parts)
        else:
            output = str(content)

        return ToolResult(True, output)

    def get_tools(self) -> list[Tool]:
        """Get Tool instances for all server tools.

        Returns:
            List of MCPToolWrapper instances.
        """
        tools = []
        for tool_schema in self._tools:
            wrapper = MCPToolWrapper(
                schema=tool_schema,
                executor=self.call_tool,
                server_name=self.config.name,
            )
            tools.append(wrapper)
        return tools

    def get_tool_names(self) -> list[str]:
        """Get names of all available tools.

        Returns:
            List of tool names.
        """
        return [t.get("name", "unknown") for t in self._tools]

    def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        self._connected = False

        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

        self._tools = []

    @property
    def is_connected(self) -> bool:
        """Check if connected to the server."""
        return self._connected


class MCPManager:
    """Manages multiple MCP server connections."""

    def __init__(self):
        """Initialize the MCP manager."""
        self.clients: dict[str, MCPClient] = {}

    def add_server(self, config: MCPServerConfig) -> bool:
        """Add and connect to an MCP server.

        Args:
            config: Server configuration.

        Returns:
            True if connection successful.
        """
        if config.name in self.clients:
            logger.warning(f"Server '{config.name}' already connected")
            return True

        client = MCPClient(config=config)
        if client.connect():
            self.clients[config.name] = client
            return True
        return False

    def remove_server(self, name: str) -> bool:
        """Disconnect and remove an MCP server.

        Args:
            name: Server name.

        Returns:
            True if server was removed.
        """
        if name in self.clients:
            self.clients[name].disconnect()
            del self.clients[name]
            return True
        return False

    def get_all_tools(self) -> list[Tool]:
        """Get all tools from all connected servers.

        Returns:
            Combined list of tools from all servers.
        """
        tools = []
        for client in self.clients.values():
            tools.extend(client.get_tools())
        return tools

    def get_server_names(self) -> list[str]:
        """Get names of all connected servers.

        Returns:
            List of server names.
        """
        return list(self.clients.keys())

    def disconnect_all(self) -> None:
        """Disconnect from all servers."""
        for client in self.clients.values():
            client.disconnect()
        self.clients.clear()

    def __del__(self):
        """Clean up connections on deletion."""
        self.disconnect_all()
