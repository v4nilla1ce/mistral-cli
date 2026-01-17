
import click
import logging
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML

from ..agent import Agent, AgentConfig
from ..api import MistralAPI
from ..config import get_api_key
from ..utils import interactive_file_picker
from ..backup import get_last_backup, list_backups, restore_backup

console = Console()

@click.command()
@click.argument("instruction", required=False)
@click.option("--interactive", "-i", is_flag=True, help="Enter interactive mode after instruction.")
@click.option("--file", "-f", multiple=True, help="Add file context.")
@click.option("--model", default="mistral-small", help="Mistral model to use.")
@click.option("--api-key", envvar="MISTRAL_API_KEY", help="Mistral API key.")
@click.option("--auto-confirm-safe", is_flag=True, help="Auto-confirm safe read-only commands.")
@click.option("--confirm-all", is_flag=True, help="Skip all confirmations (trusted mode).")
@click.option("--max-iterations", default=10, help="Max agent iterations per request.")
def agent(
    instruction: str,
    interactive: bool,
    file: tuple[str],
    model: str,
    api_key: str,
    auto_confirm_safe: bool,
    confirm_all: bool,
    max_iterations: int
):
    """Proactive Agent Mode (Gen 3).
    
    Execute complex tasks with reasoning, memory, and tools.
    """
    if not api_key:
        api_key = get_api_key()
    
    if not api_key:
        console.print("[red]API key not configured. Run `mistral config setup` first.[/]")
        return

    if confirm_all:
        console.print(
            "[yellow]Warning: Running in trusted mode. "
            "All tool executions will be auto-confirmed.[/]"
        )

    # Initialize Agent
    api = MistralAPI(api_key=api_key)
    config = AgentConfig(
        model=model,
        max_iterations=max_iterations,
        auto_confirm_safe=auto_confirm_safe,
        confirm_all=confirm_all,
        circuit_breaker=True
    )
    
    agent_instance = Agent(api=api, config=config)

    # Set up callbacks
    def on_thinking():
        console.print("[dim]Thinking...[/]")

    def on_tool_call(name: str, args: dict):
        console.print(f"[cyan]Calling tool:[/] {name}")
        if args:
            for k, v in args.items():
                v_str = str(v)
                if len(v_str) > 100:
                    v_str = v_str[:100] + "..."
                console.print(f"  [dim]{k}:[/] {v_str}")

    def on_tool_result(name: str, result):
        if result.success:
            console.print(f"[green]✓[/] {name} completed")
            output = result.output
            if len(output) > 500:
                output = output[:500] + "\n... (truncated)"
            if output:
                console.print(Panel(output, title="Output", border_style="dim"))
        else:
            console.print(f"[red]✗[/] {name} failed: {result.error}")

    def on_response(content: str):
        console.print()
        console.print(Markdown(content))
        
    def on_plan(plan):
        # Plan confirmation is handled by Agent._confirm_plan, strictly passing callback for logging/UI
        pass

    agent_instance.on_thinking = on_thinking
    agent_instance.on_tool_call = on_tool_call
    agent_instance.on_tool_result = on_tool_result
    agent_instance.on_response = on_response
    agent_instance.on_plan = on_plan

    # Add context files
    for f_path in file:
        success, msg = agent_instance.add_file(f_path)
        if success:
            console.print(f"[dim]Added context: {f_path}[/]")
        else:
            console.print(f"[red]{msg}[/]")

    # Single Instruction Execution
    if instruction:
        console.print(f"[bold blue]Agent Goal:[/] {instruction}")
        try:
            agent_instance.run(instruction)
        except Exception as e:
            console.print(f"[red]Error: {e}[/]")
        
        if not interactive:
            return

    # Interactive Loop
    console.print(
        Panel(
            f"[bold blue]Mistral AI Agent ({model})[/]\n"
            "The agent can use tools to help accomplish tasks.\n"
            "Type [green]/tools[/] to list available tools.\n"
            "Type [green]/exit[/] to quit.",
            title="Agentic Mode",
            border_style="cyan",
        )
    )

    session = PromptSession()

    while True:
        try:
            user_input = session.prompt(HTML("<ansicyan>Agent ></ansicyan> ")).strip()

            if not user_input:
                continue

            # Slash commands 
            if user_input.startswith("/"):
                parts = user_input.split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else None

                if cmd in ["/exit", "/quit"]:
                    console.print("[yellow]Goodbye![/]")
                    break
                
                elif cmd == "/tools":
                    console.print("[bold]Available Tools:[/]")
                    for name, desc, needs_confirm in agent_instance.list_tools():
                        confirm_indicator = "[yellow]⚠[/]" if needs_confirm else "[green]✓[/]"
                        console.print(f" {confirm_indicator} [bold]{name}[/]")
                        console.print(f"    [dim]{desc[:80]}...[/]" if len(desc) > 80 else f"    [dim]{desc}[/]")
                    console.print()
                    console.print("[dim][yellow]⚠[/] = requires confirmation, [green]✓[/] = safe[/]")
                    continue

                elif cmd == "/add":
                    if not arg:
                        selected = interactive_file_picker()
                        if selected:
                            success, msg = agent_instance.add_file(selected)
                            color = "green" if success else "red"
                            console.print(f"[{color}]{msg}[/]")
                        else:
                            console.print("[dim]No file selected.[/]")
                    else:
                        success, msg = agent_instance.add_file(arg)
                        color = "green" if success else "red"
                        console.print(f"[{color}]{msg}[/]")
                    continue

                elif cmd == "/remove":
                    if not arg:
                        console.print("[red]Usage: /remove <file_path>[/]")
                    else:
                        success, msg = agent_instance.remove_file(arg)
                        color = "green" if success else "red"
                        console.print(f"[{color}]{msg}[/]")
                    continue

                elif cmd == "/list":
                    files = agent_instance.list_files()
                    if not files:
                        console.print("[dim]No files in context.[/]")
                    else:
                        console.print("[bold]Context Files:[/]")
                        for f in files:
                            console.print(f" - {f}")
                    continue

                elif cmd == "/clear":
                    agent_instance.clear()
                    console.print("[yellow]Context and history cleared.[/]")
                    continue

                elif cmd == "/model":
                    if not arg:
                        console.print(f"[bold]Current model:[/] {agent_instance.config.model}")
                    else:
                        agent_instance.config.model = arg.strip()
                        console.print(f"[green]Switched to model: {arg.strip()}[/]")
                    continue
                
                elif cmd == "/plan":
                    if not arg:
                        agent_instance.planning_mode = True
                        console.print("[bold]Planning Mode Enabled[/]")
                    else:
                        agent_instance.planning_mode = True
                        try:
                            agent_instance.run(arg)
                        except KeyboardInterrupt:
                            agent_instance.cancel()
                            console.print("\n[yellow]Cancelled.[/]")
                    continue
                
                elif cmd == "/help":
                    console.print(
                        "[bold]Agent Commands:[/]\n"
                        " /plan [task]               - Enable planning mode\n"
                        " /tools                     - List available tools\n"
                        " /add [file]                - Add file to context\n"
                        " /remove <file>             - Remove file\n"
                        " /list                      - List files\n"
                        " /clear                     - Clear context\n"
                        " /exit                      - Quit\n"
                    )
                    continue

                else:
                    console.print(f"[red]Unknown command: {cmd}[/]")
                    continue

            # Run the agent
            console.print()
            try:
                agent_instance.run(user_input)
            except KeyboardInterrupt:
                agent_instance.cancel()
                console.print("\n[yellow]Cancelled.[/]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/]")
                logging.error(f"Agent error: {e}")

        except KeyboardInterrupt:
            continue
        except EOFError:
            break
