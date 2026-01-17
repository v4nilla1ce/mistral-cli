# Mistral CLI 🤖

A powerful command-line interface that uses Mistral AI to inspect your Python code, analyze bugs, and automatically suggest fixes.

## Features ✨

*   **Automated Bug Fixing**: Analyzes error descriptions and suggests Python code fixes.
*   **Safety First**:
    *   **Backups**: Automatically creates `.bak` files before applying any changes.
    *   **Dry Run**: Preview the AI's suggestion without modifying files (`--dry-run`).
    *   **Confirmation**: Always asks for permission before writing to disk.
*   **Smart Context**:
    *   **Token Management**: Estimates token usage to avoid API limits.
    *   **Context Truncation**: Automatically shortens huge files to fit within the model's window.
*   **Windows Compatible**: Native implementation works seamlessly on Windows, Linux, and macOS.
*   **Logging**: Tracks all actions in `mistral-cli.log` for debugging and transparency.

## Installation 📦

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/v4nilla1ce/mistral-cli.git
    cd mistral-cli
    ```

2.  **Create a virtual environment** (recommended):
    ```bash
    python -m venv venv
    # Windows
    venv\Scripts\activate
    # Linux/Mac
    source venv/bin/activate
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Configuration 🔑

You need a Mistral AI API Key.

1.  Create a `.env` file in the project root:
    ```bash
    # .env
    MISTRAL_API_KEY=your_actual_api_key_here
    ```

## Usage 🚀

### Interactive Chat 💬 (New!)
Experience a Gemini-like conversational interface with streaming responses and context management.

```bash
python main.py chat
```

**Slash Commands:**
- `/add <file>`: Add a file to the conversation context.
- `/remove <file>`: Remove a file.
- `/list`: See what files the AI can see.
- `/clear`: Reset history and context.
- `/exit`: Quit the chat.

### Fix a bug
Run the `fix` command with the filename and a description of the error:

```bash
python main.py fix app.py "TypeError in calculate_total function"
```

### Dry Run (Safe Mode)
Want to see the fix without applying it? Use `--dry-run`:

```bash
python main.py fix app.py "IndexError in list processing" --dry-run
```

## Logs 📝

Every interaction is logged to `mistral-cli.log` in the same directory. Check this file if something goes wrong or to audit previous fixes.

## License

MIT
