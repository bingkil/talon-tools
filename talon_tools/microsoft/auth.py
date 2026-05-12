"""
Microsoft Graph API auth — MSAL token management.

Tokens are encrypted at rest via AES-256 (Fernet). See credential_store.py.

Uses the Microsoft Graph PowerShell client ID by default (first-party,
pre-registered in most tenants). Override via environment variables:
    MS_CLIENT_ID       — Azure AD application (client) ID
    MS_TENANT_ID       — Azure AD tenant ID
    MS_TOKEN_FILE      — Path to persisted token cache

Defaults to talon/microsoft/ in the repo root, then ~/.config/talon-microsoft/.

First-time setup / re-auth:
    python -m talon_microsoft.auth
"""

from __future__ import annotations

from pathlib import Path

import msal
from talon_tools.credentials import get as cred
from talon_tools.credential_store import save_encrypted, load_encrypted

_REPO_DIR = Path.cwd() / "talon" / "microsoft"
_FALLBACK_DIR = Path.home() / ".config" / "talon-microsoft"

# Microsoft Graph PowerShell (first-party, widely pre-consented)
_DEFAULT_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
_DEFAULT_TENANT_ID = "common"  # multi-tenant; override with MS_TENANT_ID env var

SCOPES = [
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/Calendars.Read",
    "https://graph.microsoft.com/Chat.Read",
    "https://graph.microsoft.com/Team.ReadBasic.All",
    "https://graph.microsoft.com/Channel.ReadBasic.All",
    "https://graph.microsoft.com/User.Read",
]

# MS Graph base URL
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _token_path() -> Path:
    val = cred("MS_TOKEN_FILE", "")
    if val:
        return Path(val)
    repo = _REPO_DIR / "token.json"
    if repo.exists():
        return repo
    return _FALLBACK_DIR / "token.json"


def _build_app() -> msal.PublicClientApplication:
    """Build an MSAL public client app with token cache."""
    client_id = cred("MS_CLIENT_ID", _DEFAULT_CLIENT_ID)
    tenant_id = cred("MS_TENANT_ID", _DEFAULT_TENANT_ID)

    cache = msal.SerializableTokenCache()
    token_path = _token_path()
    cached = load_encrypted(token_path)
    if cached:
        cache.deserialize(cached)

    app = msal.PublicClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        token_cache=cache,
    )
    return app


def _save_cache(app: msal.PublicClientApplication) -> None:
    """Persist the token cache (encrypted) if it changed."""
    cache = app.token_cache
    if cache.has_state_changed:
        token_path = _token_path()
        save_encrypted(cache.serialize(), token_path)


def get_token() -> str:
    """Return a valid Microsoft Graph access token, refreshing silently if needed."""
    app = _build_app()
    accounts = app.get_accounts()

    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _save_cache(app)
            return result["access_token"]

    raise RuntimeError(
        "Microsoft token missing or expired. Run: python -m talon_microsoft.auth"
    )


def authorize_interactive() -> str:
    """Run the device-code OAuth flow for first-time auth."""
    app = _build_app()

    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Device flow failed: {flow.get('error_description', flow)}")

    print("\n" + "=" * 60)
    print("To sign in, open a browser to:")
    print(f"  {flow['verification_uri']}")
    print(f"  Enter code: {flow['user_code']}")
    print("=" * 60 + "\n")

    result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise RuntimeError(
            f"Auth failed: {result.get('error_description', result.get('error', 'unknown'))}"
        )

    _save_cache(app)
    token_path = _token_path()
    print(f"Token cached to {token_path}")
    return result["access_token"]


if __name__ == "__main__":
    authorize_interactive()
