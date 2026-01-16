import click
from context import build_prompt
from mistral_api import MistralAPI

import shutil
import re

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

        # Extract and write code
        code_to_write = extract_code(suggestion)
        
        with open(file_path, 'w') as file:
            file.write(code_to_write)
        return True
    except Exception as e:
        print(f"Error applying fix: {e}")
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
    click.echo(f"Analyzing {file} for bug: {bug_description}")
    prompt = build_prompt(file, bug_description)
    api = MistralAPI()

    try:
        suggestion = api.chat(prompt)
        click.echo(f"Mistral's suggestion:\n{suggestion}")

        if dry_run:
            click.echo("\n[Dry Run] Changes were NOT applied.")
            return

        if click.confirm("Do you want to apply this fix?"):
            if apply_fix(file, suggestion):
                click.echo("Fix applied successfully!")
            else:
                click.echo("Failed to apply fix.")
    except Exception as e:
        click.echo(f"Error: {e}")

if __name__ == "__main__":
    cli()
