
"""Autonomous Verification System ("The Critic").

Responsible for:
1. Syntax checking (static analysis)
2. Test execution (dynamic verification)
3. Linting (future)
"""

import ast
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple, Dict

console_logger = logging.getLogger("rich")

class Critic:
    """The Critic evaluates code quality and correctness."""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path.cwd()
        self.test_command = self._resolve_test_command()

    def check_syntax(self, file_path: str, content: Optional[str] = None) -> Tuple[bool, str]:
        """Check Python syntax of a file or string content.

        Args:
            file_path: Path to the file (used for error reporting).
            content: Optional content override. If None, reads from file.

        Returns:
            (valid: bool, message: str)
        """
        try:
            if content is None:
                if not Path(file_path).exists():
                    return False, f"File not found: {file_path}"
                content = Path(file_path).read_text(encoding="utf-8")

            ast.parse(content, filename=file_path)
            return True, "Syntax valid."
        except SyntaxError as e:
            error_msg = f"Syntax Error in {file_path}:{e.lineno}\n{e.msg}\n{e.text}"
            return False, error_msg
        except Exception as e:
            return False, f"Error checking syntax: {str(e)}"

    def _resolve_test_command(self) -> str:
        """Determine the command to run tests."""
        # 1. Check pyproject.toml for [tool.mistral]
        toml_path = self.project_root / "pyproject.toml"
        if toml_path.exists():
            try:
                content = toml_path.read_text(encoding="utf-8")
                mistral_section = re.search(r"\[tool\.mistral\](.*?)(?:\[|$)", content, re.DOTALL)
                if mistral_section:
                    cmd_match = re.search(r'test_command\s*=\s*"(.*?)"', mistral_section.group(1))
                    if cmd_match:
                        return cmd_match.group(1)
            except Exception:
                logging.warning("Failed to parse pyproject.toml for test command.")

        # 2. Auto-detect
        if (self.project_root / "pytest.ini").exists() or shutil.which("pytest"):
            return "pytest"
        if (self.project_root / "manage.py").exists():
            return "python manage.py test"
        
        # Fallback
        return "python -m unittest"

    def run_tests(self, files: Optional[List[str]] = None) -> Tuple[bool, str]:
        """Run the test suite."""
        cmd = self.test_command
        
        # Basic optimization for pytest
        if files and "pytest" in cmd:
            test_files = [f for f in files if "test" in f or "spec" in f]
            if test_files:
                cmd = f"{cmd} {' '.join(test_files)}"
            # If changed files are not tests, we typically run the whole suite 
            # or try to map implementation to test (future work).
            # For now, run full suite if no specific test file modified.

        try:
            logging.info(f"Running verification: {cmd}")
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            
            # Truncate
            if len(output) > 5000:
                output = output[:5000] + "\n... (truncated)"

            header = f"Command: {cmd}\nExit Code: {result.returncode}\n"
            full_report = header + output
            
            return result.returncode == 0, full_report
            
        except subprocess.TimeoutExpired:
            return False, "Verification timed out after 300s."
        except Exception as e:
            return False, f"Verification failed to run: {str(e)}"
