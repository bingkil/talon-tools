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
                    "Provide the Docenter JWT signing key.\n"
                    "This is the shared secret used to generate auth tokens\n"
                    "for the Zoomin-based documentation portal."
                ),
                credential_key="DOCENTER_JWT_KEY",
            ),
            OnboardingStep(
                title="Set JWT Issuer",
                instruction=(
                    "Provide the JWT issuer URL.\n"
                    "This is the 'iss' claim value for token generation."
                ),
                credential_key="DOCENTER_JWT_ISSUER",
            ),
            OnboardingStep(
                title="Set User Email",
                instruction="Provide your Actimize email address (used as 'sub' claim in JWT).",
                credential_key="DOCENTER_USER_EMAIL",
            ),
        ],
    )
