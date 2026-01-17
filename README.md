# Mistral CLI

A command-line interface that uses Mistral AI to inspect your Python code, analyze bugs, and automatically suggest fixes.

## Features

- **Automated Bug Fixing**: Analyzes error descriptions and suggests Python code fixes.
- **Interactive Chat**: Conversational interface with streaming responses and file context management.
- **Global Installation**: Install once with `pipx`, run from anywhere.
- **Safety First**:
  - **Backups**: Automatically creates backups before applying any changes.
  - **Dry Run**: Preview the AI's suggestion without modifying files (`--dry-run`).
  - **Confirmation**: Always asks for permission before writing to disk.
- **Smart Context**:
  - **Token Management**: Estimates token usage to avoid API limits.
  - **Context Truncation**: Automatically shortens large files to fit within the model's window.
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

### Interactive Chat

```bash
mistral chat
```

**Slash Commands:**
- `/add <file>` - Add a file to the conversation context
- `/remove <file>` - Remove a file from context
- `/list` - See files the AI can see
- `/apply [file]` - Apply code from the last AI response to a file (with backup)
- `/clear` - Reset history and context
- `/exit` - Quit the chat

### Fix a Bug

```bash
mistral fix app.py "TypeError in calculate_total function"
```

### Dry Run (Safe Mode)

Preview the fix without applying it:

```bash
mistral fix app.py "IndexError in list processing" --dry-run
```

### Version

```bash
mistral --version
```

## Logs

Logs are stored in the global data directory:
- **Windows**: `%LOCALAPPDATA%\mistral-cli\logs\mistral-cli.log`
- **Linux/Mac**: `~/.local/share/mistral-cli/logs/mistral-cli.log`

## Development

```bash
# Run tests
pytest

# Run linters
black src/
isort src/
flake8 src/

# Type checking
mypy src/
```

## License

MIT
