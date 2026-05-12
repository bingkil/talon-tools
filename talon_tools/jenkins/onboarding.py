"""Jenkins onboarding — API token setup.

Supports multiple named instances.  The default instance uses
``JENKINS_URL`` / ``JENKINS_USERNAME`` / ``JENKINS_TOKEN``.
Additional instances use ``JENKINS_<NAME>_URL`` etc.
"""

from __future__ import annotations

from talon_tools.onboarding.base import ToolOnboarding, OnboardingStep


def get_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="jenkins",
        display_name="Jenkins",
        setup_type="manual",
        pip_extras=[],
        steps=[
            OnboardingStep(
                title="Set Jenkins URL",
                instruction=(
                    "Provide your Jenkins server URL.\n"
                    "Example: https://jenkins.company.com\n\n"
                    "For additional instances, add JENKINS_<NAME>_URL\n"
                    "(e.g. JENKINS_PROD_URL, JENKINS_STAGING_URL)."
                ),
                credential_key="JENKINS_URL",
            ),
            OnboardingStep(
                title="Set Jenkins Username",
                instruction="Provide your Jenkins username.",
                credential_key="JENKINS_USERNAME",
            ),
            OnboardingStep(
                title="Create API Token",
                instruction=(
                    "1. Log in to Jenkins\n"
                    "2. Click your name (top right) → Configure\n"
                    "3. Under 'API Token', click 'Add new Token'\n"
                    "4. Give it a name (e.g. 'Talon') and click 'Generate'\n"
                    "5. Copy the token (it won't be shown again)"
                ),
                credential_key="JENKINS_TOKEN",
            ),
        ],
    )
