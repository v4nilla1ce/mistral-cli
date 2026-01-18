# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Mistral CLI (v0.8.0) is a Python CLI tool that uses Mistral AI for code analysis, bug fixing, code review, and autonomous task execution. It features an agentic mode with tool execution, planning, self-correction, and MCP (Model Context Protocol) support.

## Commands

```bash
# Development setup
pip install -e ".[dev]"
pre-commit install

# Run tests
pytest                           # All tests
pytest --cov=mistral_cli         # With coverage
pytest tests/test_agent.py       # Single file

# Linting & formatting
black src/ && isort src/         # Format code
flake8 src/                      # Lint
mypy src/                        # Type check

# CLI usage
mistral fix <file> "error"       # One-shot bug fix
mistral chat                     # Interactive chat
mistral agent                    # Agentic mode with tools
mistral review <file>            # Code review (no modifications)
mistral watch "pytest"           # Auto-fix on failure
mistral benchmark                # Run Golden Tasks evaluation
mistral index                    # Build semantic search index
mistral mcp list                 # Manage MCP servers
mistral config setup             # Configure API key
```

## Architecture

```
src/mistral_cli/
├── cli.py           # Entry point (Click commands, REPL loops)
├── api.py           # Mistral API client (streaming, tool calling)
├── config.py        # XDG-compliant config (Windows: %LOCALAPPDATA%, Unix: ~/.config/)
├── context.py       # Prompt building, ConversationContext, SystemEnvironment
├── tokens.py        # Token counting via mistral-common tokenizer
├── backup.py        # Backup indexing for /undo support
├── agent.py         # Agent loop with planning, MCP, circuit breaker
├── memory.py        # Active Memory (global + project-scoped)
├── critic.py        # Autonomous verification (syntax checks, test execution)
├── benchmark.py     # Golden Tasks benchmark runner
├── knowledge.py     # Semantic search with embeddings (optional [rag] dependency)
├── mcp_client.py    # MCP server client (stdio/SSE transports)
└── tools/
    ├── __init__.py  # Tool registry and factory
    ├── base.py      # Tool ABC, ToolResult, MCPToolWrapper
    ├── files.py     # ReadFile, WriteFile, EditFile, ListFiles
    ├── shell.py     # ShellTool with SmartShell (OS detection, error hints)
    ├── project.py   # SearchFiles, ProjectContext, FindPattern
    ├── semantic.py  # SemanticSearchTool
    ├── memory.py    # UpdateMemoryTool
    └── critic.py    # CriticTool
```

### Key Data Flows

1. **Fix command**: `cli.py` → `context.build_prompt()` → `tokens.count_tokens()` → `MistralAPI.chat()` → `apply_fix()`
2. **Agent mode**: `Agent.run()` → tool loop → `MistralAPI.chat(tools=...)` → tool execution → Critic verification → memory update

### Core Classes

- **`MistralAPI`** (`api.py`): HTTP client supporting streaming and tool calling. Returns `ChatResponse` with `tool_calls` list.
- **`Agent`** (`agent.py`): Orchestrates agentic loop with planning support, circuit breaker (max 3 consecutive failures), and MCP tool integration.
- **`Tool`** (`tools/base.py`): Abstract base class. All tools return `ToolResult(success, output, error, hint)`.
- **`ConversationContext`** (`context.py`): Manages chat state with files dict and messages list. Includes `SystemEnvironment` for OS detection.
- **`MemoryManager`** (`memory.py`): Hierarchical memory - global (`~/.local/share/mistral-cli/memory.json`) and project (`.mistral/memory.json`).
- **`Critic`** (`critic.py`): Runs syntax checks and tests after file writes for self-correction.

### Tool Confirmation Rules

Tools requiring user confirmation before execution:
- `write_file`, `edit_file` - File modifications (creates backups)
- `shell` - Command execution
- MCP tools - External server tools

Read-only tools execute without confirmation: `read_file`, `list_files`, `search_files`, `semantic_search`, `project_context`

### Self-Correction Flow

On tool failure, the agent:
1. Tracks consecutive/total failures
2. Injects `[HINT]` system message with error analysis (exit codes, stderr patterns)
3. Checks circuit breaker thresholds
4. Model retries with awareness of failure context

## Configuration

API key precedence (highest to lowest):
1. CLI argument `--api-key`
2. Environment variable `MISTRAL_API_KEY`
3. Global config file
4. Local `.env` file

Config paths:
- Windows: `%LOCALAPPDATA%\mistral-cli\`
- Linux/Mac: `~/.config/mistral-cli/` (config), `~/.local/share/mistral-cli/` (data)

## Testing

- Tests in `tests/` use pytest with Click's `CliRunner`
- Golden Tasks benchmark dataset in `tests/golden_tasks.json` (100 tasks)
- Mock `MistralAPI` and file operations in tests

## Adding New Tools

1. Create class in `tools/` inheriting from `Tool`
2. Implement `name`, `description`, `parameters` (JSON Schema), `execute()`
3. Set `requires_confirmation = True` for dangerous operations
4. Register in `tools/__init__.py` via `get_all_tools()`
5. Add tests in `tests/test_tools.py`
