"""Notion onboarding — integration token setup."""

from __future__ import annotations

from talon_tools.onboarding.base import ToolOnboarding, OnboardingStep


def get_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="notion",
        display_name="Notion",
        setup_type="manual",
        pip_extras=[],
        steps=[
            OnboardingStep(
                title="Create Notion Integration",
                instruction=(
                    "1. Go to https://www.notion.so/my-integrations\n"
                    "2. Click '+ New integration'\n"
                    "3. Give it a name (e.g. 'Talon')\n"
                    "4. Select the workspace to connect\n"
                    "5. Copy the 'Internal Integration Secret'"
                ),
                credential_key="NOTION_TOKEN",
            ),
            OnboardingStep(
                title="Share pages with integration",
                instruction=(
                    "For each Notion page/database you want accessible:\n"
                    "1. Open the page in Notion\n"
                    "2. Click '...' menu → 'Connections' → find your integration\n"
                    "3. Click 'Confirm'\n"
                    "\n"
                    "The integration can only see pages explicitly shared with it."
                ),
                credential_key=None,
                is_optional=True,
            ),
        ],
    )
