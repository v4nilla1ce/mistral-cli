"""Basic tests for the CLI entry point."""

import pytest
from click.testing import CliRunner

from mistral_cli.cli import cli


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


def test_cli_help(runner):
    """Test that --help works."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Mistral CLI" in result.output


def test_cli_version(runner):
    """Test that --version works."""
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    # Check version format without hardcoding specific version
    assert "version" in result.output.lower()


def test_config_show(runner):
    """Test that config show command works."""
    result = runner.invoke(cli, ["config", "show"])
    assert result.exit_code == 0
    assert "Config file:" in result.output


def test_fix_help(runner):
    """Test that fix --help works."""
    result = runner.invoke(cli, ["fix", "--help"])
    assert result.exit_code == 0
    assert "dry-run" in result.output


def test_chat_help(runner):
    """Test that chat --help works."""
    result = runner.invoke(cli, ["chat", "--help"])
    assert result.exit_code == 0
    assert "model" in result.output


def test_agent_help(runner):
    """Test that agent --help works."""
    result = runner.invoke(cli, ["agent", "--help"])
    assert result.exit_code == 0
    assert "model" in result.output
    assert "confirm-all" in result.output
    assert "max-iterations" in result.output


def test_review_help(runner):
    """Test that review --help works."""
    result = runner.invoke(cli, ["review", "--help"])
    assert result.exit_code == 0
    assert "model" in result.output
