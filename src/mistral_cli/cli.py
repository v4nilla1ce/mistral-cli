"""CLI entry point for Mistral CLI."""

import difflib
import logging
import re
import shutil
from datetime import datetime
from glob import glob
from pathlib import Path
from typing import Optional

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

from . import __version__
from .api import MistralAPI
from .config import (
    ensure_dirs,
    get_api_key,
    get_backup_dir,
    get_config_file,
    get_config_source,
    get_log_dir,
    load_config,
    save_config,
)
from .context import ConversationContext, build_prompt

# Configure logging to use global log directory
ensure_dirs()
log_file = get_log_dir() / "mistral-cli.log"
logging.basicConfig(
    filename=str(log_file),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

console = Console()


def extract_code(suggestion: str) -> str:
    """Extract code from a Markdown code block (any language)."""
    # Match any language identifier (python, javascript, etc.) or no identifier
    pattern = r"```(?:\w+)?\s*(.*?)\s*```"
    match = re.search(pattern, suggestion, re.DOTALL)
    if match:
        return match.group(1)
    return suggestion  # Fallback: assume the whole text is code if no block found


def show_diff(original: str, new_content: str, file_path: str) -> None:
    """Display a colored diff between original and new content."""
    original_lines = original.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        original_lines,
        new_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
    )

    diff_text = "".join(diff)
    if not diff_text:
        console.print("[dim]No changes detected.[/]")
        return

    # Display with syntax highlighting
    console.print(Panel(Syntax(diff_text, "diff", theme="monokai"), title="Diff Preview", border_style="yellow"))


def create_file(file_path: str, content: str, dry_run: bool = False) -> bool:
    """Create a new file with the given content.

    Args:
        file_path: Path to the file to create.
        content: Content to write to the file.
        dry_run: If True, only preview without creating.

    Returns:
        True if successful, False otherwise.
    """
    try:
        path = Path(file_path)

        if path.exists():
            console.print(f"[red]Error: File {file_path} already exists. Use /apply to modify.[/]")
            return False

        if dry_run:
            console.print(f"[yellow][Dry Run] Would create: {file_path}[/]")
            console.print(Panel(Syntax(content, path.suffix.lstrip(".") or "text", theme="monokai"), title="Preview", border_style="yellow"))
            return True

        # Create parent directories if needed
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        console.print(f"[bold green]Created: {file_path}[/]")
        logging.info(f"Created new file: {file_path}")
        return True
    except Exception as e:
        console.print(f"[bold red]Error creating file: {e}[/]")
        logging.error(f"Error creating file {file_path}: {e}")
        return False


def apply_fix(
    file_path: str,
    suggestion: str,
    dry_run: bool = False,
    show_diff_preview: bool = False,
) -> bool:
    """Apply the suggested fix to the file, with backup.

    Args:
        file_path: Path to the file to modify.
        suggestion: The AI suggestion containing code.
        dry_run: If True, only preview without applying.
        show_diff_preview: If True, show diff before applying.

    Returns:
        True if successful, False otherwise.
    """
    try:
        path = Path(file_path)

        # Read original content for diff
        original_content = ""
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                original_content = f.read()

        # Extract code to write
        code_to_write = extract_code(suggestion)

        # Show diff preview if requested
        if show_diff_preview:
            show_diff(original_content, code_to_write, file_path)

        # Dry run mode
        if dry_run:
            console.print(f"[yellow][Dry Run] Would modify: {file_path}[/]")
            if not show_diff_preview:
                show_diff(original_content, code_to_write, file_path)
            return True

        # Create backup in the global backup directory
        backup_dir = get_backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_name = path.name
        backup_path = backup_dir / f"{original_name}.{timestamp}.bak"
        shutil.copy(file_path, backup_path)
        console.print(f"[dim]Backup created: {backup_path}[/]")
        logging.info(f"Backup created at {backup_path}")

        # Write the new content
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(code_to_write)
        logging.info(f"Fix applied to {file_path}")
        return True
    except Exception as e:
        error_msg = f"Error applying fix: {e}"
        console.print(f"[bold red]{error_msg}[/]")
        logging.error(error_msg)
        return False


@click.group()
@click.version_option(version=__version__, prog_name="mistral")
def cli():
    """Mistral CLI: Fix Python bugs using Mistral AI."""
    pass


@cli.group()
def config():
    """Manage Mistral CLI configuration."""
    pass


@config.command("setup")
def config_setup():
    """Interactive setup to configure API key."""
    console.print("[bold blue]Mistral CLI Configuration Setup[/]")
    console.print()

    # Show current status
    current_source = get_config_source()
    if current_source != "Not configured":
        console.print(f"[dim]Current API key source: {current_source}[/]")
        if not click.confirm("Do you want to update the configuration?"):
            return

    # Prompt for API key
    api_key = click.prompt(
        "Enter your Mistral API key",
        hide_input=True,
        confirmation_prompt=True,
    )

    # Save to config file
    cfg = load_config()
    cfg["api_key"] = api_key
    if save_config(cfg):
        console.print(f"[bold green]Configuration saved to {get_config_file()}[/]")
    else:
        console.print("[bold red]Failed to save configuration.[/]")


@config.command("show")
def config_show():
    """Show current configuration status."""
    console.print("[bold blue]Mistral CLI Configuration[/]")
    console.print()

    # Config file path
    config_file = get_config_file()
    console.print(f"[bold]Config file:[/] {config_file}")
    console.print(f"[bold]Log directory:[/] {get_log_dir()}")
    console.print(f"[bold]Backup directory:[/] {get_backup_dir()}")
    console.print()

    # API key status
    source = get_config_source()
    api_key = get_api_key()

    console.print(f"[bold]API key source:[/] {source}")
    if api_key:
        masked = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
        console.print(f"[bold]API key:[/] {masked}")
    else:
        console.print("[bold yellow]API key:[/] Not configured")
        console.print()
        console.print("[dim]Run 'mistral config setup' to configure your API key.[/]")


@cli.command()
@click.argument("file")
@click.argument("bug_description")
@click.option("--dry-run", is_flag=True, help="Simulate the fix without applying it.")
@click.option("--api-key", envvar="MISTRAL_API_KEY", help="Mistral API key.")
def fix(file: str, bug_description: str, dry_run: bool, api_key: str):
    """Suggest and optionally apply fixes for bugs."""
    logging.info(f"Started fix command for file: {file} with bug: {bug_description}")
    console.print(
        f"[bold blue]Analyzing[/] [green]{file}[/] for bug: [yellow]{bug_description}[/]"
    )

    try:
        prompt = build_prompt(file, bug_description)

        # Token Counting
        from .tokens import count_tokens

        token_count = count_tokens(prompt)
        console.print(f"[dim]Estimated Input Tokens: {token_count}[/]")
        logging.info(f"Input tokens: {token_count}")

        api = MistralAPI(api_key=api_key)

        with console.status("[bold green]Asking Mistral AI...[/]"):
            suggestion = api.chat(prompt)

        console.print(
            Panel(Markdown(suggestion), title="Mistral's Suggestion", border_style="blue")
        )
        logging.info("Received suggestion from API")

        if dry_run:
            console.print("\n[bold yellow][Dry Run] Changes were NOT applied.[/]")
            logging.info("Dry run completed. No changes applied.")
            return

        if click.confirm("Do you want to apply this fix?"):
            if apply_fix(file, suggestion):
                console.print("[bold green]Fix applied successfully![/]")
            else:
                console.print("[bold red]Failed to apply fix.[/]")
        else:
            console.print("[bold yellow]Fix cancelled[/]")
            logging.info("User cancelled the fix.")

    except Exception as e:
        console.print(f"[bold red]Error: {e}[/]")
        logging.error(f"An error occurred: {e}")


@cli.command()
@click.option(
    "--model",
    default="mistral-small",
    help="Mistral model to use (tiny, small, medium, large).",
)
@click.option("--api-key", envvar="MISTRAL_API_KEY", help="Mistral API key.")
def chat(model: str, api_key: str):
    """Interactive chat with Mistral AI."""
    console.print(
        Panel(
            f"[bold blue]Mistral AI Chat ({model})[/]\n"
            "Type [green]/add <file>[/] to add context.\n"
            "Type [green]/exit[/] to quit.",
            title="Welcome",
            border_style="blue",
        )
    )

    api = MistralAPI(api_key=api_key)
    context = ConversationContext()
    session = PromptSession()

    while True:
        try:
            # Prompt
            user_input = session.prompt(HTML("<ansigreen>You ></ansigreen> ")).strip()

            if not user_input:
                continue

            # Slash Commands
            if user_input.startswith("/"):
                parts = user_input.split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else None

                if cmd in ["/exit", "/quit"]:
                    console.print("[yellow]Goodbye![/]")
                    break

                elif cmd == "/add":
                    if not arg:
                        console.print("[red]Usage: /add <file_path or glob pattern>[/]")
                        continue

                    # Check if arg contains glob patterns
                    if any(c in arg for c in ["*", "?", "["]):
                        # Glob pattern
                        matches = glob(arg, recursive=True)
                        if not matches:
                            console.print(f"[red]No files matched: {arg}[/]")
                            continue
                        added = 0
                        for match in matches:
                            if Path(match).is_file():
                                success, msg = context.add_file(match)
                                if success:
                                    added += 1
                                    console.print(f"[dim]Added: {match}[/]")
                        console.print(f"[green]Added {added} file(s)[/]")
                    else:
                        # Single file
                        success, msg = context.add_file(arg)
                        color = "green" if success else "red"
                        console.print(f"[{color}]{msg}[/]")
                    continue

                elif cmd == "/remove":
                    if not arg:
                        console.print("[red]Usage: /remove <file_path>[/]")
                        continue
                    success, msg = context.remove_file(arg)
                    color = "green" if success else "red"
                    console.print(f"[{color}]{msg}[/]")
                    continue

                elif cmd == "/list":
                    if not context.files:
                        console.print("[dim]No files in context.[/]")
                    else:
                        console.print("[bold]Context Files:[/]")
                        for f in context.files:
                            console.print(f" - {f}")
                    continue

                elif cmd == "/clear":
                    context.clear()
                    console.print("[yellow]Context and history cleared.[/]")
                    continue

                elif cmd == "/apply":
                    # Get last assistant message
                    last_msg = None
                    for msg in reversed(context.messages):
                        if msg["role"] == "assistant":
                            last_msg = msg["content"]
                            break

                    if not last_msg:
                        console.print("[red]No AI response to apply.[/]")
                        continue

                    # Parse argument for flags
                    target_file = None
                    show_diff_flag = False
                    dry_run_flag = False

                    if arg:
                        parts = arg.split()
                        for part in parts:
                            if part == "--diff":
                                show_diff_flag = True
                            elif part == "--dry-run":
                                dry_run_flag = True
                            else:
                                target_file = part

                    if not target_file:
                        if len(context.files) == 1:
                            target_file = list(context.files.keys())[0]
                        else:
                            console.print(
                                "[red]Usage: /apply [--diff] [--dry-run] <file_path>[/]"
                            )
                            continue

                    # Show diff first if requested
                    if show_diff_flag and not dry_run_flag:
                        if Path(target_file).exists():
                            with open(target_file, "r", encoding="utf-8") as f:
                                original = f.read()
                            new_content = extract_code(last_msg)
                            show_diff(original, new_content, target_file)
                            if not click.confirm("Apply these changes?"):
                                console.print("[yellow]Cancelled.[/]")
                                continue

                    # Apply
                    console.print(f"[yellow]Applying changes to {target_file}...[/]")
                    if apply_fix(target_file, last_msg, dry_run=dry_run_flag, show_diff_preview=dry_run_flag):
                        if not dry_run_flag:
                            console.print(
                                f"[bold green]Successfully applied changes to {target_file}[/]"
                            )
                    else:
                        console.print(
                            f"[bold red]Failed to apply changes to {target_file}[/]"
                        )
                    continue

                elif cmd == "/create":
                    if not arg:
                        console.print("[red]Usage: /create <file_path>[/]")
                        continue

                    # Get last assistant message for content
                    last_msg = None
                    for msg in reversed(context.messages):
                        if msg["role"] == "assistant":
                            last_msg = msg["content"]
                            break

                    if not last_msg:
                        console.print("[red]No AI response to use as content.[/]")
                        continue

                    # Parse for --dry-run flag
                    dry_run_flag = "--dry-run" in arg
                    file_path = arg.replace("--dry-run", "").strip()

                    content = extract_code(last_msg)
                    create_file(file_path, content, dry_run=dry_run_flag)
                    continue

                elif cmd == "/diff":
                    # Show diff of what would change
                    last_msg = None
                    for msg in reversed(context.messages):
                        if msg["role"] == "assistant":
                            last_msg = msg["content"]
                            break

                    if not last_msg:
                        console.print("[red]No AI response to diff.[/]")
                        continue

                    target_file = arg if arg else (list(context.files.keys())[0] if len(context.files) == 1 else None)
                    if not target_file:
                        console.print("[red]Usage: /diff <file_path>[/]")
                        continue

                    if Path(target_file).exists():
                        with open(target_file, "r", encoding="utf-8") as f:
                            original = f.read()
                        new_content = extract_code(last_msg)
                        show_diff(original, new_content, target_file)
                    else:
                        console.print(f"[yellow]File {target_file} doesn't exist (would be created)[/]")
                        console.print(Panel(Syntax(extract_code(last_msg), Path(target_file).suffix.lstrip(".") or "text", theme="monokai"), title="New File Content"))
                    continue

                elif cmd == "/help":
                    console.print(
                        "[bold]Commands:[/]\n"
                        " /add <file|glob>           - Add file(s) to context (supports *.py, **/*.js)\n"
                        " /remove <file>             - Remove file from context\n"
                        " /list                      - List context files\n"
                        " /apply [--diff] [--dry-run] [file] - Apply last AI code to file\n"
                        " /create [--dry-run] <file> - Create new file from last AI response\n"
                        " /diff [file]               - Preview diff of last AI response\n"
                        " /clear                     - Clear history & files\n"
                        " /exit                      - Quit"
                    )
                    continue

                else:
                    console.print(f"[red]Unknown command: {cmd}[/]")
                    continue

            # Chat Logic
            messages = context.prepare_messages(user_input, model=model)

            # Streaming Response
            full_response = ""
            with Live(Markdown(""), refresh_per_second=10, console=console) as live:
                try:
                    stream = api.chat(messages, model=model, stream=True, temperature=0.7)
                    # Check if stream is a list (error fallback) or generator
                    if isinstance(stream, list):
                        full_response = stream[0]
                        live.update(Markdown(full_response))
                    else:
                        for chunk in stream:
                            full_response += chunk
                            live.update(Markdown(full_response))
                except Exception as e:
                    console.print(f"[red]Error during streaming: {e}[/]")

            # Update History
            context.add_message("user", user_input)
            context.add_message("assistant", full_response)
            logging.info(f"Chat Response: {full_response}")

        except KeyboardInterrupt:
            continue
        except EOFError:
            break


if __name__ == "__main__":
    cli()
