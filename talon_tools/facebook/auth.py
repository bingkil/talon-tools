"""Auth helpers — load Facebook cookies and build Playwright cookie objects."""

from __future__ import annotations

from talon_tools.credentials import get as cred


def load_cookies() -> dict[str, str]:
    """Load Facebook session cookies from credentials.

    Required: FB_C_USER, FB_XS (or facebook.c_user, facebook.xs in credentials.yaml)
    Optional: FB_DATR, FB_FR
    """
    c_user = cred("FB_C_USER", "") or cred("FACEBOOK_C_USER", "")
    xs = cred("FB_XS", "") or cred("FACEBOOK_XS", "")

    if not c_user or not xs:
        raise RuntimeError(
            "Facebook cookies not found. Set FB_C_USER and FB_XS env vars. "
            "Extract from Chrome DevTools > Application > Cookies > facebook.com"
        )

    cookies = {"c_user": c_user, "xs": xs}

    for key in ("FB_DATR", "FB_FR"):
        val = cred(key, "")
        if val:
            cookies[key[3:].lower()] = val

    return cookies


def playwright_cookies(cookies: dict[str, str]) -> list[dict]:
    """Convert flat cookie dict to Playwright's add_cookies format."""
    return [
        {"name": k, "value": v, "domain": ".facebook.com", "path": "/"}
        for k, v in cookies.items()
    ]
