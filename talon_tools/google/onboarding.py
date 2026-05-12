"""Google onboarding — OAuth credentials and authorization."""

from __future__ import annotations

from talon_tools.onboarding.base import ToolOnboarding, OnboardingStep


def _run_google_setup() -> None:
    """Run the automated GCP setup — creates project, enables APIs, saves credentials.

    Requires gcloud CLI (https://cloud.google.com/sdk/docs/install).
    """
    from talon_tools.google.setup import run_setup
    run_setup(login_after=True)


def _run_google_oauth() -> None:
    """Run the Google OAuth flow — opens browser, handles callback, saves token."""
    from talon_tools.google.auth import authorize_interactive
    authorize_interactive()


def get_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="google",
        display_name="Google (Gmail, Calendar, Drive, YouTube, etc.)",
        setup_type="oauth",
        pip_extras=["google-auth-oauthlib"],
        dependencies=["gcloud"],
        steps=[
            OnboardingStep(
                title="Set up GCP project and OAuth credentials",
                instruction=(
                    "Automated setup via gcloud CLI:\n"
                    "  - Creates/selects a GCP project\n"
                    "  - Enables Workspace APIs (Gmail, Calendar, Drive, etc.)\n"
                    "  - Configures OAuth consent screen\n"
                    "  - Guides you to create an OAuth client and paste credentials\n"
                    "\n"
                    "Requires: gcloud CLI (https://cloud.google.com/sdk/docs/install)\n"
                    "Run manually: python -m talon_tools.google.setup"
                ),
                credential_key="GOOGLE_CREDENTIALS_FILE",
                oauth_handler=_run_google_setup,
            ),
            OnboardingStep(
                title="Authorize Google Access",
                instruction=(
                    "A browser will open for you to grant access to your Google\n"
                    "account. The token is saved automatically."
                ),
                credential_key="GOOGLE_TOKEN_FILE",
                is_url=True,
                oauth_handler=_run_google_oauth,
            ),
        ],
    )


def get_youtube_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="youtube",
        display_name="YouTube",
        setup_type="oauth",
        steps=[
            OnboardingStep(
                title="Enable YouTube Data API v3",
                instruction=(
                    "1. Go to https://console.cloud.google.com/apis/library\n"
                    "2. Search for 'YouTube Data API v3'\n"
                    "3. Click 'Enable'\n"
                    "4. Ensure your Google OAuth credentials (credentials.json) include YouTube scope"
                ),
                credential_key="GOOGLE_CREDENTIALS_FILE",
                is_optional=True,
            ),
            OnboardingStep(
                title="Authorize Google with YouTube scope",
                instruction=(
                    "A browser will open for Google OAuth.\n"
                    "Make sure to grant YouTube access when prompted.\n"
                    "Note: If you already authorized Google without YouTube scope,\n"
                    "delete the existing token.json and re-authorize."
                ),
                credential_key="GOOGLE_TOKEN_FILE",
                is_optional=True,
                oauth_handler=_run_google_oauth,
            ),
        ],
    )
