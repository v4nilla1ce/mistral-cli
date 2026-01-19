"""AgentBench integration for mistral-cli."""

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional

from .api import MistralAPI
from .tools.shell import ShellTool

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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

    def step(self, observation: str) -> dict[str, Any]:
        """Advance the agent state with an observation from the environment."""
        
        # 1. Add observation to history
        # If this is the FIRST step (after system prompt), it's the user's task prompt.
        if len(self.messages) == 1:
            self.messages.append({"role": "user", "content": observation})
        else:
             # If we have history, the last message probably was a tool call (assistant).
             # We need to append the tool result (tool).
             
             last_msg = self.messages[-1]
        if last_msg["role"] == "assistant" and "tool_calls" in last_msg and last_msg["tool_calls"]:
                 # It was a tool call, so this observation is the tool output
                 # We assume the observation corresponds to the LAST tool call if multiple
                 # But typically AgentBench is single-threaded step-by-step
                 for tc in last_msg["tool_calls"]:
                     self.messages.append({
                         "role": "tool",
                         "content": observation,
                         "tool_call_id": tc["id"],
                         "name": tc["function"]["name"]
                     })
             else:
                 # Fallback: Just treat it as user message (e.g. feedback)
                 self.messages.append({"role": "user", "content": observation})
        
        return self.respond()

    def respond(self) -> dict[str, Any]:
        """Generate a response based on current message history."""
        # 2. Call API
        try:
             response = self.api.chat(
                 messages=self.messages,
                 model="mistral-large-latest", # Use capable model
                 tools=self.tools,
                 return_full_response=True
             )
             
             # Check for API error represented as ChatResponse with content but no raw
             if not response.raw and not response.tool_calls and not response.content:
                  return {"action": "echo 'Error: Empty response from API'"}
             
             # Append assistant response to history
             # We need to reconstruct the message dict from the ChatResponse
             # The MistralAPI returns a ChatResponse, but for history we need the raw dict or equivalent
             if response.raw:
                 asst_msg = response.raw["choices"][0]["message"]
             else:
                 # Reconstruct if raw is missing (mocking etc)
                 asst_msg = {"role": "assistant", "content": response.content}
                 if response.tool_calls:
                     asst_msg["tool_calls"] = [
                         {
                             "id": tc.id,
                             "type": "function",
                             "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}
                         }
                         for tc in response.tool_calls
                     ]

             self.messages.append(asst_msg)

             # 3. Handle Output
             if response.has_tool_calls:
                 # Extract first tool call
                 tc = response.tool_calls[0]
                 if tc.name == "execute":
                     cmd = tc.arguments.get("command", "")
                     return {"action": cmd}
                 else:
                     return {"action": f"echo 'Error: Unknown tool {tc.name}'"}
             else:
                 # Text response - treat as thought or generic output
                 content = response.content or ""
                 # Escape quotes for echo
                 safe_content = content.replace("'", "'\\''") 
                 return {"action": f"echo '{safe_content}'"}

        except Exception as e:
            logger.error(f"Error in step: {e}")
            return {"action": f"echo 'Error: {str(e)}'"}


# Global session instance
_session: Optional[AgentBenchSession] = None


class AgentBenchHandler(BaseHTTPRequestHandler):
    """HTTP Handler for AgentBench requests."""

    def do_POST(self):
        """Handle POST requests."""
        global _session
        
        if self.path == "/step":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
                if "messages" in data:
                    # STATELESS MODE: Client provides full history
                    messages = data["messages"]
                    if _session is None:
                        _session = AgentBenchSession()
                    
                    # Sync session messages with provided history
                    # We preserve the system prompt (first message) from our session
                    # and append/replace the rest with provided messages
                    
                    # Ensure provided messages don't duplicate the system prompt if client sent it
                    start_idx = 0
                    if messages and messages[0]["role"] == "system":
                        start_idx = 1
                    
                    # Update session state: System Prompt + Client History
                    _session.messages = [_session.messages[0]] + messages[start_idx:]
                    
                    # Now call step with empty observation because the observation is already in the history!
                    # BUT step() expects an observation to APPEND.
                    # We don't want to append anything. We just want to call the API.
                    
                    # Refactor step() or call internal logic?
                    # Let's create a new method 'respond()'
                    
                    result = _session.respond()
                    
                else:
                    # STATEFUL MODE: Legacy AgentBench
                    observation = data.get("observation") or data.get("prompt") or ""
                    
                    if _session is None:
                        _session = AgentBenchSession()
                    
                    result = _session.step(observation)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode('utf-8'))
                
            except Exception as e:
                logger.error(f"Error handling request: {e}")
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
                
        elif self.path == "/reset":
             _session = AgentBenchSession()
             self.send_response(200)
             self.end_headers()
             self.wfile.write(b'{"status": "reset"}')
        else:
            self.send_response(404)
            self.end_headers()


def run_agentbench_server(port: int = 5000):
    """Start the AgentBench server."""
    server_address = ('', port)
    httpd = HTTPServer(server_address, AgentBenchHandler)
    print(f"Starting AgentBench server on port {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()
