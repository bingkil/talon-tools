"""Browser cookie extraction — auto-reads cookies from Chrome/Edge/Firefox."""

from __future__ import annotations


def extract_cookies(domain: str, cookie_names: list[str]) -> dict[str, str]:
    """Try to extract specific cookies from installed browsers.

    Args:
        domain: The domain to get cookies for (e.g. ".x.com", ".facebook.com")
        cookie_names: List of cookie names to look for

    Returns:
        Dict of {cookie_name: value} for cookies that were found.
        Missing cookies are omitted from the result.
    """
    try:
        import browser_cookie3
    except ImportError:
        return {}

    found: dict[str, str] = {}

    # Try browsers in order of popularity
    browsers = [
        ("Chrome", browser_cookie3.chrome),
        ("Edge", browser_cookie3.edge),
        ("Firefox", browser_cookie3.firefox),
        ("Brave", browser_cookie3.brave),
    ]

    for browser_name, browser_fn in browsers:
        if len(found) == len(cookie_names):
            break  # Already got everything
        try:
            cj = browser_fn(domain_name=domain)
            for cookie in cj:
                if cookie.name in cookie_names and cookie.name not in found:
                    if cookie.value:
                        found[cookie.name] = cookie.value
        except Exception:
            continue  # Browser not installed or locked

    return found
