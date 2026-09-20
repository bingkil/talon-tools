"""
Microsoft Graph API auth — MSAL token management.

Tokens are encrypted at rest via AES-256 (Fernet). See credential_store.py.

Uses the Microsoft Graph PowerShell client ID by default (first-party,
pre-registered in most tenants). Override via environment variables:
    MS_CLIENT_ID       — Azure AD application (client) ID
    MS_TENANT_ID       — Azure AD tenant ID

Per-service credential keys:
    MS_MAIL_TOKEN      — Outlook mail token cache
    MS_CALENDAR_TOKEN  — Calendar token cache
    MS_ONEDRIVE_TOKEN  — OneDrive token cache

First-time setup / re-auth:
    python -m talon_tools.microsoft.auth [mail|onedrive]
"""

from __future__ import annotations

import json
import sys
import msal
from talon_tools.credentials import get as cred, set_credential

# Microsoft Graph PowerShell (first-party, widely pre-consented)
_DEFAULT_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
_DEFAULT_TENANT_ID = "common"  # multi-tenant; override with MS_TENANT_ID env var

# Per-service scope definitions
MAIL_SCOPES = [
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/User.Read",
]

CALENDAR_SCOPES = [
    "https://graph.microsoft.com/Calendars.Read",
    "https://graph.microsoft.com/User.Read",
]

ONEDRIVE_SCOPES = [
    "https://graph.microsoft.com/Files.Read",
    "https://graph.microsoft.com/User.Read",
]

# Service → (credential key, scopes)
_SERVICES = {
    "mail": ("MS_MAIL_TOKEN", MAIL_SCOPES),
    "calendar": ("MS_CALENDAR_TOKEN", CALENDAR_SCOPES),
    "onedrive": ("MS_ONEDRIVE_TOKEN", ONEDRIVE_SCOPES),
}

# Union of every service's scopes — one device-code sign-in that consents to
# all of them at once produces a single cache that satisfies acquire_token_silent
# for each individual service's narrower scope subset (see run_device_flow_emit_json).
ALL_SCOPES = sorted(set(MAIL_SCOPES + CALENDAR_SCOPES + ONEDRIVE_SCOPES))

# Legacy fallback key (if MS_MAIL_TOKEN not found, try MS_TOKEN_CACHE)
_LEGACY_KEY = "MS_TOKEN_CACHE"

# MS Graph base URL
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _build_app(cache_key: str) -> msal.PublicClientApplication:
    """Build an MSAL public client app with token cache for a specific service."""
    client_id = cred("MS_CLIENT_ID", _DEFAULT_CLIENT_ID)
    tenant_id = cred("MS_TENANT_ID", _DEFAULT_TENANT_ID)

    cache = msal.SerializableTokenCache()
    cached = cred(cache_key, "")
    # Fallback to legacy key for mail
    if not cached and cache_key == "MS_MAIL_TOKEN":
        cached = cred(_LEGACY_KEY, "")
    if cached:
        cache.deserialize(cached)

    app = msal.PublicClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        token_cache=cache,
    )
    return app


def _save_cache(app: msal.PublicClientApplication, cache_key: str) -> None:
    """Persist the token cache if it changed."""
    cache = app.token_cache
    if cache.has_state_changed:
        set_credential(cache_key, cache.serialize())


def get_token(service: str = "mail") -> str:
    """Return a valid Microsoft Graph access token for a service.

    Args:
        service: "mail" or "onedrive"
    """
    if service not in _SERVICES:
        raise ValueError(f"Unknown service: {service}. Use: {list(_SERVICES.keys())}")

    cache_key, scopes = _SERVICES[service]
    app = _build_app(cache_key)
    accounts = app.get_accounts()

    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])
        if result and "access_token" in result:
            _save_cache(app, cache_key)
            return result["access_token"]

    raise RuntimeError(
        f"Microsoft {service} token missing or expired. "
        f"Run: python -m talon_tools.microsoft.auth {service}"
    )


def authorize_interactive(service: str = "mail") -> str:
    """Run the device-code OAuth flow for first-time auth."""
    if service not in _SERVICES:
        raise ValueError(f"Unknown service: {service}. Use: {list(_SERVICES.keys())}")

    cache_key, scopes = _SERVICES[service]
    app = _build_app(cache_key)

    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        raise RuntimeError(f"Device flow failed: {flow.get('error_description', flow)}")

    print("\n" + "=" * 60)
    print(f"Authorizing: {service}")
    print(f"Scopes: {', '.join(s.split('/')[-1] for s in scopes)}")
    print()
    print("To sign in, open a browser to:")
    print(f"  {flow['verification_uri']}")
    print(f"  Enter code: {flow['user_code']}")
    print("=" * 60 + "\n")

    result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise RuntimeError(
            f"Auth failed: {result.get('error_description', result.get('error', 'unknown'))}"
        )

    _save_cache(app, cache_key)
    print(f"Token cached to credential store ({cache_key})")
    return result["access_token"]


def run_device_flow_emit_json(client_id: str, tenant_id: str) -> None:
    """Run one device-code flow covering all services' scopes and emit JSON events.

    Designed for host programs (e.g. the Nest web UI) that persist the resulting
    token cache themselves rather than relying on the credential store's injected
    provider — mirrors talon_tools.google.auth.run_oauth_emit_json.

    Emits one JSON object per line on stdout:
        {"event": "device_code", "user_code": "...", "verification_uri": "...", "message": "..."}
        {"event": "success", "token": "<serialized MSAL cache>", "username": "..."}
        {"event": "error", "message": "..."}
    """
    def emit(obj: dict) -> None:
        sys.stdout.write(json.dumps(obj) + "\n")
        sys.stdout.flush()

    cache = msal.SerializableTokenCache()
    app = msal.PublicClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        token_cache=cache,
    )

    flow = app.initiate_device_flow(scopes=ALL_SCOPES)
    if "user_code" not in flow:
        emit({"event": "error", "message": flow.get("error_description", str(flow))})
        return

    emit({
        "event": "device_code",
        "user_code": flow["user_code"],
        "verification_uri": flow["verification_uri"],
        "message": flow.get("message", ""),
    })

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        emit({"event": "error", "message": result.get("error_description", result.get("error", "unknown"))})
        return

    username = result.get("id_token_claims", {}).get("preferred_username", "unknown")
    emit({"event": "success", "token": cache.serialize(), "username": username})


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Authorize Microsoft Graph access")
    parser.add_argument("service", nargs="?", default="mail", help="mail | calendar | onedrive")
    parser.add_argument("--json", action="store_true", help="Emit JSON events to stdout (for host programs that persist the token)")
    parser.add_argument("--client-id", help="Azure AD app client ID (required with --json)")
    parser.add_argument("--tenant-id", help="Azure AD tenant ID (required with --json)")
    args = parser.parse_args()

    if args.json:
        if not args.client_id or not args.tenant_id:
            print(json.dumps({"event": "error", "message": "--client-id and --tenant-id are required with --json"}))
            sys.exit(1)
        run_device_flow_emit_json(args.client_id, args.tenant_id)
    else:
        authorize_interactive(args.service)
