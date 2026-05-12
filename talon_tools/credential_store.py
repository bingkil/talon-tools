"""
Encrypted credential storage for Talon services.

Provides AES-256 encryption at rest via Fernet (cryptography package)
for any service's token/secret files. Encryption keys are stored in the
OS keyring (Windows Credential Manager / macOS Keychain / Linux
secret-service) with a file fallback for headless environments.

Each service directory gets its own encryption key, namespaced by
resolved path in the keyring.

Usage:
    from talon_tools.credential_store import save_encrypted, load_encrypted

    # Save (encrypts + removes plaintext original)
    save_encrypted(data_str, Path("flock/google/token.json"))

    # Load (decrypts; auto-migrates plaintext if found)
    data_str = load_encrypted(Path("flock/google/token.json"))
"""

from __future__ import annotations

import logging
import os
import platform
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger(__name__)

_KEYRING_SERVICE = "talon-tools"
_KEY_FILENAME = ".encryption_key"


# ---------------------------------------------------------------------------
# Keyring namespace
# ---------------------------------------------------------------------------

def _keyring_username(directory: Path) -> str:
    """Per-directory keyring entry: 'encryption-key:<resolved-path>'."""
    return f"encryption-key:{directory.resolve()}"


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

def _keyring_available() -> bool:
    """Check if the keyring backend is usable (not the fallback null backend)."""
    try:
        import keyring
        backend = keyring.get_keyring()
        name = type(backend).__name__
        if "fail" in name.lower() or "null" in name.lower():
            return False
        return True
    except Exception:
        return False


def _get_key_from_keyring(directory: Path) -> bytes | None:
    """Try to read the encryption key from the OS keyring."""
    try:
        import keyring
        username = _keyring_username(directory)
        stored = keyring.get_password(_KEYRING_SERVICE, username)
        if stored:
            return stored.encode("utf-8")
    except Exception as e:
        log.debug("Keyring read failed: %s", e)
    return None


def _set_key_in_keyring(key: bytes, directory: Path) -> bool:
    """Try to store the encryption key in the OS keyring."""
    try:
        import keyring
        username = _keyring_username(directory)
        keyring.set_password(_KEYRING_SERVICE, username, key.decode("utf-8"))
        return True
    except Exception as e:
        log.debug("Keyring write failed: %s", e)
        return False


def _get_key_from_file(directory: Path) -> bytes | None:
    """Read encryption key from the fallback key file."""
    kf = directory / _KEY_FILENAME
    if kf.exists():
        return kf.read_text().strip().encode("utf-8")
    return None


def _save_key_to_file(directory: Path, key: bytes) -> None:
    """Save encryption key to a file with restricted permissions."""
    kf = directory / _KEY_FILENAME
    kf.parent.mkdir(parents=True, exist_ok=True)
    kf.write_text(key.decode("utf-8"))
    if platform.system() != "Windows":
        kf.chmod(0o600)
    else:
        _restrict_windows_acl(kf)


def _restrict_windows_acl(path: Path) -> None:
    """On Windows, restrict file to current user only via icacls."""
    try:
        import subprocess
        user = os.environ.get("USERNAME", "")
        if user:
            subprocess.run(
                ["icacls", str(path), "/inheritance:r",
                 "/grant:r", f"{user}:(R,W)"],
                capture_output=True, check=False,
            )
    except Exception as e:
        log.debug("Windows ACL restriction failed: %s", e)


def get_or_create_key(directory: Path) -> bytes:
    """Get the encryption key for a directory, creating one if needed.

    Priority:
        1. OS keyring (per-directory)
        2. Key file at <directory>/.encryption_key
        3. Generate new key → store in keyring + file
    """
    # 1. Try keyring
    key = _get_key_from_keyring(directory)
    if key:
        return key

    # 2. Try key file
    key = _get_key_from_file(directory)
    if key:
        if _keyring_available():
            _set_key_in_keyring(key, directory)
        return key

    # 3. Generate new key
    key = Fernet.generate_key()
    stored = False
    if _keyring_available():
        stored = _set_key_in_keyring(key, directory)
    _save_key_to_file(directory, key)
    if stored:
        log.info("Encryption key stored in OS keyring + file backup")
    else:
        log.info("Encryption key stored in file (keyring unavailable)")
    return key


# ---------------------------------------------------------------------------
# Encrypt / decrypt raw data
# ---------------------------------------------------------------------------

def encrypt(data: str, directory: Path) -> bytes:
    """Encrypt a string. Returns Fernet ciphertext bytes."""
    key = get_or_create_key(directory)
    return Fernet(key).encrypt(data.encode("utf-8"))


def decrypt(ciphertext: bytes, directory: Path) -> str:
    """Decrypt Fernet ciphertext. Returns the original string."""
    key = get_or_create_key(directory)
    return Fernet(key).decrypt(ciphertext).decode("utf-8")


# ---------------------------------------------------------------------------
# File I/O — save/load encrypted files with auto-migration
# ---------------------------------------------------------------------------

def save_encrypted(data: str, logical_path: Path, enc_suffix: str = ".enc") -> Path:
    """Encrypt and save data, replacing any plaintext original.

    Args:
        data: The data string to encrypt (typically JSON).
        logical_path: The *logical* file path (e.g. flock/google/token.json).
                      The encrypted file uses the same stem + enc_suffix.
        enc_suffix: Suffix for the encrypted file (default ".enc").

    Returns:
        Path to the encrypted file.
    """
    directory = logical_path.parent
    enc_path = logical_path.with_suffix(enc_suffix)
    directory.mkdir(parents=True, exist_ok=True)

    ciphertext = encrypt(data, directory)
    enc_path.write_bytes(ciphertext)

    if platform.system() != "Windows":
        enc_path.chmod(0o600)
    else:
        _restrict_windows_acl(enc_path)

    # Remove plaintext original if it exists (migration)
    if logical_path.exists() and logical_path != enc_path:
        logical_path.unlink()
        log.info("Removed plaintext %s (migrated to %s)", logical_path.name, enc_path.name)

    return enc_path


def load_encrypted(logical_path: Path, enc_suffix: str = ".enc") -> str | None:
    """Load and decrypt a file, with auto-migration from plaintext.

    Checks for the encrypted file first, falls back to plaintext.
    If a plaintext file is found, auto-migrates it to encrypted.

    Args:
        logical_path: The logical file path (e.g. flock/google/token.json).
        enc_suffix: Suffix for the encrypted file (default ".enc").

    Returns:
        Decrypted data string, or None if no file exists.
    """
    directory = logical_path.parent
    enc_path = logical_path.with_suffix(enc_suffix)

    # Prefer encrypted file
    if enc_path.exists():
        try:
            return decrypt(enc_path.read_bytes(), directory)
        except InvalidToken:
            log.error("Failed to decrypt %s — key may have changed", enc_path)
            return None

    # Fall back to plaintext and auto-migrate
    if logical_path.exists():
        log.info("Found plaintext %s — migrating to encrypted storage", logical_path.name)
        data = logical_path.read_text()
        try:
            save_encrypted(data, logical_path, enc_suffix)
            return data
        except Exception as e:
            log.warning("Migration failed, using plaintext: %s", e)
            return data

    return None
