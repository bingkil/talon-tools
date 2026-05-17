"""Tool onboarding registry — discovers onboarding from each tool module."""

from __future__ import annotations

from .base import ToolOnboarding, OnboardingStep


# ---------------------------------------------------------------------------
# Zero-config tools (no setup needed)
# ---------------------------------------------------------------------------

def _zero_config(service: str, display_name: str) -> ToolOnboarding:
    return ToolOnboarding(
        service=service,
        display_name=display_name,
        setup_type="zero",
        steps=[],
    )


# ---------------------------------------------------------------------------
# Channels (no tool module in talon-tools, onboarding lives here)
# ---------------------------------------------------------------------------

def _telegram_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="telegram",
        display_name="Telegram",
        setup_type="manual",
        category="channel",
        steps=[
            OnboardingStep(
                title="Create a Telegram Bot",
                instruction=(
                    "1. Open Telegram and search for @BotFather\n"
                    "2. Send /newbot and follow the prompts\n"
                    "3. Choose a name and username for your bot\n"
                    "4. BotFather will give you an API token"
                ),
                credential_key="TELEGRAM_TOKEN",
            ),
            OnboardingStep(
                title="Get your Chat ID",
                instruction=(
                    "1. Start a conversation with your new bot in Telegram\n"
                    "2. Send any message to it (e.g. 'hi')\n"
                    "3. We'll auto-detect your chat_id from the bot's updates"
                ),
                credential_key="TELEGRAM_CHAT_ID",
                is_optional=True,
            ),
        ],
    )


def _discord_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="discord",
        display_name="Discord",
        setup_type="manual",
        category="channel",
        steps=[
            OnboardingStep(
                title="Create a Discord Bot",
                instruction=(
                    "1. Go to https://discord.com/developers/applications\n"
                    "2. Click 'New Application', give it a name\n"
                    "3. Go to Bot → click 'Reset Token' to get the bot token\n"
                    "4. Enable 'Message Content Intent' under Privileged Gateway Intents\n"
                    "5. Go to OAuth2 → URL Generator:\n"
                    "   - Scopes: bot\n"
                    "   - Bot Permissions: Send Messages, Read Message History\n"
                    "6. Copy the generated URL and open it to invite the bot to your server"
                ),
                credential_key="DISCORD_TOKEN",
            ),
            OnboardingStep(
                title="Set allowed user IDs (optional)",
                instruction=(
                    "Restrict the bot to respond only to specific users.\n"
                    "To get your user ID: Settings → Advanced → enable Developer Mode,\n"
                    "then right-click your username → Copy User ID.\n"
                    "Enter comma-separated IDs, or leave empty to allow all users."
                ),
                credential_key="DISCORD_ALLOWED_USERS",
                is_optional=True,
            ),
        ],
    )


def _slack_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="slack",
        display_name="Slack",
        setup_type="manual",
        category="channel",
        steps=[
            OnboardingStep(
                title="Create a Slack App",
                instruction=(
                    "1. Go to https://api.slack.com/apps\n"
                    "2. Click 'Create New App' → 'From scratch'\n"
                    "3. Name it 'Talon' and select your workspace\n"
                    "4. Go to OAuth & Permissions → add Bot Token Scopes:\n"
                    "   - chat:write, channels:history, groups:history,\n"
                    "     im:history, mpim:history, app_mentions:read\n"
                    "5. Install the app to your workspace\n"
                    "6. Copy the Bot User OAuth Token (starts with xoxb-)"
                ),
                credential_key="SLACK_BOT_TOKEN",
            ),
            OnboardingStep(
                title="Enable Socket Mode",
                instruction=(
                    "1. Go to Settings → Socket Mode → Enable Socket Mode\n"
                    "2. Create an App-Level Token with connections:write scope\n"
                    "3. Copy the token (starts with xapp-)"
                ),
                credential_key="SLACK_APP_TOKEN",
            ),
        ],
    )


def _viber_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="viber",
        display_name="Viber",
        setup_type="manual",
        category="channel",
        steps=[
            OnboardingStep(
                title="Create a Viber Bot",
                instruction=(
                    "1. Go to https://partners.viber.com/\n"
                    "2. Sign in and click 'Create Bot Account'\n"
                    "3. Fill in bot name, avatar, and category\n"
                    "4. Copy the Authentication Token from the bot's settings"
                ),
                credential_key="VIBER_AUTH_TOKEN",
            ),
            OnboardingStep(
                title="Set bot sender name (optional)",
                instruction=(
                    "The name shown when your bot sends messages.\n"
                    "Leave empty to use 'Talon' as default."
                ),
                credential_key="VIBER_SENDER_NAME",
                is_optional=True,
            ),
        ],
    )


def _install_signal_cli() -> None:
    """Download and install signal-cli + Java to ~/.config/talon/."""
    import io
    import json
    import platform
    import shutil
    import tarfile
    import urllib.request
    import zipfile
    from pathlib import Path

    talon_dir = Path.home() / ".config" / "talon"
    signal_dir = talon_dir / "signal-cli"
    jre_dir = talon_dir / "jre"

    # --- Java check ---
    def _find_java() -> Path | None:
        """Find Java 21+ (signal-cli 0.13+ needs 21)."""
        # Check Talon-managed JRE
        if jre_dir.exists():
            for java in jre_dir.glob("*/bin/java.exe"):
                return java
            for java in jre_dir.glob("*/bin/java"):
                return java
        # Check system Java
        system = shutil.which("java")
        if system:
            return Path(system)
        return None

    def _install_java() -> None:
        """Download Temurin 21 JRE to ~/.config/talon/jre/."""
        arch = platform.machine().lower()
        if arch in ("x86_64", "amd64"):
            arch = "x64"
        elif arch in ("aarch64", "arm64"):
            arch = "aarch64"

        os_name = "windows" if platform.system() == "Windows" else "linux"
        ext = "zip" if os_name == "windows" else "tar.gz"

        api_url = (
            f"https://api.adoptium.net/v3/binary/latest/21/ga/"
            f"{os_name}/{arch}/jre/hotspot/normal/eclipse"
        )
        print(f"    Downloading Temurin 21 JRE...")
        jre_dir.mkdir(parents=True, exist_ok=True)

        req = urllib.request.Request(api_url, headers={"User-Agent": "talon-tools"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()

        if ext == "zip":
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                zf.extractall(jre_dir)
        else:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
                tf.extractall(jre_dir)

        print(f"    ✓ Java installed to {jre_dir}")

    # --- signal-cli download ---
    def _install_signal_cli_binary() -> None:
        """Download latest signal-cli from GitHub releases."""
        print("    Fetching latest signal-cli release...")
        api_url = "https://api.github.com/repos/AsamK/signal-cli/releases/latest"
        req = urllib.request.Request(api_url, headers={"User-Agent": "talon-tools"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            release = json.loads(resp.read())

        tag = release["tag_name"]  # e.g. "v0.13.8"
        version = tag.lstrip("v")

        # signal-cli publishes a tar.gz archive
        archive_name = f"signal-cli-{version}.tar.gz"
        asset = next(
            (a for a in release["assets"] if a["name"] == archive_name),
            None,
        )
        if not asset:
            # Fallback: try any tar.gz
            asset = next(
                (a for a in release["assets"] if a["name"].endswith(".tar.gz")),
                None,
            )
        if not asset:
            raise RuntimeError(
                f"Could not find signal-cli archive in release {tag}.\n"
                f"    Download manually: https://github.com/AsamK/signal-cli/releases"
            )

        print(f"    Downloading signal-cli {version}...")
        req = urllib.request.Request(
            asset["browser_download_url"],
            headers={"User-Agent": "talon-tools"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()

        # Remove old install
        if signal_dir.exists():
            shutil.rmtree(signal_dir)

        # Extract — archive contains signal-cli-X.Y.Z/ folder
        signal_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            tf.extractall(talon_dir)

        # Rename extracted folder to signal-cli
        extracted = talon_dir / f"signal-cli-{version}"
        if extracted.exists() and extracted != signal_dir:
            if signal_dir.exists():
                shutil.rmtree(signal_dir)
            extracted.rename(signal_dir)

        # On Windows, create a .bat wrapper if not present
        if platform.system() == "Windows":
            bat = signal_dir / "bin" / "signal-cli.bat"
            if not bat.exists():
                # The tar.gz should include it, but create fallback
                bat.write_text(
                    f'@echo off\n"{_find_java()}" -jar "{signal_dir / "lib" / "signal-cli.jar"}" %*\n'
                )

        print(f"    ✓ signal-cli {version} installed to {signal_dir}")

    # --- Main flow ---
    java = _find_java()
    if not java:
        _install_java()
        java = _find_java()
        if not java:
            raise RuntimeError("Failed to install Java. Please install Java 21+ manually.")

    if not (signal_dir / "bin").exists():
        _install_signal_cli_binary()
    else:
        print(f"    ✓ signal-cli already installed at {signal_dir}")


def _signal_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="signal",
        display_name="Signal",
        setup_type="qr",
        category="channel",
        steps=[
            OnboardingStep(
                title="Install signal-cli and Java",
                instruction=(
                    "signal-cli will be downloaded to ~/.config/talon/signal-cli/\n"
                    "Java (Temurin 21 JRE) will be installed to ~/.config/talon/jre/ if needed.\n"
                    "\n"
                    "This does NOT modify your system PATH or Java installation."
                ),
                oauth_handler=_install_signal_cli,
            ),
            OnboardingStep(
                title="Link Signal as secondary device",
                instruction=(
                    "This will run 'signal-cli link' to generate a QR code.\n"
                    "Scan it with your Signal app:\n"
                    "  Signal → Settings → Linked Devices → Link New Device\n"
                    "\n"
                    "If you prefer, enter your phone number (E.164 format, e.g. +1234567890)."
                ),
                is_command=True,
                command=["signal-cli", "link", "-n", "Talon"],
                credential_key="SIGNAL_ACCOUNT",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Provider: GitHub Models
# ---------------------------------------------------------------------------

def _validate_github_token(token: str) -> None:
    """Validate a GitHub token by calling the user endpoint."""
    import json
    import urllib.request
    import urllib.error

    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "talon-tools",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            print(f"    ✓ Authenticated as {data.get('login', 'unknown')}")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ValueError(f"Invalid GitHub token ({e.code})")
    except urllib.error.URLError:
        print("    ⚠ Could not reach api.github.com — skipping validation")


def _github_onboarding() -> ToolOnboarding:
    return ToolOnboarding(
        service="github",
        display_name="GitHub Models (Copilot Enterprise)",
        setup_type="manual",
        category="provider",
        steps=[
            OnboardingStep(
                title="Create a fine-grained Personal Access Token",
                instruction=(
                    "1. Go to https://github.com/settings/personal-access-tokens/new\n"
                    "2. Under Account permissions, add 'Models' with Read-only access\n"
                    "3. Set expiration to your preference\n"
                    "4. Click 'Generate token' and copy it (starts with github_pat_)"
                ),
                credential_key="GITHUB_TOKEN",
            ),
            OnboardingStep(
                title="Validate token",
                instruction="Verifying your GitHub token...",
                oauth_handler=_validate_github_token_from_env,
                is_optional=True,
            ),
        ],
    )


def _validate_github_token_from_env() -> None:
    """Validate the stored GITHUB_TOKEN."""
    import os
    from talon_tools.credentials import get as cred_get
    token = cred_get("GITHUB_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("    ⚠ No GITHUB_TOKEN found — skipping validation")
        return
    _validate_github_token(token)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def get_all_onboardings() -> dict[str, ToolOnboarding]:
    """Return all tool onboarding definitions.

    Each tool module provides its own `onboarding.py` with a `get_onboarding()`
    function. Channels without a tool module are defined above.
    """
    from talon_tools.atlassian.onboarding import get_onboarding as atlassian
    from talon_tools.notion.onboarding import get_onboarding as notion
    from talon_tools.servicenow.onboarding import get_onboarding as servicenow
    from talon_tools.google.onboarding import get_onboarding as google
    from talon_tools.microsoft.onboarding import get_onboarding as microsoft
    from talon_tools.spotify.onboarding import get_onboarding as spotify
    from talon_tools.x.onboarding import get_onboarding as x
    from talon_tools.facebook.onboarding import get_onboarding as facebook
    from talon_tools.wa.onboarding import get_onboarding as wa

    return {
        # Zero-config
        "search": _zero_config("search", "Web Search (DuckDuckGo)"),
        "terminal": _zero_config("terminal", "Terminal"),
        "workspace": _zero_config("workspace", "Workspace"),
        # Tools (onboarding from each module)
        "atlassian": atlassian(),
        "notion": notion(),
        "servicenow": servicenow(),
        "google": google(),
        "microsoft": microsoft(),
        "spotify": spotify(),
        "x": x(),
        "facebook": facebook(),
        # Providers
        "github": _github_onboarding(),
        # Channels
        "telegram": _telegram_onboarding(),
        "discord": _discord_onboarding(),
        "slack": _slack_onboarding(),
        "viber": _viber_onboarding(),
        "signal": _signal_onboarding(),
        "wa": wa(),
    }
