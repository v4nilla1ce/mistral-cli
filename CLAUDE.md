# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Mistral CLI is a Python command-line tool that uses Mistral AI to analyze Python code, identify bugs, and suggest fixes. It features both a one-shot `fix` command and an interactive `chat` mode with file context management.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the fix command (one-shot bug analysis)
python main.py fix <file.py> "error description" --dry-run

# Run interactive chat mode
python main.py chat --model mistral-small
```

## Architecture

The codebase follows a simple 4-module architecture:

```
main.py          → CLI entry point (Click + Rich), REPL loop, apply_fix logic
context.py       → Prompt building, ConversationContext class for chat state
mistral_api.py   → HTTP client for Mistral API (streaming and non-streaming)
token_utils.py   → Token counting via mistral-common tokenizer
```

### Data Flow

1. **Fix command**: `main.py` → `context.build_prompt()` → `token_utils.count_tokens()` → `MistralAPI.chat()` → `apply_fix()`
2. **Chat mode**: `main.py` REPL → `ConversationContext.prepare_messages()` → `MistralAPI.chat(stream=True)` → Rich Live rendering

### Key Classes

- **`MistralAPI`** (`mistral_api.py`): Handles both string prompts (backward compat) and message lists. Supports streaming via `_stream_response()` generator.
- **`ConversationContext`** (`context.py`): Manages chat state with `files` dict (path→content) and `messages` list. Dynamically builds system prompt with file contents via `get_system_prompt()`.

### Safety Mechanisms

All file writes go through `apply_fix()` which:
1. Creates `.bak` backup before any modification
2. Extracts code from markdown code blocks via `extract_code()` regex
3. Requires explicit user confirmation (except in dry-run mode)

### Token Management

`token_utils.py` uses the official `mistral-common` tokenizer (initialized once globally). `build_prompt()` in `context.py` auto-truncates file content if prompt exceeds 4000 tokens.

## Configuration

Requires `MISTRAL_API_KEY` in a `.env` file at project root.

## Slash Commands (Chat Mode)

`/add <file>`, `/remove <file>`, `/list`, `/apply [file]`, `/clear`, `/exit`, `/help`
