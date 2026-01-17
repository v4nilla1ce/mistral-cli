import click
from context import build_prompt, ConversationContext
from mistral_api import MistralAPI

import shutil
import re
import logging
import datetime

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.patch_stdout import patch_stdout

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

@cli.command()
@click.option("--model", default="mistral-small", help="Mistral model to use (tiny, small, medium, large).")
def chat(model):
    """Interactive chat with Mistral AI."""
    console.print(Panel(f"[bold blue]Mistral AI Chat ({model})[/]\n"
                        "Type [green]/add <file>[/] to add context.\n"
                        "Type [green]/exit[/] to quit.", 
                        title="Welcome", border_style="blue"))
    
    api = MistralAPI()
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
                        console.print("[red]Usage: /apply <file_path> (Required if multiple files in context)[/]")
                        continue

                    # Apply
                    console.print(f"[yellow]Applying changes to {target_file}...[/]")
                    if apply_fix(target_file, last_msg):
                        console.print(f"[bold green]Successfully applied changes to {target_file}[/]")
                    else:
                        console.print(f"[bold red]Failed to apply changes to {target_file}[/]")
                    continue

                elif cmd == "/help":
                    console.print("[bold]Commands:[/]\n"
                                  " /add <file>    - Add file to context\n"
                                  " /remove <file> - Remove file\n"
                                  " /list          - List files\n"
                                  " /apply [file]  - Apply last AI code to file\n"
                                  " /clear         - Clear history & files\n"
                                  " /exit          - Quit")
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
