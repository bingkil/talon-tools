"""Docenter onboarding — JWT credential setup."""

from __future__ import annotations

from talon_tools.onboarding.base import ToolOnboarding, OnboardingStep


def get_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="docenter",
        display_name="Docenter (Actimize Documentation)",
        setup_type="manual",
        pip_extras=[],
        steps=[
            OnboardingStep(
                title="Set JWT Key",
                instruction=(
                    "Provide the Docenter JWT signing key (base64-encoded).\n"
                    "\n"
                    "To get this key:\n"
                    "  1. Go to https://actimize.zoominsoftware.io/admin\n"
                    "  2. Navigate to Settings > SSO & Authentication > JWT\n"
                    "  3. Copy the 'Signing Key' value\n"
                    "\n"
                    "If you don't have admin access, ask your Docenter admin\n"
                    "or check the team's shared credentials vault."
                ),
                credential_key="DOCENTER_JWT_KEY",
            ),
            OnboardingStep(
                title="Set JWT Issuer",
                instruction=(
                    "Provide the JWT issuer identifier.\n"
                    "This is the 'iss' claim value used when generating tokens.\n"
                    "\n"
                    "Typically this is your company's SSO issuer URL, e.g.:\n"
                    "  https://login.microsoftonline.com/<tenant-id>/v2.0\n"
                    "\n"
                    "Check the same JWT settings page in the Docenter admin panel,\n"
                    "or ask your identity team for the issuer value."
                ),
                credential_key="DOCENTER_JWT_ISSUER",
            ),
            OnboardingStep(
                title="Set User Email",
                instruction=(
                    "Provide your Actimize email address.\n"
                    "This is used as the 'sub' (subject) claim in the JWT.\n"
                    "\n"
                    "Use your standard corporate email, e.g. first.last@niceactimize.com"
                ),
                credential_key="DOCENTER_USER_EMAIL",
            ),
        ],
    )
