"""CLI entry point for Mistral CLI."""

import logging
import re
import shutil
from pathlib import Path

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

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
    """Extract code from a Markdown code block."""
    pattern = r"```python\s*(.*?)\s*```"
    match = re.search(pattern, suggestion, re.DOTALL)
    if match:
        return match.group(1)
    return suggestion  # Fallback: assume the whole text is code if no block found


def apply_fix(file_path: str, suggestion: str) -> bool:
    """Apply the suggested fix to the file, with backup.

    Args:
        file_path: Path to the file to modify.
        suggestion: The AI suggestion containing code.

    Returns:
        True if successful, False otherwise.
    """
    try:
        # Create backup in the global backup directory
        backup_dir = get_backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique backup filename
        original_name = Path(file_path).name
        backup_path = backup_dir / f"{original_name}.bak"
        shutil.copy(file_path, backup_path)
        console.print(f"[dim]Backup created: {backup_path}[/]")
        logging.info(f"Backup created at {backup_path}")

        # Extract and write code
        code_to_write = extract_code(suggestion)

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
                        console.print("[red]Usage: /add <file_path>[/]")
                        continue
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

                    # Determine file
                    target_file = None
                    if arg:
                        target_file = arg
                    elif len(context.files) == 1:
                        target_file = list(context.files.keys())[0]
                    else:
                        console.print(
                            "[red]Usage: /apply <file_path> "
                            "(Required if multiple files in context)[/]"
                        )
                        continue

                    # Apply
                    console.print(f"[yellow]Applying changes to {target_file}...[/]")
                    if apply_fix(target_file, last_msg):
                        console.print(
                            f"[bold green]Successfully applied changes to {target_file}[/]"
                        )
                    else:
                        console.print(
                            f"[bold red]Failed to apply changes to {target_file}[/]"
                        )
                    continue

                elif cmd == "/help":
                    console.print(
                        "[bold]Commands:[/]\n"
                        " /add <file>    - Add file to context\n"
                        " /remove <file> - Remove file\n"
                        " /list          - List files\n"
                        " /apply [file]  - Apply last AI code to file\n"
                        " /clear         - Clear history & files\n"
                        " /exit          - Quit"
                    )
                    continue

                else:
                    console.print(f"[red]Unknown command: {cmd}[/]")
                    continue

            # Chat Logic
            messages = context.prepare_messages(user_input)

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
