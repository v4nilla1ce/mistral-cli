"""Backup management and indexing for undo support."""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import get_backup_dir


def get_backup_index_path() -> Path:
    """Get the path to the backup index file."""
    return get_backup_dir() / "index.json"


def load_backup_index() -> list[dict]:
    """Load the backup index from disk.

    Returns:
        List of backup entries, each with timestamp, original_path, backup_path.
    """
    index_path = get_backup_index_path()
    if not index_path.exists():
        return []

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logging.warning(f"Failed to load backup index: {e}")
        return []


def save_backup_index(entries: list[dict]) -> bool:
    """Save the backup index to disk.

    Args:
        entries: List of backup entries.

    Returns:
        True if successful, False otherwise.
    """
    index_path = get_backup_index_path()
    index_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)
        return True
    except IOError as e:
        logging.error(f"Failed to save backup index: {e}")
        return False


def add_backup_entry(original_path: str, backup_path: str) -> bool:
    """Add a new backup entry to the index.

    Args:
        original_path: The original file path.
        backup_path: The backup file path.

    Returns:
        True if successful, False otherwise.
    """
    entries = load_backup_index()

    entry = {
        "timestamp": datetime.now().isoformat(),
        "original_path": str(Path(original_path).resolve()),
        "backup_path": str(Path(backup_path).resolve()),
    }

    entries.append(entry)
    return save_backup_index(entries)


def get_last_backup(file_path: Optional[str] = None) -> Optional[dict]:
    """Get the most recent backup entry.

    Args:
        file_path: Optional filter by original file path.

    Returns:
        The most recent backup entry, or None if no backups exist.
    """
    entries = load_backup_index()
    if not entries:
        return None

    if file_path:
        resolved_path = str(Path(file_path).resolve())
        entries = [e for e in entries if e["original_path"] == resolved_path]

    if not entries:
        return None

    # Sort by timestamp descending and return the most recent
    entries.sort(key=lambda x: x["timestamp"], reverse=True)
    return entries[0]


def restore_backup(entry: dict) -> tuple[bool, str]:
    """Restore a file from a backup entry.

    Args:
        entry: The backup entry to restore.

    Returns:
        Tuple of (success, message).
    """
    backup_path = Path(entry["backup_path"])
    original_path = Path(entry["original_path"])

    if not backup_path.exists():
        return False, f"Backup file not found: {backup_path}"

    try:
        # Create parent directories if needed
        original_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy backup to original location
        shutil.copy(backup_path, original_path)
        logging.info(f"Restored {original_path} from {backup_path}")

        return True, f"Restored {original_path}"
    except IOError as e:
        error_msg = f"Failed to restore backup: {e}"
        logging.error(error_msg)
        return False, error_msg


def remove_backup_entry(entry: dict) -> bool:
    """Remove a backup entry from the index (does not delete the file).

    Args:
        entry: The backup entry to remove.

    Returns:
        True if successful, False otherwise.
    """
    entries = load_backup_index()
    entries = [
        e
        for e in entries
        if not (
            e["timestamp"] == entry["timestamp"]
            and e["original_path"] == entry["original_path"]
        )
    ]
    return save_backup_index(entries)


def list_backups(file_path: Optional[str] = None, limit: int = 10) -> list[dict]:
    """List backup entries.

    Args:
        file_path: Optional filter by original file path.
        limit: Maximum number of entries to return.

    Returns:
        List of backup entries, most recent first.
    """
    entries = load_backup_index()

    if file_path:
        resolved_path = str(Path(file_path).resolve())
        entries = [e for e in entries if e["original_path"] == resolved_path]

    # Sort by timestamp descending
    entries.sort(key=lambda x: x["timestamp"], reverse=True)
    return entries[:limit]


def clean_old_backups(days: int = 30) -> tuple[int, int]:
    """Remove backup entries older than specified days.

    Args:
        days: Remove backups older than this many days.

    Returns:
        Tuple of (entries_removed, files_deleted).
    """
    from datetime import timedelta

    entries = load_backup_index()
    cutoff = datetime.now() - timedelta(days=days)

    entries_to_keep = []
    entries_removed = 0
    files_deleted = 0

    for entry in entries:
        entry_time = datetime.fromisoformat(entry["timestamp"])
        if entry_time >= cutoff:
            entries_to_keep.append(entry)
        else:
            entries_removed += 1
            # Optionally delete the backup file
            backup_path = Path(entry["backup_path"])
            if backup_path.exists():
                try:
                    backup_path.unlink()
                    files_deleted += 1
                except IOError:
                    pass

    save_backup_index(entries_to_keep)
    return entries_removed, files_deleted
