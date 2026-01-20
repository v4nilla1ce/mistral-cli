"""AgentBench integration for mistral-cli."""

import json
import logging
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Optional

from .api import MistralAPI
from .tools.shell import ShellTool

# Configure logging to both file and stderr for visibility
# Use absolute path so log works regardless of working directory
# Path: src/mistral_cli/agentbench.py -> parent.parent.parent = project root
_log_path = Path(__file__).resolve().parent.parent.parent / 'agentbench_server.log'

# Create handlers with immediate flush
_file_handler = logging.FileHandler(str(_log_path), mode='w')
_file_handler.setLevel(logging.DEBUG)
_stream_handler = logging.StreamHandler(sys.stderr)
_stream_handler.setLevel(logging.DEBUG)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[_file_handler, _stream_handler]
)

# Force immediate writes
for handler in logging.root.handlers:
    if hasattr(handler, 'stream'):
        handler.stream.flush()

logger = logging.getLogger(__name__)
logger.info(f"AgentBench module loaded, logging to: {_log_path}")
sys.stderr.flush()

def _heartbeat_loop():
    """Periodic log to prove server is alive."""
    import time
    while True:
        try:
            logger.debug("--- HEARTBEAT: Agent Server is alive ---")
            sys.stderr.flush()
        except:
            pass
        time.sleep(60)

import threading
_heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
_heartbeat_thread.start()


class AgentBenchSession:
    """Manages a single AgentBench session."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the session."""
        self.api = MistralAPI(api_key=api_key)
        self.messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are an autonomous AI agent capable of using a shell. "
                    "You are being evaluated in the AgentBench benchmark. "
                    "You will receive observations from the environment and must "
                    "respond with the appropriate shell command to execute using the `execute` function. "
                    "Do not ask for confirmation. Do not apologize. "
                    "If you are stuck, try to gather more information."
                ),
            }
        ]
        # We only expose the shell tool
        self._shell_tool = ShellTool()
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "execute",
                    "description": self._shell_tool.description,
                    "parameters": self._shell_tool.parameters,
                },
            }
        ]

    def _translate_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Translate roles for Mistral API compatibility."""
        translated = []
        for msg in messages:
            m = msg.copy()
            if m["role"] == "agent":
                m["role"] = "assistant"
                logger.info("Translating role 'agent' -> 'assistant'")
            translated.append(m)
        return translated

    def step(self, observation: str) -> dict[str, Any]:
        """Advance the agent state with an observation from the environment."""
        
        # 1. Add observation to history
        if len(self.messages) == 1:
            self.messages.append({"role": "user", "content": observation})
        else:
             last_msg = self.messages[-1]
             if last_msg["role"] == "assistant" and "tool_calls" in last_msg and last_msg["tool_calls"]:
                 for tc in last_msg["tool_calls"]:
                     self.messages.append({
                         "role": "tool",
                         "content": observation,
                         "tool_call_id": tc["id"],
                         "name": tc["function"]["name"]
                     })
             else:
                 self.messages.append({"role": "user", "content": observation})
        
        return self.respond()

    def respond(self, tools: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        """Generate a response based on current message history."""
        # Use provided tools or fall back to session tools
        active_tools = tools if tools is not None else self.tools

        # Translate messages for Mistral (role mapping)
        api_messages = self._translate_messages(self.messages)

        print(f"[AGENT] Calling API: {len(api_messages)} msgs, {len(active_tools) if active_tools else 0} tools", file=sys.stderr, flush=True)
        logger.info(f"Calling Mistral API with {len(api_messages)} messages, {len(active_tools) if active_tools else 0} tools")
        logger.debug(f"First message role: {api_messages[0]['role'] if api_messages else 'none'}")

        # Call API
        try:
            # Safeguard: Mistral API requires the last message to be User or Tool.
            if api_messages and api_messages[-1]["role"] == "assistant":
                logger.warning("Last message is from assistant. Skipping API call to avoid 400 error.")
                return {"role": "assistant", "content": ""}

            print(f"[AGENT] Making API call to Mistral...", file=sys.stderr, flush=True)
            logger.debug(f"Making API call with {len(api_messages)} messages and {len(active_tools) if active_tools else 0} tools...")
            
            # Explicitly log the roles in history for debugging
            roles = [m['role'] for m in api_messages]
            logger.debug(f"Message role sequence: {roles}")

            response = self.api.chat(
                messages=api_messages,
                model="mistral-large-latest",
                tools=active_tools if active_tools else None,
                return_full_response=True
            )
            print(f"[AGENT] API response received", file=sys.stderr, flush=True)
            logger.info(f"API response received: content={bool(response.content)}, tool_calls={len(response.tool_calls) if response.tool_calls else 0}")

            if not response.raw and not response.tool_calls and not response.content:
                logger.warning("Empty response from API")
                return {"role": "assistant", "content": "Error: Empty response from API"}

            if response.raw:
                asst_msg = response.raw["choices"][0]["message"]
                logger.debug(f"Using raw response message")
            else:
                asst_msg = {"role": "assistant", "content": response.content or ""}
                if response.tool_calls:
                    asst_msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}
                        }
                        for tc in response.tool_calls
                    ]
                    logger.debug(f"Added {len(response.tool_calls)} tool calls to response")

            self.messages.append(asst_msg)
            logger.info(f"Response ready: role={asst_msg.get('role')}, has_tool_calls={'tool_calls' in asst_msg}")
            return asst_msg

        except Exception as e:
            print(f"[AGENT] ERROR in respond: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc()
            logger.error(f"Error in respond: {e}", exc_info=True)
            return {"role": "assistant", "content": f"Error: {str(e)}"}


# Global session instance
_session: Optional[AgentBenchSession] = None


class AgentBenchHandler(BaseHTTPRequestHandler):
    """HTTP Handler for AgentBench requests."""

    def do_POST(self):
        """Handle POST requests."""
        global _session

        print(f"[AGENT] POST {self.path}", file=sys.stderr, flush=True)
        logger.info(f"POST request to {self.path}")

        if self.path == "/step":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)

            try:
                raw_data = post_data.decode('utf-8')
                print(f"[AGENT] Request received, len={len(raw_data)}", file=sys.stderr, flush=True)
                logger.info(f"RAW REQUEST BODY: {raw_data[:2000]}")
                data = json.loads(raw_data)
                tools = data.get("tools")
                print(f"[AGENT] Tools: {len(tools) if tools else 0}", file=sys.stderr, flush=True)
                logger.info(f"Received tools: {len(tools) if tools else 0} tools")
                if tools:
                    logger.debug(f"Tool names: {[t.get('function', {}).get('name', t.get('name', 'unknown')) for t in tools]}")

                if "messages" in data:
                    # STATELESS MODE - use their messages directly (or merge deltas)
                    messages = data["messages"]
                    logger.info(f"STATELESS MODE: Received {len(messages)} messages")
                    for i, m in enumerate(messages):
                        logger.info(f"  Message {i}: role={m.get('role')}, content_len={len(str(m.get('content', '')))}")

                    if _session is None:
                        _session = AgentBenchSession()
                        # If starting fresh, take the whole batch
                        _session.messages = messages.copy()
                        logger.debug("Initialized new session with messages")
                    else:
                        # Logic to merge deltas vs full update
                        # Heuristic: If first message is 'system', it's a full history/new task -> Replace
                        if messages and messages[0].get('role') == 'system':
                            _session.messages = messages.copy()
                            logger.info("Received System message: Replacing full history")
                        else:
                            # It is likely a delta (e.g. [Assistant, ToolResult])
                            # We might have generated the Assistant message locally in the previous turn.
                            # AgentBench (Worker) returns history slice which includes that Assistant message.
                            # So we should skip it if it matches our last message to avoid duplication.
                            
                            start_idx = 0
                            if messages and messages[0].get('role') == 'assistant':
                                last_msg = _session.messages[-1] if _session.messages else None
                                if last_msg and last_msg.get('role') == 'assistant':
                                    logger.info("Skipping echoed Assistant message in delta")
                                    start_idx = 1
                            
                            if start_idx < len(messages):
                                to_append = messages[start_idx:]
                                _session.messages.extend(to_append)
                                logger.info(f"Appended {len(to_append)} delta messages")
                            else:
                                logger.info("No new messages to append from delta")

                    # Persist tools if provided
                    if tools:
                        _session.tools = tools
                        logger.info(f"Updated session tools: {len(tools)} tools")

                    logger.debug(f"Current session messages count: {len(_session.messages)}")
                    logger.debug(f"First role: {_session.messages[0]['role'] if _session.messages else 'none'}")
                    logger.debug(f"Last role: {_session.messages[-1]['role'] if _session.messages else 'none'}")

                    # Use session tools if request doesn't provide them
                    result = _session.respond(tools=tools if tools else _session.tools)
                    logger.info(f"Response generated: {str(result)[:200]}...")
                    logger.info(f"Response generated: {str(result)[:200]}...")

                else:
                    # STATEFUL MODE
                    observation = data.get("observation") or data.get("prompt") or ""
                    logger.info(f"STATEFUL MODE: observation length={len(observation)}")
                    if _session is None:
                        _session = AgentBenchSession()
                    result = _session.step(observation)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response_json = json.dumps(result)
                print(f"[AGENT] Sending response: {response_json[:300]}...", file=sys.stderr, flush=True)
                logger.info(f"FULL RESPONSE: {response_json}")
                self.wfile.write(response_json.encode('utf-8'))
                print(f"[AGENT] Response sent successfully", file=sys.stderr, flush=True)

            except Exception as e:
                print(f"[AGENT] EXCEPTION in handler: {e}", file=sys.stderr, flush=True)
                import traceback
                traceback.print_exc()
                logger.error(f"Error handling request: {e}", exc_info=True)
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
                
        elif self.path == "/reset":
            logger.info("Received /reset request")
            _session = AgentBenchSession()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status": "reset"}')
            logger.info("Session reset complete")
        else:
            self.send_response(404)
            self.end_headers()


def run_agentbench_server(port: int = 5000):
    """Start the AgentBench server."""
    logger.info(f"=== AgentBench Server Starting ===")
    logger.info(f"Log file: {_log_path}")
    logger.info(f"Port: {port}")

    server_address = ('', port)
    httpd = HTTPServer(server_address, AgentBenchHandler)

    print(f"Starting AgentBench server on port {port}...")
    print(f"Log file: {_log_path}")
    logger.info(f"Server ready and listening on port {port}")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopping (KeyboardInterrupt)")
        print("\nStopping server...")
        httpd.server_close()
