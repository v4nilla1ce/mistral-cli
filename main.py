import click
from context import build_prompt
from mistral_api import MistralAPI

def apply_fix(file_path, suggestion):
    """Apply the suggested fix to the file."""
    try:
        with open(file_path, 'w') as file:
            file.write(suggestion)
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
def fix(file, bug_description):
    """Suggest and optionally apply fixes for bugs."""
    click.echo(f"Analyzing {file} for bug: {bug_description}")
    prompt = build_prompt(file, bug_description)
    api = MistralAPI()

    try:
        suggestion = api.chat(prompt)
        click.echo(f"Mistral's suggestion:\n{suggestion}")

        if click.confirm("Do you want to apply this fix?"):
            if apply_fix(file, suggestion):
                click.echo("Fix applied successfully!")
            else:
                click.echo("Failed to apply fix.")
    except Exception as e:
        click.echo(f"Error: {e}")

if __name__ == "__main__":
    cli()
