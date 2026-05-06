"""X (Twitter) onboarding — session cookie extraction."""

from __future__ import annotations

from talon_tools.onboarding.base import ToolOnboarding, OnboardingStep


def _extract_x_cookies() -> None:
    """Open X in browser, wait for user to log in, then extract cookies."""
    import webbrowser
    from talon_tools.onboarding.cookies import extract_cookies
    from talon_tools.credentials import set_credential

    # First try without opening browser (user might already be logged in)
    cookies = extract_cookies(".x.com", ["auth_token", "ct0"])

    if "auth_token" not in cookies or "ct0" not in cookies:
        print("    Opening x.com in your browser...")
        webbrowser.open("https://x.com")
        input("    Log in to X, then CLOSE the browser and press Enter... ")
        cookies = extract_cookies(".x.com", ["auth_token", "ct0"])

    # Retry once more if still not found
    if "auth_token" not in cookies or "ct0" not in cookies:
        input("    Still not found. Close ALL browser windows and press Enter to retry... ")
        cookies = extract_cookies(".x.com", ["auth_token", "ct0"])

    if "auth_token" in cookies and "ct0" in cookies:
        set_credential("X_AUTH_TOKEN", cookies["auth_token"])
        set_credential("X_CT0", cookies["ct0"])
        print("    Found auth_token and ct0 — saved automatically.")
    else:
        missing = [k for k in ["auth_token", "ct0"] if k not in cookies]
        raise RuntimeError(
            f"Could not find cookies: {', '.join(missing)}. "
            "Extract manually from DevTools (F12) → Application → Cookies → x.com"
        )


def get_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="x",
        display_name="X (Twitter)",
        setup_type="manual",
        pip_extras=["browser-cookie3"],
        steps=[
            OnboardingStep(
                title="Extract X session cookies",
                instruction=(
                    "We'll try to read your X login cookies directly from your browser.\n"
                    "Make sure you're logged in to x.com in Chrome, Edge, or Firefox.\n"
                    "\n"
                    "If auto-extraction fails, you can get them manually:\n"
                    "  DevTools (F12) → Application → Cookies → https://x.com\n"
                    "  Copy 'auth_token' and 'ct0' values."
                ),
                credential_key="X_AUTH_TOKEN",
                oauth_handler=_extract_x_cookies,
            ),
            OnboardingStep(
                title="X ct0 cookie (if not auto-extracted)",
                instruction=(
                    "Paste the 'ct0' cookie value from x.com.\n"
                    "  DevTools (F12) → Application → Cookies → https://x.com"
                ),
                credential_key="X_CT0",
            ),
        ],
    )
