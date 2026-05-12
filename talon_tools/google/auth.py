"""
Google API auth — shared OAuth2 credential management.

Credential/token file paths are configurable via environment variables:
    GOOGLE_CREDENTIALS_FILE  — path to OAuth client secrets JSON
    GOOGLE_TOKEN_FILE        — path to persisted OAuth token (encrypted)

Tokens are encrypted at rest via AES-256 (Fernet). See credential_store.py.

Defaults to ~/.config/talon-google/ if not set.

First-time setup / re-auth:
    python -m talon_tools.google.auth
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from talon_tools.credentials import get as cred

_REPO_DIR = Path.cwd() / "talon" / "google"  # bot runs from repo root
_FALLBACK_DIR = Path.home() / ".config" / "talon-google"

def _resolve(env_key: str, filename: str) -> Path:
    val = cred(env_key, "")
    if val:
        return Path(val)
    repo = _REPO_DIR / filename
    if repo.exists():
        return repo
    return _FALLBACK_DIR / filename

CREDENTIALS_FILE = _resolve("GOOGLE_CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE = _resolve("GOOGLE_TOKEN_FILE", "token.json")

SCOPES = [
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/photoslibrary.readonly",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/youtube",
]


def get_credentials(token_file: Path | str | None = None) -> Credentials:
    """Return valid Google OAuth credentials, refreshing if needed.

    Args:
        token_file: Optional path to a specific token file. If None, uses
                    the global TOKEN_FILE (from env or default location).
                    Can point to token.json (legacy) or token.enc (encrypted).
    """
    from .credential_store import load_token, save_token

    tf = Path(token_file) if token_file else TOKEN_FILE
    creds = None

    token_json = load_token(tf)
    if token_json:
        creds = Credentials.from_authorized_user_info(
            json.loads(token_json), SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            save_token(creds.to_json(), tf)
        else:
            raise RuntimeError(
                f"Google token missing or revoked at {tf}. "
                "Run: python -m talon_tools.google.auth"
            )

    return creds


def authorize_interactive(token_file: Path | str | None = None) -> Credentials:
    """Run the full OAuth flow (opens browser). Use for initial setup / re-auth.

    Args:
        token_file: Where to save the token. Defaults to global TOKEN_FILE.
    """
    from .credential_store import save_token

    tf = Path(token_file) if token_file else TOKEN_FILE
    # Re-resolve credentials file (env var may have been set by setup.py)
    creds_file = _resolve("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    if not creds_file.exists():
        raise FileNotFoundError(
            f"OAuth client secrets not found: {creds_file}\n"
            f"Set GOOGLE_CREDENTIALS_FILE env var or place credentials.json in {_FALLBACK_DIR}"
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)
    enc_path = save_token(creds.to_json(), tf)
    print(f"\nToken saved to {enc_path} (encrypted)")
    return creds


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Authorize Google account")
    parser.add_argument(
        "--agent",
        help="Agent name (stores token in agents/<name>/google/token.json)",
    )
    parser.add_argument(
        "--token-file",
        help="Explicit path for the token file",
    )
    args = parser.parse_args()

    if args.agent:
        from pathlib import Path as P
        target = P.cwd() / "agents" / args.agent / "google" / "token.json"
        print(f"Authorizing for agent: {args.agent}")
        print(f"Token will be saved to: {target}")
        authorize_interactive(target)
    elif args.token_file:
        authorize_interactive(args.token_file)
    else:
        authorize_interactive()
