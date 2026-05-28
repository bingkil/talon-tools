"""Docenter onboarding — session cookie or JWT credential setup."""

from __future__ import annotations

from talon_tools.onboarding.base import ToolOnboarding, OnboardingStep, check_credential


def _is_docenter_configured() -> bool:
    """Docenter is configured if EITHER session cookie OR full JWT triple is set."""
    if check_credential("DOCENTER_SESSION"):
        return True
    return (
        check_credential("DOCENTER_JWT_KEY")
        and check_credential("DOCENTER_JWT_ISSUER")
        and check_credential("DOCENTER_USER_EMAIL")
    )


def get_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="docenter",
        display_name="Docenter (Actimize Documentation)",
        setup_type="manual",
        pip_extras=[],
        configured_check=_is_docenter_configured,
        steps=[
            OnboardingStep(
                title="Set Session Cookie",
                instruction=(
                    "Provide the Docenter session cookie.\n"
                    "\n"
                    "Easiest method (actimize-tools):\n"
                    "  Run: actimize-tools login\n"
                    "  This opens a browser, you log in, and the cookie is saved automatically.\n"
                    "\n"
                    "Manual method (browser dev tools):\n"
                    "  1. Go to https://docs.niceactimize.com/ and log in\n"
                    "  2. Open DevTools (F12) > Application > Cookies\n"
                    "  3. Copy the '_SESSION' cookie value"
                ),
                credential_key="DOCENTER_SESSION",
            ),
        ],
    )
