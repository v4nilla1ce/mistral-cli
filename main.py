import click
import os
from context import build_prompt
from mistral_api import MistralAPI

@click.group()
def cli():
    """Mistral CLI: Fix Python bugs using Mistral API."""
    pass

@cli.command()
@click.argument("file")
@click.argument("bug_description")
def fix(file, bug_description):
    """Suggest a fix for a bug in the specified file."""
    click.echo(f"Analyzing {file} for bug: {bug_description}")
    prompt = build_prompt(file, bug_description)
    api = MistralAPI()
    suggestion = api.chat(prompt)
    click.echo(f"Mistral's suggestion:\n{suggestion}")

    # Ask for confirmation before applying the fix
    if click.confirm("Do you want to apply this fix?"):
        apply_fix(file, suggestion)
        click.echo("Fix applied successfully!")
    else:
        click.echo("Fix not applied.")

def apply_fix(file_path, suggestion):
    """Apply the suggested fix to the file."""
    # This is a simplified example. You may need to parse the suggestion more carefully.
    with open(file_path, 'w') as file:
        file.write(suggestion)

if __name__ == "__main__":
    cli()
