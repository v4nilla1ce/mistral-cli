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
        
        logger.info(f"Generating response for history length: {len(api_messages)}")
        
        # 2. Call API
        try:
             response = self.api.chat(
                 messages=api_messages,
                 model="mistral-large-latest",
                 tools=active_tools if active_tools else None,
                 return_full_response=True
             )
             
             if not response.raw and not response.tool_calls and not response.content:
                  logger.warning("Empty response from API")
                  return {"action": "echo 'Error: Empty response from API'"}
             
             if response.raw:
                 asst_msg = response.raw["choices"][0]["message"]
             else:
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
                 tc = response.tool_calls[0]
                 logger.info(f"Agent called tool: {tc.name}")
                 
                 # Dynamic action mapping:
                 # In OSWorld, often 'bash_action' takes 'script'
                 # In our ShellTool, 'execute' takes 'command'
                 # We need to return what the LLM produced, but maybe normalization is needed.
                 # AgentBench typically expects a flat "action" string for certain tasks.
                 
                 args = tc.arguments
                 if tc.name == "bash_action":
                     return {"action": args.get("script", "")}
                 elif tc.name == "execute":
                     return {"action": args.get("command", "")}
                 else:
                     # Generic fallback: return the raw arguments or a string representation
                     if "script" in args:
                         return {"action": args["script"]}
                     if "command" in args:
                         return {"action": args["command"]}
                     return {"action": f"echo 'Called tool {tc.name} with {args}'"}
             else:
                 content = response.content or ""
                 logger.info(f"Agent responded with text: {content[:50]}...")
                 safe_content = content.replace("'", "'\\''") 
                 return {"action": f"echo '{safe_content}'"}

        except Exception as e:
            logger.error(f"Error in respond: {e}", exc_info=True)
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
                tools = data.get("tools")
                
                if "messages" in data:
                    # STATELESS MODE
                    messages = data["messages"]
                    if _session is None:
                        _session = AgentBenchSession()
                    
                    start_idx = 0
                    if messages and messages[0]["role"] == "system":
                        start_idx = 1
                    
                    _session.messages = [_session.messages[0]] + messages[start_idx:]
                    result = _session.respond(tools=tools)
                    
                else:
                    # STATEFUL MODE
                    observation = data.get("observation") or data.get("prompt") or ""
                    if _session is None:
                        _session = AgentBenchSession()
                    result = _session.step(observation)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode('utf-8'))
                
            except Exception as e:
                logger.error(f"Error handling request: {e}", exc_info=True)
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
