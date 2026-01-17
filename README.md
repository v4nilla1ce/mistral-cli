# Mistral CLI

A command-line interface that uses Mistral AI to inspect your code, analyze bugs, review quality, and automatically suggest fixes.

## Features

- **Automated Bug Fixing**: Analyzes error descriptions and suggests code fixes with streaming output.
- **Code Review**: Get detailed quality assessments without modifying files (`mistral review`).
- **Interactive Chat**: Conversational interface with streaming responses and file context management.
- **Agentic Mode**: Let the AI autonomously execute commands, read/write files, and accomplish complex tasks with human-in-the-loop confirmation.
- **Self-Correction**: Agent detects errors, analyzes exit codes, and automatically adapts commands (e.g., tries `python` when `python3` fails on Windows).
- **Active Memory**: Remembers user preferences (`~/.local/share/mistral-cli/memory.json`) and project-specific facts (`.mistral/memory.json`).
- **Autonomous Verification** (NEW in v0.8): Agent runs syntax checks and local tests via the `Critic` module to self-correct.
- **Benchmark Mode** (NEW in v0.8): Data-driven evaluation using "Golden Tasks" (`mistral benchmark`).
- **Watch Mode**: Proactively monitor commands (`mistral watch "pytest"`) and auto-fix failures.
- **Planning Mode**: Agent creates step-by-step plans for complex tasks.
- **Semantic Search**: Index your codebase for semantic similarity search (`mistral index`).
- **MCP Support**: Connect to Model Context Protocol servers for extended tool capabilities.
- **Multi-Language Support**: Works with Python, JavaScript, TypeScript, Go, Rust, and more.
- **Global Installation**: Install once with `pipx`, run from anywhere.
- **Safety First**:
  - **Backups**: Automatically creates backups before applying any changes.
  - **Undo**: Quickly revert changes with `/undo`.
  - **Dry Run**: Preview changes without modifying files (`--dry-run`).
  - **Diff Preview**: See exactly what will change before applying (`/diff`).
  - **Confirmation**: Always asks for permission before writing to disk.
  - **Circuit Breaker**: Stops after repeated failures to prevent infinite loops.
- **Smart Context**:
  - **Token Management**: Estimates token usage and warns at 80%/90% capacity.
  - **Glob Patterns**: Add multiple files with `/add src/**/*.py`.
  - **Directory Tree**: Visualize project structure with `/tree`.
  - **Profiles**: Save and load conversation contexts with `/profile`.
- **Session Persistence**: Save and resume chat sessions with `/save` and `/load`.
- **Shell Completions**: Tab completion for bash, zsh, fish, and PowerShell.
- **CI/CD Aware**: Automatically adjusts output for non-interactive environments.
- **Cross-Platform**: Works on Windows, Linux, and macOS with XDG-compliant config paths.

## Installation

### Option 1: Install with pipx (Recommended)

```bash
pipx install git+https://github.com/v4nilla1ce/mistral-cli.git
```

This installs `mistral` globally in an isolated environment.

### Option 2: Install from source

```bash
git clone https://github.com/v4nilla1ce/mistral-cli.git
cd mistral-cli
pip install -e .
```

### Option 3: Development setup

```bash
git clone https://github.com/v4nilla1ce/mistral-cli.git
cd mistral-cli
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Updating

### Update with pipx

```bash
pipx upgrade mistral-cli
```

Or reinstall to get the latest version:

```bash
pipx uninstall mistral-cli
pipx install git+https://github.com/v4nilla1ce/mistral-cli.git
```

### Update from source

```bash
cd mistral-cli
git pull origin main
pip install -e .
```

## Configuration

### Quick Setup (Recommended)

Run the interactive setup:

```bash
mistral config setup
```

This saves your API key to the global config file.

### View Current Configuration

```bash
mistral config show
```

Shows config file location, log directory, and API key source.

### Manual Configuration

You can also configure via environment variable or `.env` file:

```bash
# Environment variable
export MISTRAL_API_KEY=your_api_key_here

# Or create a .env file in your project
echo "MISTRAL_API_KEY=your_api_key_here" > .env
```

**Config Precedence** (highest to lowest):
1. CLI argument (`--api-key`)
2. Environment variable (`MISTRAL_API_KEY`)
3. Global config file
4. Local `.env` file

### Config Paths

| Platform | Config File | Logs & Backups |
|----------|-------------|----------------|
| Windows | `%LOCALAPPDATA%\mistral-cli\config.json` | `%LOCALAPPDATA%\mistral-cli\` |
| Linux/Mac | `~/.config/mistral-cli/config.json` | `~/.local/share/mistral-cli/` |

## Usage

### Agentic Mode (NEW)

The agent can autonomously execute shell commands, read/write files, search code, and accomplish complex tasks:

```bash
mistral agent
```

Simply describe what you want to do:
- "List all Python files in src/"
- "Find all TODO comments in the codebase"
- "Create a new test file for the utils module"
- "Run the tests and fix any failures"

**Options:**
- `--model <name>` - Use a specific model (default: mistral-small)
- `--confirm-all` - Skip all confirmations (trusted mode, use with caution)
- `--auto-confirm-safe` - Auto-confirm read-only commands (ls, git status, etc.)
- `--max-iterations <n>` - Maximum agent iterations per request (default: 10)

**Self-Correction (v0.4):**

The agent is now context-aware and can recover from common errors:
- Knows its OS, shell, and available tools (python, node, git, etc.)
- Detects exit codes (e.g., 9009 on Windows = command not found)
- Analyzes error patterns and suggests fixes (e.g., "Try `python` instead of `python3`")
- Circuit breaker stops after 3 consecutive failures to prevent infinite loops

**Available Tools:**

| Tool | Description | Confirmation |
|------|-------------|--------------|
| `read_file` | Read file contents | No |
| `list_files` | List directory contents with glob support | No |
| `search_files` | Search for text/patterns in files | No |
| `semantic_search` | Search code by meaning (requires `[rag]`) | No |
| `project_context` | Analyze project structure | No |
| `write_file` | Create or overwrite files | **Yes** |
| `edit_file` | Modify specific parts of files | **Yes** |
| `shell` | Execute shell commands | **Yes** |
| MCP tools | Tools from connected MCP servers | **Yes** |

**Agent Slash Commands:**

| Command | Description |
|---------|-------------|
| `/tools` | List available tools |
| `/plan` | Enable planning mode for complex tasks |
| `/add [file]` | Add file to context |
| `/remove <file>` | Remove file from context |
| `/list` | List context files |
| `/model [name]` | Show or switch model |
| `/undo [file]` | Undo last file change |
| `/clear` | Clear context and history |
| `/help` | Show all commands |
| `/exit` | Quit |

### Interactive Chat

```bash
mistral chat
```

**Slash Commands:**

| Command | Description |
|---------|-------------|
| `/add [file\|glob]` | Add file(s) to context (no arg = file picker) |
| `/remove <file>` | Remove file from context |
| `/list` | List context files |
| `/tree [path]` | Show directory tree |
| `/apply [--diff] [--dry-run] [file]` | Apply last AI code to file |
| `/create [--dry-run] <file>` | Create new file from last AI response |
| `/diff [file]` | Preview diff of last AI response |
| `/undo [file]` | Undo last change (restore from backup) |
| `/backups` | List recent backups |
| `/model [name]` | Show or switch model |
| `/system [prompt\|--clear]` | Set or view custom system prompt |
| `/profile [save\|load\|delete] <name>` | Manage conversation profiles |
| `/save <name>` | Save current session |
| `/load <name>` | Load a saved session |
| `/sessions` | List saved sessions |
| `/clear [history\|files]` | Clear history, files, or both |
| `/help` | Show all commands |
| `/exit` | Quit the chat |

### Fix a Bug

```bash
mistral fix app.py "TypeError in calculate_total function"
```

Options:
- `--dry-run` - Preview without applying
- `--model <name>` - Use a specific model
- `--no-stream` - Disable streaming output

### Review Code

Get a quality assessment without modifying files:

```bash
mistral review app.py
```

Options:
- `--model <name>` - Use a specific model

### Dry Run (Safe Mode)

Preview the fix without applying it:

```bash
mistral fix app.py "IndexError in list processing" --dry-run
```

### Semantic Search (Index)

Index your codebase for semantic code search:

```bash
# Index current directory
mistral index

# Index a specific path
mistral index ./src

# Rebuild the index
mistral index --rebuild
```

Requires the `[rag]` optional dependency:

```bash
pipx install 'mistral-cli[rag]' --force
# or
pip install -e ".[rag]"
```

### MCP Servers

Connect to Model Context Protocol servers for extended capabilities:

```bash
# List configured servers
mistral mcp list

# Add an MCP server (stdio transport)
mistral mcp add filesystem -c npx -c @anthropic/mcp-server-filesystem -c /tmp

# Test connection
mistral mcp test filesystem

# Remove a server
mistral mcp remove filesystem
```

MCP tools appear automatically in agent mode alongside built-in tools.

### Shell Completions

Enable tab completion for your shell:

```bash
# Show instructions
mistral completions bash

# Auto-install
mistral completions bash --install
mistral completions zsh --install
mistral completions fish --install
mistral completions powershell --install
```

### Watch Mode (NEW)

Proactively monitor a command and auto-fix validation failures:

```bash
# Run pytest and auto-fix if it fails
mistral watch "pytest"

# Run a script and fix errors
mistral watch "python script.py"
```

The agent will stream the output, detect failure exit codes, analyze the error, and apply fixes until the command passes (or max retries reached).

### Benchmark Mode (NEW)

Evaluate the agent's performance against a dataset of Golden Tasks:

```bash
# Run the default benchmark suite
mistral benchmark

# Use a custom task file
mistral benchmark --tasks my_tasks.json
```

This runs the agent against defined tasks (file creation, refactoring, etc.) in isolated environments and reports success/failure rates.


### Version

```bash
mistral --version
```

## Examples

### Add multiple files with glob patterns

```bash
# In chat mode:
/add src/**/*.py
/add tests/*.py
```

### Use conversation profiles

```bash
# Save current context (files, model, system prompt) as a profile
/profile save my-project

# Load it later
/profile load my-project
```

### Review and then fix

```bash
# First, review the code
mistral review src/utils.py

# Then fix specific issues
mistral fix src/utils.py "handle edge case when list is empty"
```

## Logs

Logs are stored in the global data directory:
- **Windows**: `%LOCALAPPDATA%\mistral-cli\logs\mistral-cli.log`
- **Linux/Mac**: `~/.local/share/mistral-cli/logs/mistral-cli.log`

## Development

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=mistral_cli

# Run linters
black src/
isort src/
flake8 src/

# Type checking
mypy src/
```

## License

MIT
