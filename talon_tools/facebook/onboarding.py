"""Facebook onboarding — session cookie extraction."""

from __future__ import annotations

from talon_tools.onboarding.base import ToolOnboarding, OnboardingStep


def _extract_fb_cookies() -> None:
    """Open Facebook in browser, wait for user to log in, then extract cookies."""
    import webbrowser
    from talon_tools.onboarding.cookies import extract_cookies
    from talon_tools.credentials import set_credential

    # First try without opening browser (user might already be logged in)
    cookies = extract_cookies(".facebook.com", ["c_user", "xs"])

    if "c_user" not in cookies or "xs" not in cookies:
        print("    Opening facebook.com in your browser...")
        webbrowser.open("https://www.facebook.com")
        input("    Log in to Facebook, then CLOSE the browser and press Enter... ")
        cookies = extract_cookies(".facebook.com", ["c_user", "xs"])

    # Retry once more if still not found
    if "c_user" not in cookies or "xs" not in cookies:
        input("    Still not found. Close ALL browser windows and press Enter to retry... ")
        cookies = extract_cookies(".facebook.com", ["c_user", "xs"])

    if "c_user" in cookies and "xs" in cookies:
        set_credential("FB_C_USER", cookies["c_user"])
        set_credential("FB_XS", cookies["xs"])
        print("    Found c_user and xs — saved automatically.")
    else:
        missing = [k for k in ["c_user", "xs"] if k not in cookies]
        raise RuntimeError(
            f"Could not find cookies: {', '.join(missing)}. "
            "Extract manually from DevTools (F12) → Application → Cookies → facebook.com"
        )


def get_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="facebook",
        display_name="Facebook",
        setup_type="manual",
        pip_extras=["browser-cookie3"],
        steps=[
            OnboardingStep(
                title="Extract Facebook session cookies",
                instruction=(
                    "We'll try to read your Facebook login cookies directly from your browser.\n"
                    "Make sure you're logged in to facebook.com in Chrome, Edge, or Firefox.\n"
                    "\n"
                    "If auto-extraction fails, you can get them manually:\n"
                    "  DevTools (F12) → Application → Cookies → https://www.facebook.com\n"
                    "  Copy 'c_user' and 'xs' values."
                ),
                credential_key="FB_C_USER",
                oauth_handler=_extract_fb_cookies,
            ),
            OnboardingStep(
                title="Facebook xs cookie (if not auto-extracted)",
                instruction=(
                    "Paste the 'xs' cookie value from facebook.com.\n"
                    "  DevTools (F12) → Application → Cookies → https://www.facebook.com"
                ),
                credential_key="FB_XS",
            ),
        ],
    )
