# Running AgentBench with Mistral CLI

This guide explains how to evaluate `mistral-cli` using the AgentBench framework.

## Prerequisites

1.  **Mistral CLI**: Installed and configured with a valid API key.
2.  **AgentBench**: Cloned and set up (requires Docker/Linux for OS tasks).
    *   Repository: [THUDM/AgentBench](https://github.com/THUDM/AgentBench)

## Step 1: Start the Mistral Agent Server

First, start the `mistral-cli` in "Headless Benchmark Mode". This opens an HTTP server that AgentBench will communicate with.

```powershell
# In your mistral-cli directory
mistral agentbench --port 5000
```

You should see:
> Starting AgentBench server on port 5000...

## Step 2: Configure AgentBench (On the Benchmark Machine)

In your **AgentBench repository**, you need to configure an agent to point to your running server.

1.  Create a new config file `configs/agents/mistral_http.yaml`:

```yaml
id: mistral_http
name: MistralHTTP
module: agentbench.agents.http_agent.HttpAgent
parameters:
  url: "http://host.docker.internal:5000/step"  # Use host.docker.internal if running AgentBench in Docker
  # url: "http://localhost:5000/step"           # Use localhost if running locally on the same machine
```

*Note: If `mistral-cli` is on Windows and AgentBench is in WSL or Docker, use valid networking to reach the Windows host (often `host.docker.internal`).*

## Step 3: Run the Benchmark

Run AgentBench pointing to your new agent config.

```bash
# Example for running the OSWorld task
python verify_agent.py --agent mistral_http --task os_fs
```

(Note: The exact command depends on the specific version/branch of AgentBench you are using. Refer to their `README.md` for the `assigner` or `eval.py` usage).

## Troubleshooting

- **Server not receiving requests?**
    - Check firewall settings on Windows (allow Python to accept connections).
    - detailed logging is printed to the console where `mistral agentbench` is running.
- **Agent stuck?**
    - The server logs will show `Error in step` if something crashes internally.
    - Ensure your `MISTRAL_API_KEY` is valid.
