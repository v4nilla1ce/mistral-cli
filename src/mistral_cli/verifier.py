"""Autonomous Verification system ("The Critic").

Responsible for running tests and verifying code changes.
"""

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple


class Verifier:
    """Runs tests to verify code validity."""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path.cwd()
        self.test_command = self._resolve_test_command()

    def _resolve_test_command(self) -> str:
        """Determine the command to run tests."""
        # 1. Check pyproject.toml for [tool.mistral]
        toml_path = self.project_root / "pyproject.toml"
        if toml_path.exists():
            try:
                content = toml_path.read_text(encoding="utf-8")
                # Simple regex match to avoid adding 'tomli' dependency for now
                # Matches: [tool.mistral] ... test_command = "..."
                # Only works if test_command is on a separate line for now, or use a more complex regex
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
        """Run the test suite.

        Args:
            files: Specific files to test (optimization).
                   Note: Implementation depends on test runner. Use sensible defaults.

        Returns:
            Tuple[bool, str]: (Success, Output)
        """
        cmd = self.test_command
        
        # Basic optimization: if using pytest and files are test files, pass them
        # This is a naive implementation; a full one would map source -> test files
        if files and "pytest" in cmd:
            test_files = [f for f in files if "test" in f or "spec" in f]
            if test_files:
                cmd = f"{cmd} {' '.join(test_files)}"

        try:
            logging.info(f"Running verification with command: {cmd}")
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            output = f"Command: {cmd}\nExit Code: {result.returncode}\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
            return result.returncode == 0, output
            
        except subprocess.TimeoutExpired:
            return False, "Verification timed out after 300s."
        except Exception as e:
            return False, f"Verification failed to run: {str(e)}"
