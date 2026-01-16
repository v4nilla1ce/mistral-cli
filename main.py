import click
from context import build_prompt
from mistral_api import MistralAPI

import shutil
import re
import logging
import datetime

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

# Configure logging
logging.basicConfig(
    filename='mistral-cli.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

console = Console()

def extract_code(suggestion):
    """Extract code from a Markdown code block."""
    pattern = r"```python\s*(.*?)\s*```"
    match = re.search(pattern, suggestion, re.DOTALL)
    if match:
        return match.group(1)
    return suggestion  # Fallback: assume the whole text is code if no block found

def apply_fix(file_path, suggestion):
    """Apply the suggested fix to the file, with backup."""
    try:
        # Create backup
        backup_path = f"{file_path}.bak"
        shutil.copy(file_path, backup_path)
        console.print(f"[dim]Backup created: {backup_path}[/]")
        logging.info(f"Backup created at {backup_path}")

        # Extract and write code
        code_to_write = extract_code(suggestion)
        
        with open(file_path, 'w') as file:
            file.write(code_to_write)
        logging.info(f"Fix applied to {file_path}")
        return True
    except Exception as e:
        error_msg = f"Error applying fix: {e}"
        console.print(f"[bold red]{error_msg}[/]")
        logging.error(error_msg)
        return False

@click.group()
def cli():
    """Mistral CLI: Fix Python bugs using Mistral API."""
    pass

@cli.command()
@click.argument("file")
@click.argument("bug_description")
@click.option("--dry-run", is_flag=True, help="Simulate the fix without applying it.")
def fix(file, bug_description, dry_run):
    """Suggest and optionally apply fixes for bugs."""
    logging.info(f"Started fix command for file: {file} with bug: {bug_description}")
    console.print(f"[bold blue]Analyzing[/] [green]{file}[/] for bug: [yellow]{bug_description}[/]")
    
    try:
        prompt = build_prompt(file, bug_description)
        
        # Token Counting
        from token_utils import count_tokens
        token_count = count_tokens(prompt)
        console.print(f"[dim]Estimated Input Tokens: {token_count}[/]")
        logging.info(f"Input tokens: {token_count}")

        api = MistralAPI()
        
        with console.status("[bold green]Asking Mistral AI...[/]"):
            suggestion = api.chat(prompt)
        
        console.print(Panel(Markdown(suggestion), title="Mistral's Suggestion", border_style="blue"))
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

if __name__ == "__main__":
    cli()
