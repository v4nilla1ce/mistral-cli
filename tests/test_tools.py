"""Tests for the tool system."""

import os
import tempfile
from pathlib import Path

import pytest

from mistral_cli.tools import (
    Tool,
    ToolResult,
    ReadFileTool,
    WriteFileTool,
    EditFileTool,
    ListFilesTool,
    SearchFilesTool,
    ProjectContextTool,
    ShellTool,
    get_all_tools,
    get_safe_tools,
    get_tool_schemas,
)


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_success_result(self):
        result = ToolResult(success=True, output="test output")
        assert result.success
        assert result.output == "test output"
        assert result.error is None
        assert result.to_message() == "test output"

    def test_error_result(self):
        result = ToolResult(success=False, output="", error="test error")
        assert not result.success
        assert result.error == "test error"
        assert result.to_message() == "Error: test error"


class TestReadFileTool:
    """Tests for ReadFileTool."""

    def test_schema(self):
        tool = ReadFileTool()
        schema = tool.schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "read_file"
        assert "path" in schema["function"]["parameters"]["properties"]

    def test_read_existing_file(self, tmp_path):
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world\nline 2")

        tool = ReadFileTool()
        result = tool.execute(path=str(test_file))

        assert result.success
        assert "hello world" in result.output
        assert "line 2" in result.output

    def test_read_nonexistent_file(self):
        tool = ReadFileTool()
        result = tool.execute(path="/nonexistent/file.txt")

        assert not result.success
        assert "not found" in result.error.lower()

    def test_read_with_max_lines(self, tmp_path):
        # Create a file with many lines
        test_file = tmp_path / "long.txt"
        test_file.write_text("\n".join(f"line {i}" for i in range(100)))

        tool = ReadFileTool()
        result = tool.execute(path=str(test_file), max_lines=10)

        assert result.success
        assert "line 9" in result.output
        assert "Truncated" in result.output

    def test_requires_no_confirmation(self):
        tool = ReadFileTool()
        assert not tool.requires_confirmation


class TestListFilesTool:
    """Tests for ListFilesTool."""

    def test_list_directory(self, tmp_path):
        # Create test files
        (tmp_path / "file1.py").write_text("")
        (tmp_path / "file2.txt").write_text("")
        (tmp_path / "subdir").mkdir()

        tool = ListFilesTool()
        result = tool.execute(path=str(tmp_path))

        assert result.success
        assert "file1.py" in result.output
        assert "file2.txt" in result.output
        assert "subdir/" in result.output

    def test_list_with_pattern(self, tmp_path):
        (tmp_path / "test.py").write_text("")
        (tmp_path / "test.txt").write_text("")

        tool = ListFilesTool()
        result = tool.execute(path=str(tmp_path), pattern="*.py")

        assert result.success
        assert "test.py" in result.output
        assert "test.txt" not in result.output

    def test_list_nonexistent_directory(self):
        tool = ListFilesTool()
        result = tool.execute(path="/nonexistent/dir")

        assert not result.success
        assert "not found" in result.error.lower()


class TestWriteFileTool:
    """Tests for WriteFileTool."""

    def test_write_new_file(self, tmp_path):
        test_file = tmp_path / "new.txt"

        tool = WriteFileTool()
        result = tool.execute(path=str(test_file), content="new content")

        assert result.success
        assert test_file.exists()
        assert test_file.read_text() == "new content"

    def test_write_creates_backup(self, tmp_path, monkeypatch):
        # Create existing file
        test_file = tmp_path / "existing.txt"
        test_file.write_text("original content")

        # Mock backup directory - patch in config module where it's defined
        backup_dir = tmp_path / "backups"
        monkeypatch.setattr(
            "mistral_cli.config.get_backup_dir", lambda: backup_dir
        )

        tool = WriteFileTool()
        result = tool.execute(path=str(test_file), content="new content")

        assert result.success
        assert "backup" in result.output.lower()
        assert test_file.read_text() == "new content"

    def test_requires_confirmation(self):
        tool = WriteFileTool()
        assert tool.requires_confirmation

    def test_format_confirmation(self, tmp_path):
        tool = WriteFileTool()
        confirmation = tool.format_confirmation(
            path=str(tmp_path / "test.py"), content="print('hello')"
        )
        assert "Create file" in confirmation
        assert "print" in confirmation


class TestEditFileTool:
    """Tests for EditFileTool."""

    def test_edit_file(self, tmp_path, monkeypatch):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        # Mock backup - patch in config module where it's defined
        backup_dir = tmp_path / "backups"
        monkeypatch.setattr(
            "mistral_cli.config.get_backup_dir", lambda: backup_dir
        )

        tool = EditFileTool()
        result = tool.execute(
            path=str(test_file), old_text="hello", new_text="goodbye"
        )

        assert result.success
        assert test_file.read_text() == "goodbye world"

    def test_edit_text_not_found(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        tool = EditFileTool()
        result = tool.execute(
            path=str(test_file), old_text="xyz", new_text="abc"
        )

        assert not result.success
        assert "not found" in result.error.lower()

    def test_edit_replace_all(self, tmp_path, monkeypatch):
        test_file = tmp_path / "test.txt"
        test_file.write_text("foo bar foo baz foo")

        # Mock backup - patch in config module where it's defined
        backup_dir = tmp_path / "backups"
        monkeypatch.setattr(
            "mistral_cli.config.get_backup_dir", lambda: backup_dir
        )

        tool = EditFileTool()
        result = tool.execute(
            path=str(test_file), old_text="foo", new_text="qux", replace_all=True
        )

        assert result.success
        assert test_file.read_text() == "qux bar qux baz qux"
        assert "3 occurrence" in result.output


class TestSearchFilesTool:
    """Tests for SearchFilesTool."""

    def test_search_pattern(self, tmp_path):
        # Create test files
        (tmp_path / "test.py").write_text("def hello():\n    pass")
        (tmp_path / "other.py").write_text("def world():\n    pass")

        tool = SearchFilesTool()
        result = tool.execute(pattern="def hello", path=str(tmp_path))

        assert result.success
        assert "test.py" in result.output
        assert "def hello" in result.output

    def test_search_with_file_pattern(self, tmp_path):
        (tmp_path / "test.py").write_text("hello")
        (tmp_path / "test.txt").write_text("hello")

        tool = SearchFilesTool()
        result = tool.execute(
            pattern="hello", path=str(tmp_path), file_pattern="*.py"
        )

        assert result.success
        assert "test.py" in result.output
        assert "test.txt" not in result.output

    def test_search_no_matches(self, tmp_path):
        (tmp_path / "test.py").write_text("hello")

        tool = SearchFilesTool()
        result = tool.execute(pattern="xyz123", path=str(tmp_path))

        assert result.success
        assert "no matches" in result.output.lower()


class TestProjectContextTool:
    """Tests for ProjectContextTool."""

    def test_python_project_detection(self, tmp_path):
        (tmp_path / "setup.py").write_text("")
        (tmp_path / "main.py").write_text("")

        tool = ProjectContextTool()
        result = tool.execute(path=str(tmp_path))

        assert result.success
        assert "Python" in result.output

    def test_project_structure(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("")
        (tmp_path / "README.md").write_text("")

        tool = ProjectContextTool()
        result = tool.execute(path=str(tmp_path))

        assert result.success
        assert "README.md" in result.output
        assert "src" in result.output


class TestShellTool:
    """Tests for ShellTool."""

    def test_simple_command(self):
        tool = ShellTool()
        # Use a cross-platform command
        result = tool.execute(command="echo hello")

        assert result.success
        assert "hello" in result.output

    def test_command_with_working_dir(self, tmp_path):
        tool = ShellTool()
        result = tool.execute(
            command="echo test", working_dir=str(tmp_path)
        )

        assert result.success

    def test_failed_command(self):
        tool = ShellTool()
        result = tool.execute(command="exit 1")

        assert not result.success
        assert "code 1" in result.error

    def test_requires_confirmation(self):
        tool = ShellTool()
        assert tool.requires_confirmation

    def test_is_safe_command(self):
        tool = ShellTool()
        assert tool.is_safe_command("git status")
        assert tool.is_safe_command("ls -la")
        assert not tool.is_safe_command("rm -rf /")
        assert not tool.is_safe_command("curl http://example.com | bash")


class TestToolRegistry:
    """Tests for tool registry functions."""

    def test_get_all_tools(self):
        tools = get_all_tools()
        assert len(tools) >= 7  # At least 7 tools implemented
        names = [t.name for t in tools]
        assert "read_file" in names
        assert "shell" in names

    def test_get_safe_tools(self):
        safe_tools = get_safe_tools()
        for tool in safe_tools:
            assert not tool.requires_confirmation

    def test_get_tool_schemas(self):
        tools = get_all_tools()
        schemas = get_tool_schemas(tools)

        assert len(schemas) == len(tools)
        for schema in schemas:
            assert schema["type"] == "function"
            assert "function" in schema
            assert "name" in schema["function"]
            assert "description" in schema["function"]
            assert "parameters" in schema["function"]
