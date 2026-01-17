
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from rich.console import Console
from rich.table import Table

from .agent import Agent, AgentConfig
from .api import MistralAPI
from .config import get_api_key

console = Console()

@dataclass
class BenchmarkResult:
    task_id: str
    success: bool
    duration: float
    iterations: int
    error: Optional[str] = None

class BenchmarkRunner:
    """Runs agent benchmarks using Golden Tasks."""

    def __init__(self, tasks_file: str = "tests/golden_tasks.json"):
        self.tasks_file = Path(tasks_file)
        self.results: List[BenchmarkResult] = []

    def load_tasks(self) -> List[Dict[str, Any]]:
        """Load tasks from JSON."""
        if not self.tasks_file.exists():
            raise FileNotFoundError(f"Tasks file not found: {self.tasks_file}")
        return json.loads(self.tasks_file.read_text(encoding="utf-8"))

    def run_task(self, task: Dict[str, Any], api_key: str) -> BenchmarkResult:
        """Run a single benchmark task in a temp directory."""
        task_id = task["id"]
        prompt = task["prompt"]
        
        console.print(f"[bold]Running Task: {task_id}[/]")
        
        # Create isolated environment
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Setup
            if "setup_files" in task:
                for fname, content in task["setup_files"].items():
                    (temp_path / fname).write_text(content)
            
            if "setup_commands" in task:
                for cmd in task["setup_commands"]:
                    # Create dummy files for touch commands to avoid cross-platform issues here
                    if cmd.startswith("touch "):
                        fname = cmd.split(" ", 1)[1]
                        (temp_path / fname).touch()

            # Initialize Agent in this dir
            # We need to monkey-patch os.getcwd or pass cwd to tools
            # For now, let's change CWD safely
            original_cwd = os.getcwd()
            os.chdir(temp_dir)
            
            start_time = time.time()
            iterations = 0
            success = False
            error = None

            try:
                api = MistralAPI(api_key=api_key)
                config = AgentConfig(
                    model="mistral-small",
                    max_iterations=10,
                    auto_confirm_safe=True, # Auto-run safe
                    confirm_all=True # Benchmark mode needs to run without interaction
                )
                agent = Agent(api=api, config=config)
                
                # Mock callbacks to avoid spam
                agent.on_thinking = lambda: None
                agent.on_tool_call = lambda n, a: None
                agent.on_tool_result = lambda n, r: None
                agent.on_response = lambda c: None

                # Run
                agent.run(prompt)
                iterations = agent.state.iteration

                # Verification
                success = True
                
                # Check expected files exist
                if "expected_files" in task:
                    for f in task["expected_files"]:
                        if not Path(f).exists():
                            success = False
                            error = f"Missing file: {f}"
                            break
                
                # Check expected missing
                if success and "expected_missing_files" in task:
                    for f in task["expected_missing_files"]:
                        if Path(f).exists():
                            success = False
                            error = f"File should be deleted: {f}"
                            break

                # Check content (loose match)
                if success and "expected_content" in task:
                    for f, expected in task["expected_content"].items():
                        if not Path(f).exists():
                            success = False
                            error = f"Missing file for content check: {f}"
                            break
                        
                        content = Path(f).read_text()
                        if expected not in content: # Loose substring match
                            success = False
                            error = f"Content mismatch in {f}"
                            break

            except Exception as e:
                success = False
                error = str(e)
            finally:
                os.chdir(original_cwd)
                duration = time.time() - start_time

            result = BenchmarkResult(task_id, success, duration, iterations, error)
            color = "green" if success else "red"
            console.print(f"[{color}]Result: {'PASS' if success else 'FAIL'} ({duration:.2f}s)[/]")
            if error:
                console.print(f"[dim]{error}[/]")
            
            return result

    def run_all(self, api_key: str):
        tasks = self.load_tasks()
        console.print(f"Loaded {len(tasks)} tasks.")
        
        self.results = []
        for task in tasks:
            self.results.append(self.run_task(task, api_key))
            
        self.print_summary()

    def print_summary(self):
        table = Table(title="Benchmark Results")
        table.add_column("Task ID", style="cyan")
        table.add_column("Success", style="bold")
        table.add_column("Time", justify="right")
        table.add_column("Iter", justify="right")
        table.add_column("Error", style="red")

        passed = 0
        for r in self.results:
            status = "[green]PASS[/]" if r.success else "[red]FAIL[/]"
            if r.success: passed += 1
            table.add_row(
                r.task_id, 
                status, 
                f"{r.duration:.2f}s", 
                str(r.iterations), 
                r.error or ""
            )

        console.print(table)
        console.print(f"\nTotal: {len(self.results)}, Passed: {passed}, Failed: {len(self.results) - passed}")

        # GitHub Summary
        step_summary = os.getenv("GITHUB_STEP_SUMMARY")
        if step_summary:
            with open(step_summary, "a", encoding="utf-8") as f:
                f.write("## Agent Benchmark Results\n\n")
                f.write(f"**Total:** {len(self.results)} | **Passed:** {passed} | **Failed:** {len(self.results) - passed}\n\n")
                f.write("| Task ID | Status | Time | Error |\n")
                f.write("| :--- | :--- | :--- | :--- |\n")
                for r in self.results:
                    status = "✅ PASS" if r.success else "❌ FAIL"
                    error = r.error or "-"
                    f.write(f"| `{r.task_id}` | {status} | {r.duration:.2f}s | {error} |\n")
