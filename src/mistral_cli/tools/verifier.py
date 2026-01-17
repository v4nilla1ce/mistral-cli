"""Tool for running verification tests."""

from typing import Any, Dict, List, Optional

from ..verifier import Verifier
from .base import Tool, ToolResult


class VerifyTool(Tool):
    """Tool to run project tests/verification."""

    def __init__(self, verifier: Verifier):
        self.verifier = verifier

    @property
    def name(self) -> str:
        return "verify_change"

    @property
    def description(self) -> str:
        return (
            "Run local tests to verify changes. "
            "Use this after modifying code to ensure you haven't broken anything. "
            "Returns the test output (pass/fail)."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of files to verify (optional optimization).",
                }
            },
        }

    def execute(self, files: Optional[List[str]] = None) -> ToolResult:
        success, output = self.verifier.run_tests(files)
        return ToolResult(success, output)
