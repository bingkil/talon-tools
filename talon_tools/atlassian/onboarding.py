"""Atlassian onboarding — Jira/Confluence API token setup."""

from __future__ import annotations

from talon_tools.onboarding.base import ToolOnboarding, OnboardingStep


def get_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="atlassian",
        display_name="Atlassian (Jira/Confluence)",
        setup_type="manual",
        pip_extras=[],
        steps=[
            OnboardingStep(
                title="Set Atlassian URL",
                instruction=(
                    "Provide your Atlassian instance URL.\n"
                    "Example: https://yourcompany.atlassian.net"
                ),
                credential_key="JIRA_URL",
            ),
            OnboardingStep(
                title="Set Atlassian Username",
                instruction="Provide your Atlassian email address.",
                credential_key="JIRA_USERNAME",
            ),
            OnboardingStep(
                title="Create API Token",
                instruction=(
                    "1. Go to https://id.atlassian.com/manage-profile/security/api-tokens\n"
                    "2. Click 'Create API token'\n"
                    "3. Give it a label (e.g. 'Talon')\n"
                    "4. Copy the token"
                ),
                credential_key="JIRA_API_TOKEN",
            ),
        ],
    )
