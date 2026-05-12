"""One-time Spotify OAuth setup script.

Run this once on the server to authorize Talon to access your Spotify account:

    python -m talon_tools.spotify.setup

It will print a URL. Open it in a browser, approve the app, then paste the
redirect URL back here. The token is saved locally and auto-refreshes forever.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
from pathlib import Path

from .auth import SCOPES, DEFAULT_TOKEN_FILE, DEFAULT_REDIRECT_URI, get_authorize_url, exchange_code
from talon_tools.credentials import get as cred


def main():
    client_id = cred("SPOTIFY_CLIENT_ID", "")
    client_secret = cred("SPOTIFY_CLIENT_SECRET", "")
    redirect_uri = os.environ.get("SPOTIFY_REDIRECT_URI", DEFAULT_REDIRECT_URI)
    token_file = os.environ.get("SPOTIFY_TOKEN_FILE", str(DEFAULT_TOKEN_FILE))

    if not client_id or not client_secret:
        print("Error: SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set.")
        print("Register an app at https://developer.spotify.com/dashboard")
        sys.exit(1)

    Path(token_file).parent.mkdir(parents=True, exist_ok=True)

    auth_url = get_authorize_url(client_id, redirect_uri)

    print("=== Spotify Authorization ===")
    print()
    print("1. Open this URL in your browser:")
    print()
    print(f"   {auth_url}")
    print()
    print(f"2. Approve the app. You'll be redirected to: {redirect_uri}?code=...")
    print()
    print("3. Paste the full redirect URL here:")
    print()

    redirected_url = input("   URL: ").strip()

    # Extract code from redirect URL
    parsed = urllib.parse.urlparse(redirected_url)
    params = urllib.parse.parse_qs(parsed.query)
    code = params.get("code", [None])[0]

    if not code:
        print("Error: Could not extract authorization code from URL.")
        sys.exit(1)

    token_info = exchange_code(code, client_id, client_secret, redirect_uri)

    from talon_tools.credential_store import save_encrypted
    enc_path = save_encrypted(json.dumps(token_info), Path(token_file))
    print()
    print(f"Success! Token saved to: {enc_path} (encrypted)")
    print("Talon can now control Spotify. No need to run this again.")


if __name__ == "__main__":
    main()
