
from typing import Any, Dict, List, Optional
from ..critic import Critic
from .base import Tool, ToolResult

class CriticTool(Tool):
    """Tool to run verification (syntax checks and tests)."""

    def __init__(self, critic: Critic):
        self.critic = critic

    @property
    def name(self) -> str:
        return "critic"

    @property
    def description(self) -> str:
        return (
            "Verify code using the Critic. "
            "Supports: 'syntax' (check file syntax) and 'test' (run project tests)."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["syntax", "test"],
                    "description": "Verification action to perform.",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files to check (required for syntax, optional for test).",
                }
            },
            "required": ["action"],
        }
    
    @property
    def requires_confirmation(self) -> bool:
        # Running tests might be unsafe if they modify DB/Files, so confirm.
        # Syntax check is safe.
        return True

    def is_safe_command(self, action: str) -> bool:
        if action == "syntax":
            return True
        return False

    def execute(self, action: str, files: Optional[List[str]] = None, **kwargs) -> ToolResult:
        if action == "syntax":
            if not files:
                return ToolResult(False, "", "Files list required for syntax check.")
            
            errors = []
            for f in files:
                valid, msg = self.critic.check_syntax(f)
                if not valid:
                    errors.append(msg)
            
            if errors:
                return ToolResult(False, "\n\n".join(errors))
            return ToolResult(True, "All files passed syntax check.")

        elif action == "test":
            success, output = self.critic.run_tests(files)
            return ToolResult(success, output)

        else:
            return ToolResult(False, "", f"Unknown action: {action}")
