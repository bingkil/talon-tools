"""ServiceNow onboarding — instance credentials setup."""

from __future__ import annotations

from talon_tools.onboarding.base import ToolOnboarding, OnboardingStep


def get_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="servicenow",
        display_name="ServiceNow",
        setup_type="manual",
        pip_extras=[],
        steps=[
            OnboardingStep(
                title="Set ServiceNow Instance URL",
                instruction=(
                    "Provide your ServiceNow instance URL.\n"
                    "Example: https://yourcompany.service-now.com"
                ),
                credential_key="SERVICENOW_URL",
            ),
            OnboardingStep(
                title="Set ServiceNow Username",
                instruction="Provide your ServiceNow username.",
                credential_key="SERVICENOW_USERNAME",
            ),
            OnboardingStep(
                title="Set ServiceNow Password",
                instruction="Provide your ServiceNow password or API key.",
                credential_key="SERVICENOW_PASSWORD",
            ),
        ],
    )
