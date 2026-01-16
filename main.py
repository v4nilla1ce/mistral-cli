import click
from context import build_prompt
from mistral_api import MistralAPI

import shutil
import re

import logging
import datetime

# Configure logging
logging.basicConfig(
    filename='mistral-cli.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

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
        click.echo(f"Backup created: {backup_path}")
        logging.info(f"Backup created at {backup_path}")

        # Extract and write code
        code_to_write = extract_code(suggestion)
        
        with open(file_path, 'w') as file:
            file.write(code_to_write)
        logging.info(f"Fix applied to {file_path}")
        return True
    except Exception as e:
        error_msg = f"Error applying fix: {e}"
        print(error_msg)
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
    click.echo(f"Analyzing {file} for bug: {bug_description}")
    
    try:
        prompt = build_prompt(file, bug_description)
        
        # Token Counting
        from token_utils import count_tokens
        token_count = count_tokens(prompt)
        click.echo(f"Estimated Input Tokens: {token_count}")
        logging.info(f"Input tokens: {token_count}")

        api = MistralAPI()
        
        suggestion = api.chat(prompt)
        click.echo(f"Mistral's suggestion:\n{suggestion}")
        logging.info("Received suggestion from API")

        if dry_run:
            click.echo("\n[Dry Run] Changes were NOT applied.")
            logging.info("Dry run completed. No changes applied.")
            return

        if click.confirm("Do you want to apply this fix?"):
            if apply_fix(file, suggestion):
                click.echo("Fix applied successfully!")
            else:
                click.echo("Failed to apply fix.")
        else:
            click.echo("Fix cancelled")
            logging.info("User cancelled the fix.")
            
    except Exception as e:
        click.echo(f"Error: {e}")
        logging.error(f"An error occurred: {e}")

if __name__ == "__main__":
    cli()
