"""WhatsApp onboarding — wacli auth and initial sync."""

from __future__ import annotations

from talon_tools.onboarding.base import ToolOnboarding, OnboardingStep


def get_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="wa",
        display_name="WhatsApp",
        setup_type="qr",
        category="channel",
        dependencies=["wacli"],
        steps=[
            OnboardingStep(
                title="Pair WhatsApp",
                instruction=(
                    "This will show a QR code. Scan it with your WhatsApp app:\n"
                    "  WhatsApp → Settings → Linked Devices → Link a Device"
                ),
                is_command=True,
                command=["wacli", "auth"],
                credential_key=None,
            ),
            OnboardingStep(
                title="Initial sync",
                instruction=(
                    "Run initial message sync to populate the local store.\n"
                    "This may take a minute depending on message history."
                ),
                is_command=True,
                command=["wacli", "sync"],
                credential_key=None,
            ),
        ],
    )
