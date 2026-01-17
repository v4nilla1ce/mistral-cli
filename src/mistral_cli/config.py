"""Global configuration management for Mistral CLI.

Implements XDG-compliant config paths:
- Windows: %LOCALAPPDATA%\\mistral-cli\\
- Unix: ~/.config/mistral-cli/ (config), ~/.local/share/mistral-cli/ (data)

Config precedence (highest to lowest):
1. CLI argument (--api-key)
2. Environment variable (MISTRAL_API_KEY)
3. Global config file
4. Local .env (development override)
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv


def get_config_dir() -> Path:
    """Get the platform-specific config directory."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
        return Path(base) / "mistral-cli"
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        return Path(xdg_config) / "mistral-cli"


def get_data_dir() -> Path:
    """Get the platform-specific data directory (logs, backups)."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
        return Path(base) / "mistral-cli"
    else:
        xdg_data = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        return Path(xdg_data) / "mistral-cli"


def get_log_dir() -> Path:
    """Get the directory for log files."""
    return get_data_dir() / "logs"


def get_backup_dir() -> Path:
    """Get the directory for backup files."""
    return get_data_dir() / "backups"


def get_config_file() -> Path:
    """Get the path to the config file."""
    return get_config_dir() / "config.json"


def ensure_dirs() -> None:
    """Ensure all required directories exist."""
    get_config_dir().mkdir(parents=True, exist_ok=True)
    get_log_dir().mkdir(parents=True, exist_ok=True)
    get_backup_dir().mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    """Load configuration from the config file."""
    config_file = get_config_file()
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_config(config: dict[str, Any]) -> bool:
    """Save configuration to the config file."""
    ensure_dirs()
    config_file = get_config_file()
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        return True
    except OSError:
        return False


def get_api_key(cli_key: Optional[str] = None) -> Optional[str]:
    """Get API key using precedence: CLI arg > env var > config file > local .env.

    Args:
        cli_key: API key passed via CLI argument (highest priority)

    Returns:
        The API key if found, None otherwise.
    """
    # 1. CLI argument (highest priority)
    if cli_key:
        return cli_key

    # 2. Environment variable
    env_key = os.environ.get("MISTRAL_API_KEY")
    if env_key:
        return env_key

    # 3. Global config file
    config = load_config()
    config_key = config.get("api_key")
    if config_key:
        return config_key

    # 4. Local .env (development override, lowest priority)
    load_dotenv()
    return os.environ.get("MISTRAL_API_KEY")


def get_config_source(cli_key: Optional[str] = None) -> str:
    """Identify where the API key is being loaded from.

    Returns a human-readable string indicating the source.
    """
    if cli_key:
        return "CLI argument"

    if os.environ.get("MISTRAL_API_KEY"):
        return "Environment variable (MISTRAL_API_KEY)"

    config = load_config()
    if config.get("api_key"):
        return f"Config file ({get_config_file()})"

    # Check if .env exists and has the key
    load_dotenv()
    if os.environ.get("MISTRAL_API_KEY"):
        return "Local .env file"

    return "Not configured"


def get_system_prompt() -> Optional[str]:
    """Get the custom system prompt from config.

    Returns:
        The custom system prompt if configured, None otherwise.
    """
    config = load_config()
    return config.get("system_prompt")


def set_system_prompt(prompt: Optional[str]) -> bool:
    """Set or clear the custom system prompt.

    Args:
        prompt: The system prompt to set, or None to clear.

    Returns:
        True if successful, False otherwise.
    """
    config = load_config()
    if prompt:
        config["system_prompt"] = prompt
    elif "system_prompt" in config:
        del config["system_prompt"]
    return save_config(config)


def get_default_model() -> str:
    """Get the default model from config.

    Returns:
        The configured default model, or 'mistral-small'.
    """
    config = load_config()
    return config.get("default_model", "mistral-small")


def get_profiles_dir() -> Path:
    """Get the directory for conversation profiles."""
    profiles_dir = get_data_dir() / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    return profiles_dir


def save_profile(name: str, profile_data: dict[str, Any]) -> tuple[bool, str]:
    """Save a conversation profile.

    Args:
        name: Profile name.
        profile_data: Dict with 'system_prompt', 'files', 'model' keys.

    Returns:
        Tuple of (success, message).
    """
    try:
        profile_path = get_profiles_dir() / f"{name}.json"
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(profile_data, f, indent=2)
        return True, f"Profile saved: {name}"
    except Exception as e:
        return False, f"Failed to save profile: {e}"


def load_profile(name: str) -> tuple[bool, Optional[dict[str, Any]], str]:
    """Load a conversation profile.

    Args:
        name: Profile name to load.

    Returns:
        Tuple of (success, profile_data, message).
    """
    try:
        profile_path = get_profiles_dir() / f"{name}.json"
        if not profile_path.exists():
            return False, None, f"Profile not found: {name}"

        with open(profile_path, "r", encoding="utf-8") as f:
            profile_data = json.load(f)
        return True, profile_data, f"Profile loaded: {name}"
    except Exception as e:
        return False, None, f"Failed to load profile: {e}"


def list_profiles() -> list[str]:
    """List all saved profiles.

    Returns:
        List of profile names.
    """
    profiles_dir = get_profiles_dir()
    return [p.stem for p in profiles_dir.glob("*.json")]


def delete_profile(name: str) -> tuple[bool, str]:
    """Delete a conversation profile.

    Args:
        name: Profile name to delete.

    Returns:
        Tuple of (success, message).
    """
    try:
        profile_path = get_profiles_dir() / f"{name}.json"
        if not profile_path.exists():
            return False, f"Profile not found: {name}"
        profile_path.unlink()
        return True, f"Profile deleted: {name}"
    except Exception as e:
        return False, f"Failed to delete profile: {e}"
