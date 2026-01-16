# Mistral CLI - Codebase Walkthrough

This document provides a detailed explanation of the current `mistral-cli` codebase, breaking down each component to help you understand exactly how the tool works.

## 1. Entry Point: `main.py`
This is the heart of the CLI application. It handles user input using the `click` library and orchestrates the flow between context gathering, API interactions, and applying fixes.

### Imports
```python
import click
from context import build_prompt
from mistral_api import MistralAPI
```
- **`click`**: A Python package for creating command line interfaces.
- **`build_prompt`**: Imported from our local `context` module. We'll explore this next.
- **`MistralAPI`**: Imported from our local `mistral_api` module to handle communication with the AI.

### `apply_fix` Function
```python
def apply_fix(file_path, suggestion):
    """Apply the suggested fix to the file, with backup."""
    # ... created backup .bak file ...
    # ... extracts python code block using regex ...
    with open(file_path, 'w') as file:
        file.write(code_to_write)
```
- **Purpose**: safely applies the fix.
- **Safety Mechanisms**:
    1.  **Backup**: Copies the original file to `filename.bak` before any writes.
    2.  **Extraction**: Uses a regex to find content between ```python ... ``` blocks. This prevents writing conversational text (like "Here is your fix:") into the code file.

### CLI Setup
```python
@click.group()
def cli():
    """Mistral CLI: Fix Python bugs using Mistral API."""
    pass
```
- **`@click.group()`**: Defines the main command group.

### The `fix` Command
```python
@click.command()
@click.argument("file")
@click.argument("bug_description")
def fix(file, bug_description):
```
- **`@click.command()`**: Registers `fix` as a subcommand of the main `cli`.

# ... (omitted parts of fix command logic) ...

---

## 2. Context Gathering: `context.py`
This module is responsible for "seeing" the code and the error.

### `read_relevant_file`
```python
def read_relevant_file(file_path, max_lines=50):
    # ... reads first 50 lines ...
```
- **Purpose**: Reads the target file content.

### `search_in_file`
```python
def search_in_file(file_path, keyword):
    """Search for a keyword in the file using Python (Windows-compatible)."""
    # ... iterates line by line looking for keyword ...
```
- **Purpose**: Finds specific lines of code relevant to the bug.
- **Mechanism**: Previously used `grep` (Linux only), now uses native Python file reading to work on **Windows**.

### `build_prompt`
```python
def build_prompt(file_path, bug_description):
    # ...
    function_name = bug_description.split()[0]
    error_context = search_in_file(file_path, function_name)
    # ...
```
- **Dynamic Search**: Now correctly uses the function name derived from the user's input, rather than a hardcoded string.

---

## 3. The Brain: `mistral_api.py`
This remains the same, handling the HTTP requests to Mistral AI.

---

## Summary of Current State
- **Functional**: Can read files, find context on Windows, and safely apply fixes.
- **Safety**:
    - ✅ **Backups**: Creates `.bak` files.
    - ✅ **Code Extraction**: Parses only the code blocks from the AI's response.
- **OS Support**: Works on **Windows**, Linux, and macOS (no more `grep` dependency).
