"""
Google-specific credential storage — delegates to talon_tools.credential_store.

Preserves the existing API (save_token, load_token) so auth.py and setup.py
don't need changes. Handles migration of the old 'talon-google' keyring
entries to the new 'talon-tools' namespace.
"""

from __future__ import annotations

import logging
from pathlib import Path

from talon_tools.credential_store import (
    save_encrypted,
    load_encrypted,
    _set_key_in_keyring as _set_key_new,
)

log = logging.getLogger(__name__)

_OLD_KEYRING_SERVICE = "talon-google"


def _migrate_keyring_entry(google_dir: Path) -> None:
    """One-time migration: move key from old 'talon-google' service to 'talon-tools'."""
    try:
        import keyring
        old_username = f"encryption-key:{google_dir.resolve()}"
        old_key = keyring.get_password(_OLD_KEYRING_SERVICE, old_username)
        if old_key:
            _set_key_new(old_key.encode("utf-8"), google_dir)
            keyring.delete_password(_OLD_KEYRING_SERVICE, old_username)
            log.info("Migrated keyring entry from '%s' to 'talon-tools'", _OLD_KEYRING_SERVICE)
    except Exception as e:
        log.debug("Keyring migration skipped: %s", e)


def save_token(token_json: str, token_path: Path) -> Path:
    """Encrypt and save a Google OAuth token.

    Args:
        token_json: The token as a JSON string (from creds.to_json()).
        token_path: The *logical* token path (e.g. <flock>/google/token.json).

    Returns:
        Path to the encrypted file.
    """
    _migrate_keyring_entry(token_path.parent)
    return save_encrypted(token_json, token_path)


def load_token(token_path: Path) -> str | None:
    """Load and decrypt a Google OAuth token.

    Args:
        token_path: The logical token path (e.g. <flock>/google/token.json).

    Returns:
        Token JSON string, or None if no token file exists.
    """
    _migrate_keyring_entry(token_path.parent)
    return load_encrypted(token_path)
