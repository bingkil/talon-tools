"""
Google API auth — shared OAuth2 credential management.

Credential/token file paths are configurable via environment variables:
    GOOGLE_CREDENTIALS_FILE  — path to OAuth client secrets JSON
    GOOGLE_TOKEN_FILE        — path to persisted OAuth token (encrypted)

Tokens are encrypted at rest via AES-256 (Fernet). See credential_store.py.

Credentials are scoped per-flock or per-agent — there is no global fallback.
Run `talon auth google --flock <path>` to set up.

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

def _resolve(env_key: str, filename: str) -> Path | None:
    """Resolve a credential file. Returns None if not found (no global fallback)."""
    val = cred(env_key, "")
    if val:
        return Path(val)
    repo = _REPO_DIR / filename
    if repo.exists():
        return repo
    return None

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
        token_file: Path to a specific token file (per-agent or per-flock).
                    Can point to token.json (legacy) or token.enc (encrypted).
    """
    from .credential_store import load_token, save_token

    tf = Path(token_file) if token_file else TOKEN_FILE
    if not tf:
        raise RuntimeError(
            "No Google token file specified. "
            "Run 'talon auth google --flock <path>' to set up."
        )
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
                "Run: talon auth google --flock <path>"
            )

    return creds


def _resolve_credentials(token_file: Path | None = None) -> Path | None:
    """Find credentials.json scoped to flock or agent.

    Resolution order:
      1. GOOGLE_CREDENTIALS_FILE env var / credential store
      2. Same directory as token_file (per-agent: <flock>/<agent>/google/)
      3. Flock-level: <flock>/google/credentials.json (shared across agents)
      4. <cwd>/talon/google/credentials.json (legacy repo layout)

    No global fallback — credentials must be scoped to a flock or agent.
    """
    # 1. Explicit env var
    val = cred("GOOGLE_CREDENTIALS_FILE", "")
    if val and Path(val).exists():
        return Path(val)

    # 2. Co-located with token file (per-agent)
    if token_file:
        agent_creds = token_file.parent / "credentials.json"
        if agent_creds.exists():
            return agent_creds

        # 3. Flock-level (parent of agent dir: <flock>/<agent>/google/ -> <flock>/google/)
        flock_creds = token_file.parent.parent.parent / "google" / "credentials.json"
        if flock_creds != agent_creds and flock_creds.exists():
            return flock_creds

    # 4. Legacy repo layout
    repo = _REPO_DIR / "credentials.json"
    if repo.exists():
        return repo

    return None


def authorize_interactive(token_file: Path | str | None = None) -> Credentials:
    """Run the full OAuth flow (opens browser). Use for initial setup / re-auth.

    Args:
        token_file: Where to save the token. Defaults to global TOKEN_FILE.
    """
    from .credential_store import save_token

    tf = Path(token_file) if token_file else TOKEN_FILE
    if not tf:
        raise FileNotFoundError(
            "No token file configured. Run 'talon auth google --flock <path>' to set up."
        )
    creds_file = _resolve_credentials(tf)
    if not creds_file or not creds_file.exists():
        locations = [f"  - {tf.parent / 'credentials.json'} (local)"]
        raise FileNotFoundError(
            f"OAuth client secrets not found.\n"
            f"Looked in:\n"
            + "\n".join(locations) + "\n"
            f"Run 'talon auth google --flock <path>' to set up."
        )

    # Extract project ID for helpful error messages
    project_id = None
    try:
        creds_data = json.loads(creds_file.read_text(encoding="utf-8"))
        project_id = creds_data.get("installed", {}).get("project_id")
    except Exception:
        pass

    # Show test user reminder before opening browser
    if project_id:
        print(f"\n  ℹ  If you see 'Access blocked' in the browser, add your Google")
        print(f"     account as a test user in the GCP console:")
        print(f"     https://console.cloud.google.com/auth/audience?project={project_id}")
        print(f"     → Under 'Test users', click 'Add users' → enter your Gmail → Save")
        print()

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
    try:
        creds = flow.run_local_server(port=0, open_browser=True)
    except Exception as e:
        error_msg = str(e).lower()
        if "access_denied" in error_msg or "blocked" in error_msg:
            print("\n  ✗ Access was denied by Google.")
            print("    Your app's OAuth consent screen is in Testing mode.")
            print("    You must add your Google account as a test user.\n")
            if project_id:
                print(f"    1. Go to: https://console.cloud.google.com/auth/audience?project={project_id}")
                print(f"    2. Under 'Test users', click 'Add users'")
                print(f"    3. Enter your Gmail address and save")
                print(f"    4. Run 'talon auth google' again\n")
            else:
                print("    1. Go to: https://console.cloud.google.com/auth/audience")
                print("    2. Select your project")
                print("    3. Under 'Test users', click 'Add users'")
                print("    4. Enter your Gmail address and save")
                print("    5. Run 'talon auth google' again\n")
            raise
        raise

    enc_path = save_token(creds.to_json(), tf)
    print(f"\nToken saved to {enc_path} (encrypted)")
    return creds


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Authorize Google account")
    parser.add_argument(
        "--agent",
        help="Agent name (stores token in <flock>/<name>/google/token.json)",
    )
    parser.add_argument(
        "--flock",
        help="Path to the flock directory (default: current directory)",
    )
    parser.add_argument(
        "--token-file",
        help="Explicit path for the token file",
    )
    args = parser.parse_args()

    if args.agent:
        from pathlib import Path as P
        flock = P(args.flock).resolve() if args.flock else P.cwd()
        target = flock / args.agent / "google" / "token.json"
        print(f"Authorizing for agent: {args.agent}")
        print(f"Flock: {flock}")
        print(f"Token will be saved to: {target}")
        authorize_interactive(target)
    elif args.token_file:
        authorize_interactive(args.token_file)
    else:
        authorize_interactive()
