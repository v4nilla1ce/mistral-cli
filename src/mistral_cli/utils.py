
import os
from pathlib import Path
from typing import Optional
from rich.console import Console
from prompt_toolkit.shortcuts import radiolist_dialog

console = Console()

def interactive_file_picker(cwd: str = ".") -> Optional[str]:
    """Show an interactive file picker using prompt_toolkit.

    Args:
        cwd: Current working directory to start from.

    Returns:
        Selected file path, or None if cancelled.
    """
    try:
        # Get list of files in current directory (non-hidden, common code files)
        extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".hpp", ".rb", ".php", ".swift", ".kt", ".scala", ".sh", ".bash", ".zsh", ".yaml", ".yml", ".json", ".toml", ".md", ".txt", ".html", ".css", ".scss", ".sql"}

        files = []
        cwd_path = Path(cwd).resolve()

        for p in cwd_path.rglob("*"):
            if p.is_file() and not any(part.startswith(".") for part in p.parts):
                if p.suffix.lower() in extensions or not p.suffix:
                    rel_path = p.relative_to(cwd_path)
                    files.append(str(rel_path))

        if not files:
            console.print("[yellow]No code files found in current directory.[/]")
            return None

        # Sort and limit
        files.sort()
        if len(files) > 50:
            console.print(f"[dim]Showing first 50 of {len(files)} files.[/]")
            files = files[:50]

        # Create choices for radiolist dialog
        choices = [(f, f) for f in files]

        result = radiolist_dialog(
            title="Select a file",
            text="Use arrow keys to navigate, Enter to select, Escape to cancel:",
            values=choices,
        ).run()

        return result
    except Exception as e:
        console.print(f"[red]Error in file picker: {e}[/]")
        return None
