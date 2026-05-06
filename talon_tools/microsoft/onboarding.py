"""Microsoft onboarding — Azure AD app registration and OAuth."""

from __future__ import annotations

from talon_tools.onboarding.base import ToolOnboarding, OnboardingStep


def _run_microsoft_oauth() -> None:
    """Run the Microsoft device-code OAuth flow — prints URL + code, waits for approval."""
    from talon_tools.microsoft.auth import authorize_interactive
    authorize_interactive()


def get_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="microsoft",
        display_name="Microsoft (Outlook, Calendar, Teams)",
        setup_type="oauth",
        pip_extras=["msal"],
        steps=[
            OnboardingStep(
                title="Register Azure AD App (or use default)",
                instruction=(
                    "You can skip this step to use the pre-registered client.\n"
                    "Or register your own:\n"
                    "1. Go to https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps\n"
                    "2. Click 'New registration'\n"
                    "3. Name: 'Talon'\n"
                    "4. Supported account types: 'Personal Microsoft accounts only'\n"
                    "5. Copy the Application (client) ID"
                ),
                credential_key="MS_CLIENT_ID",
                is_optional=True,
            ),
            OnboardingStep(
                title="Authorize Microsoft Access",
                instruction=(
                    "A device-code flow will start. Open the URL shown and enter\n"
                    "the code to sign in with your Microsoft account.\n"
                    "The token is saved automatically."
                ),
                credential_key="MS_TOKEN_FILE",
                is_url=True,
                oauth_handler=_run_microsoft_oauth,
            ),
        ],
    )
