"""Spotify onboarding — developer app setup and OAuth."""

from __future__ import annotations

from talon_tools.onboarding.base import ToolOnboarding, OnboardingStep


def _run_spotify_oauth() -> None:
    """Run Spotify OAuth flow — opens browser, catches callback on local server."""
    import json
    import webbrowser
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from pathlib import Path
    from urllib.parse import urlparse, parse_qs

    from talon_tools.credentials import get as cred
    from talon_tools.spotify.auth import (
        get_authorize_url, exchange_code, DEFAULT_REDIRECT_URI, DEFAULT_TOKEN_FILE,
    )

    client_id = cred("SPOTIFY_CLIENT_ID", "")
    client_secret = cred("SPOTIFY_CLIENT_SECRET", "")
    redirect_uri = cred("SPOTIFY_REDIRECT_URI", DEFAULT_REDIRECT_URI)
    token_file = cred("SPOTIFY_TOKEN_FILE", str(DEFAULT_TOKEN_FILE))

    if not client_id or not client_secret:
        raise RuntimeError("SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set first.")

    auth_url = get_authorize_url(client_id, redirect_uri)

    # Parse port from redirect URI
    parsed_redirect = urlparse(redirect_uri)
    port = parsed_redirect.port or 8888

    authorization_code: list[str] = []

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            code = query.get("code", [None])[0]
            if code:
                authorization_code.append(code)
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h2>Authorization successful!</h2>"
                    b"<p>You can close this tab and return to the terminal.</p></body></html>"
                )
            else:
                error = query.get("error", ["unknown"])[0]
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(f"<html><body><h2>Error: {error}</h2></body></html>".encode())

        def log_message(self, format, *args):
            pass  # Suppress server logs

    server = HTTPServer(("127.0.0.1", port), CallbackHandler)
    print(f"    Opening browser for Spotify authorization...")
    webbrowser.open(auth_url)

    # Wait for one request (the callback)
    server.handle_request()
    server.server_close()

    if not authorization_code:
        raise RuntimeError("No authorization code received from Spotify.")

    # Exchange code for token
    token_info = exchange_code(authorization_code[0], client_id, client_secret, redirect_uri)

    path = Path(token_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token_info))
    print(f"    Token saved to: {token_file}")


def get_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="spotify",
        display_name="Spotify",
        setup_type="oauth",
        pip_extras=["httpx"],
        steps=[
            OnboardingStep(
                title="Create Spotify Developer App",
                instruction=(
                    "1. Go to https://developer.spotify.com/dashboard\n"
                    "2. Log in with your Spotify account\n"
                    "3. Click 'Create App'\n"
                    "4. Select 'Web API' when asked which API/SDK to use\n"
                    "5. Set the Redirect URI to: http://127.0.0.1:8888/callback\n"
                    "6. Copy the Client ID and Client Secret"
                ),
                credential_key="SPOTIFY_CLIENT_ID",
            ),
            OnboardingStep(
                title="Set Client Secret",
                instruction="Provide the Client Secret from your Spotify app settings.",
                credential_key="SPOTIFY_CLIENT_SECRET",
            ),
            OnboardingStep(
                title="Authorize Spotify Access",
                instruction=(
                    "A browser will open for you to approve the Spotify app.\n"
                    "The token is saved automatically after you approve."
                ),
                credential_key=None,
                is_url=True,
                oauth_handler=_run_spotify_oauth,
            ),
        ],
    )
